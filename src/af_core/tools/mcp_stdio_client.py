from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Mapping, Sequence
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from af_core.production import (
    ProductionSettings,
    SecretReference,
    redact_text,
    sanitized_environment,
    validate_environment_key,
)

from .mcp_context import MCPContextOperations
from .mcp_context_models import (
    MCPContextDiscoveryResult,
    MCPPromptDescriptor,
    MCPPromptResult,
    MCPResourceDescriptor,
    MCPResourceReadResult,
    MCPResourceTemplateDescriptor,
)

from .mcp_models import (
    MCPServerConfig,
    MCPToolCallResult,
    MCPToolDefinition,
)
from .models import (
    ExternalToolCall,
    ExternalToolDescriptor,
    ExternalToolResult,
    ExternalToolRisk,
    ExternalToolTransport,
    ToolExecutionStatus,
)


class MCPClientError(RuntimeError):
    """Raised when an MCP client operation fails."""


class MCPStdioClient:
    DEFAULT_ALLOWED_ENVIRONMENT_KEYS = {
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "TMPDIR",
        "PYTHONPATH",
        "VIRTUAL_ENV",
        "CARGO_HOME",
        "RUSTUP_HOME",
    }

    def __init__(
        self,
        config: MCPServerConfig,
        *,
        settings: ProductionSettings | None = None,
        environment_source: Mapping[str, str] | None = None,
        secret_environment: Mapping[
            str,
            SecretReference,
        ] | None = None,
    ) -> None:
        if (
            config.transport
            is not ExternalToolTransport.MCP_STDIO
        ):
            raise ValueError(
                "MCPStdioClient requires MCP_STDIO transport."
            )

        if not config.command:
            raise ValueError(
                "MCP stdio server command is required."
            )

        self.config = config
        self.settings = settings
        self._environment_source = dict(
            os.environ
            if environment_source is None
            else environment_source
        )
        self._secret_environment = dict(
            secret_environment or {}
        )
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._initialized = False

    @property
    def connected(self) -> bool:
        return (
            self._session is not None
            and self._initialized
        )

    def _build_environment(
        self,
    ) -> tuple[dict[str, str], tuple[str, ...]]:
        if self.settings is None:
            allowed_keys = set(
                self.DEFAULT_ALLOWED_ENVIRONMENT_KEYS
            )
            secret_keys: set[str] = set()
        else:
            allowed_keys = set(
                self.settings.allowed_environment_keys
            )
            secret_keys = set(
                self.settings.secret_environment_keys
            )

        environment = sanitized_environment(
            self._environment_source,
            allowed_keys=tuple(allowed_keys),
            secret_keys=tuple(secret_keys),
        )

        for key, value in self.config.environment.items():
            normalized = validate_environment_key(key)

            if normalized in secret_keys:
                raise MCPClientError(
                    "MCP secret environment variable must "
                    f"use SecretReference: {normalized}"
                )

            if (
                self.settings is not None
                and normalized not in allowed_keys
            ):
                raise MCPClientError(
                    "MCP environment variable is not "
                    f"allowed: {normalized}"
                )

            environment[normalized] = str(value)

        known_secrets: list[str] = []

        for key, reference in (
            self._secret_environment.items()
        ):
            normalized = validate_environment_key(key)

            if (
                self.settings is not None
                and normalized not in secret_keys
            ):
                raise MCPClientError(
                    "MCP secret environment variable is "
                    f"not declared: {normalized}"
                )

            value = reference.resolve(
                self._environment_source
            )

            if value is not None:
                environment[normalized] = value
                known_secrets.append(value)

        return environment, tuple(known_secrets)

    async def connect(self) -> None:
        if self.connected:
            return

        environment, known_secrets = (
            self._build_environment()
        )

        parameters = StdioServerParameters(
            command=self.config.command or "",
            args=list(self.config.arguments),
            env=environment,
        )

        stack = AsyncExitStack()

        try:
            read_stream, write_stream = (
                await stack.enter_async_context(
                    stdio_client(parameters)
                )
            )

            session = await stack.enter_async_context(
                ClientSession(
                    read_stream,
                    write_stream,
                )
            )

            await asyncio.wait_for(
                session.initialize(),
                timeout=self.config.timeout_seconds,
            )

        except Exception as exc:
            await stack.aclose()

            safe_error = redact_text(
                str(exc),
                known_secrets=known_secrets,
            )

            raise MCPClientError(
                "Unable to initialize MCP stdio server "
                f"{self.config.server_id}: {safe_error}"
            ) from exc

        self._stack = stack
        self._session = session
        self._initialized = True

    async def close(self) -> None:
        stack = self._stack

        self._session = None
        self._stack = None
        self._initialized = False

        if stack is not None:
            await stack.aclose()

    async def __aenter__(
        self,
    ) -> "MCPStdioClient":
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type,
        exc,
        traceback,
    ) -> None:
        del exc_type, exc, traceback
        await self.close()

    def context_operations(
        self,
    ) -> MCPContextOperations:
        session = self._require_session()

        return MCPContextOperations(
            session=session,
            timeout_seconds=self.config.timeout_seconds,
        )

    async def discover_context(
        self,
    ) -> MCPContextDiscoveryResult:
        return await self.context_operations().discover()

    async def list_resources(
        self,
    ) -> list[MCPResourceDescriptor]:
        return await self.context_operations().list_resources()

    async def list_resource_templates(
        self,
    ) -> list[MCPResourceTemplateDescriptor]:
        return await (
            self.context_operations()
            .list_resource_templates()
        )

    async def read_resource(
        self,
        uri: str,
    ) -> MCPResourceReadResult:
        return await self.context_operations().read_resource(
            uri
        )

    async def list_prompts(
        self,
    ) -> list[MCPPromptDescriptor]:
        return await self.context_operations().list_prompts()

    async def get_prompt(
        self,
        *,
        name: str,
        arguments: dict[str, str] | None = None,
    ) -> MCPPromptResult:
        return await self.context_operations().get_prompt(
            name=name,
            arguments=arguments,
        )

    async def ping(self) -> bool:
        session = self._require_session()

        try:
            await asyncio.wait_for(
                session.send_ping(),
                timeout=self.config.timeout_seconds,
            )
        except Exception as exc:
            raise MCPClientError(
                f"MCP ping failed: {exc}"
            ) from exc

        return True

    async def list_tools(
        self,
    ) -> list[MCPToolDefinition]:
        session = self._require_session()

        try:
            response = await asyncio.wait_for(
                session.list_tools(),
                timeout=self.config.timeout_seconds,
            )
        except Exception as exc:
            raise MCPClientError(
                f"MCP tool discovery failed: {exc}"
            ) from exc

        definitions: list[MCPToolDefinition] = []

        for tool in response.tools:
            payload = self._model_dump(tool)

            definitions.append(
                MCPToolDefinition.model_validate(
                    payload
                )
            )

        return definitions

    async def tool_descriptors(
        self,
        *,
        default_risk: ExternalToolRisk = (
            ExternalToolRisk.READ_ONLY
        ),
        risk_by_tool: dict[
            str,
            ExternalToolRisk,
        ] | None = None,
    ) -> list[ExternalToolDescriptor]:
        risk_overrides = risk_by_tool or {}

        tools = await self.list_tools()

        return [
            tool.to_external_descriptor(
                server_id=self.config.server_id,
                risk=risk_overrides.get(
                    tool.name,
                    default_risk,
                ),
                transport=(
                    ExternalToolTransport.MCP_STDIO
                ),
            ).model_copy(
                update={
                    "timeout_seconds": (
                        self.config.timeout_seconds
                    ),
                }
            )
            for tool in tools
        ]

    async def call_tool(
        self,
        call: ExternalToolCall,
        *,
        remote_tool_name: str | None = None,
    ) -> ExternalToolResult:
        session = self._require_session()

        tool_name = (
            remote_tool_name
            or self._remote_tool_name(
                call.tool_id
            )
        )

        started = time.perf_counter()

        try:
            response = await asyncio.wait_for(
                session.call_tool(
                    tool_name,
                    arguments=call.arguments,
                ),
                timeout=self.config.timeout_seconds,
            )

            raw = self._model_dump(response)
            mcp_result = (
                MCPToolCallResult.model_validate(raw)
            )

            duration_ms = (
                time.perf_counter() - started
            ) * 1000.0

            return ExternalToolResult(
                call_id=call.call_id,
                tool_id=call.tool_id,
                status=(
                    ToolExecutionStatus.FAILED
                    if mcp_result.isError
                    else ToolExecutionStatus.SUCCEEDED
                ),
                content=(
                    mcp_result.normalized_content()
                ),
                is_error=mcp_result.isError,
                error=(
                    self._error_text(mcp_result)
                    if mcp_result.isError
                    else None
                ),
                duration_ms=duration_ms,
                metadata={
                    "server_id": self.config.server_id,
                    "remote_tool_name": tool_name,
                    "_meta": mcp_result.meta,
                },
            )

        except TimeoutError:
            return ExternalToolResult(
                call_id=call.call_id,
                tool_id=call.tool_id,
                status=ToolExecutionStatus.TIMED_OUT,
                is_error=True,
                error=(
                    "MCP tool execution exceeded "
                    f"{self.config.timeout_seconds} seconds."
                ),
                duration_ms=(
                    time.perf_counter() - started
                )
                * 1000.0,
                metadata={
                    "server_id": self.config.server_id,
                    "remote_tool_name": tool_name,
                },
            )

        except Exception as exc:
            return ExternalToolResult(
                call_id=call.call_id,
                tool_id=call.tool_id,
                status=ToolExecutionStatus.FAILED,
                is_error=True,
                error=str(exc),
                duration_ms=(
                    time.perf_counter() - started
                )
                * 1000.0,
                metadata={
                    "server_id": self.config.server_id,
                    "remote_tool_name": tool_name,
                },
            )

    def handler(
        self,
        *,
        remote_tool_name: str,
    ):
        async def execute(
            call: ExternalToolCall,
        ) -> ExternalToolResult:
            return await self.call_tool(
                call,
                remote_tool_name=remote_tool_name,
            )

        return execute

    def _require_session(
        self,
    ) -> ClientSession:
        if not self.connected or self._session is None:
            raise MCPClientError(
                "MCP client is not connected."
            )

        return self._session

    def _remote_tool_name(
        self,
        tool_id: str,
    ) -> str:
        prefix = f"mcp:{self.config.server_id}:"

        if tool_id.startswith(prefix):
            name = tool_id[len(prefix):]

            if name:
                return name

        raise MCPClientError(
            "Unable to resolve remote MCP tool name "
            f"from tool ID: {tool_id}"
        )

    def _model_dump(
        self,
        value: Any,
    ) -> dict[str, Any]:
        if hasattr(value, "model_dump"):
            payload = value.model_dump(
                mode="json",
                by_alias=True,
            )
        elif isinstance(value, dict):
            payload = value
        else:
            raise MCPClientError(
                "MCP SDK returned an unsupported "
                f"response type: {type(value)!r}"
            )

        if not isinstance(payload, dict):
            raise MCPClientError(
                "MCP response must be an object."
            )

        return payload

    def _error_text(
        self,
        result: MCPToolCallResult,
    ) -> str:
        texts = [
            item.text
            for item in result.normalized_content()
            if item.text
        ]

        if texts:
            return "\n".join(texts)

        return "MCP tool returned an error result."
