from __future__ import annotations

import asyncio
import time
from contextlib import AsyncExitStack
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import (
    streamable_http_client,
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


class MCPHTTPClientError(RuntimeError):
    """Raised when an MCP HTTP client operation fails."""


class MCPHTTPClient:
    def __init__(
        self,
        config: MCPServerConfig,
    ) -> None:
        if (
            config.transport
            is not ExternalToolTransport.MCP_HTTP
        ):
            raise ValueError(
                "MCPHTTPClient requires MCP_HTTP transport."
            )

        if not config.url:
            raise ValueError(
                "MCP HTTP server URL is required."
            )

        self.config = config
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._initialized = False
        self._session_id: str | None = None

    @property
    def connected(self) -> bool:
        return (
            self._session is not None
            and self._initialized
        )

    @property
    def session_id(self) -> str | None:
        return self._session_id

    async def connect(self) -> None:
        if self.connected:
            return

        stack = AsyncExitStack()

        timeout = httpx.Timeout(
            self.config.timeout_seconds
        )

        http_client = httpx.AsyncClient(
            headers=dict(self.config.headers),
            timeout=timeout,
            follow_redirects=False,
        )

        await stack.enter_async_context(
            http_client
        )

        try:
            transport_result = (
                await stack.enter_async_context(
                    streamable_http_client(
                        self.config.url or "",
                        http_client=http_client,
                    )
                )
            )

            if len(transport_result) == 3:
                (
                    read_stream,
                    write_stream,
                    get_session_id,
                ) = transport_result
            else:
                read_stream, write_stream = (
                    transport_result
                )
                get_session_id = None

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

            session_id = None

            if callable(get_session_id):
                try:
                    session_id = get_session_id()
                except Exception:
                    session_id = None

        except Exception as exc:
            await stack.aclose()

            raise MCPHTTPClientError(
                "Unable to initialize MCP HTTP server "
                f"{self.config.server_id}: {exc}"
            ) from exc

        self._stack = stack
        self._session = session
        self._session_id = session_id
        self._initialized = True

    async def close(self) -> None:
        stack = self._stack

        self._session = None
        self._stack = None
        self._session_id = None
        self._initialized = False

        if stack is not None:
            await stack.aclose()

    async def __aenter__(
        self,
    ) -> "MCPHTTPClient":
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
            raise MCPHTTPClientError(
                f"MCP HTTP ping failed: {exc}"
            ) from exc

        return True

    async def list_tools(
        self,
    ) -> list[MCPToolDefinition]:
        session = self._require_session()

        definitions: list[MCPToolDefinition] = []
        cursor: str | None = None

        while True:
            try:
                response = await asyncio.wait_for(
                    session.list_tools(
                        cursor=cursor
                    ),
                    timeout=self.config.timeout_seconds,
                )
            except Exception as exc:
                raise MCPHTTPClientError(
                    "MCP HTTP tool discovery failed: "
                    f"{exc}"
                ) from exc

            for tool in response.tools:
                definitions.append(
                    MCPToolDefinition.model_validate(
                        self._model_dump(tool)
                    )
                )

            cursor = getattr(
                response,
                "next_cursor",
                None,
            )

            if cursor is None:
                break

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
                    ExternalToolTransport.MCP_HTTP
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

            result = MCPToolCallResult.model_validate(
                self._model_dump(response)
            )

            return ExternalToolResult(
                call_id=call.call_id,
                tool_id=call.tool_id,
                status=(
                    ToolExecutionStatus.FAILED
                    if result.isError
                    else ToolExecutionStatus.SUCCEEDED
                ),
                content=result.normalized_content(),
                is_error=result.isError,
                error=(
                    self._error_text(result)
                    if result.isError
                    else None
                ),
                duration_ms=(
                    time.perf_counter() - started
                )
                * 1000.0,
                metadata={
                    "server_id": self.config.server_id,
                    "remote_tool_name": tool_name,
                    "session_id": self.session_id,
                    "_meta": result.meta,
                },
            )

        except TimeoutError:
            return ExternalToolResult(
                call_id=call.call_id,
                tool_id=call.tool_id,
                status=ToolExecutionStatus.TIMED_OUT,
                is_error=True,
                error=(
                    "MCP HTTP tool execution exceeded "
                    f"{self.config.timeout_seconds} seconds."
                ),
                duration_ms=(
                    time.perf_counter() - started
                )
                * 1000.0,
                metadata={
                    "server_id": self.config.server_id,
                    "remote_tool_name": tool_name,
                    "session_id": self.session_id,
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
                    "session_id": self.session_id,
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
            raise MCPHTTPClientError(
                "MCP HTTP client is not connected."
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

        raise MCPHTTPClientError(
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
            raise MCPHTTPClientError(
                "MCP SDK returned an unsupported "
                f"response type: {type(value)!r}"
            )

        if not isinstance(payload, dict):
            raise MCPHTTPClientError(
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

        return "MCP HTTP tool returned an error result."
