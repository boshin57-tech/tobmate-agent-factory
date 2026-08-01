from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Sequence
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

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
    def __init__(
        self,
        config: MCPServerConfig,
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
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._initialized = False

    @property
    def connected(self) -> bool:
        return (
            self._session is not None
            and self._initialized
        )

    async def connect(self) -> None:
        if self.connected:
            return

        environment = {
            **os.environ,
            **self.config.environment,
        }

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

            raise MCPClientError(
                "Unable to initialize MCP stdio server "
                f"{self.config.server_id}: {exc}"
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
