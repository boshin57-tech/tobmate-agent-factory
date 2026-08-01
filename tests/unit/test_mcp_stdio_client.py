import asyncio

import pytest

from af_core.tools.mcp_models import (
    MCPServerConfig,
    MCPToolCallResult,
    MCPToolDefinition,
)
from af_core.tools.mcp_stdio_client import (
    MCPClientError,
    MCPStdioClient,
)
from af_core.tools.models import (
    ExternalToolCall,
    ExternalToolRisk,
    ExternalToolTransport,
    ToolExecutionStatus,
)


def config() -> MCPServerConfig:
    return MCPServerConfig(
        server_id="filesystem",
        transport=ExternalToolTransport.MCP_STDIO,
        command="python",
        arguments=["server.py"],
        timeout_seconds=1,
    )


def test_client_requires_stdio_transport_and_command() -> None:
    with pytest.raises(
        ValueError,
        match="MCP_STDIO",
    ):
        MCPStdioClient(
            MCPServerConfig(
                server_id="remote",
                transport=ExternalToolTransport.MCP_HTTP,
                url="https://example.invalid/mcp",
            )
        )

    with pytest.raises(
        ValueError,
        match="command is required",
    ):
        MCPStdioClient(
            MCPServerConfig(
                server_id="missing-command",
                transport=ExternalToolTransport.MCP_STDIO,
            )
        )


def test_disconnected_client_rejects_operations() -> None:
    client = MCPStdioClient(config())

    assert client.connected is False

    with pytest.raises(
        MCPClientError,
        match="not connected",
    ):
        asyncio.run(client.ping())

    with pytest.raises(
        MCPClientError,
        match="not connected",
    ):
        asyncio.run(client.list_tools())


def test_remote_tool_name_resolution() -> None:
    client = MCPStdioClient(config())

    assert client._remote_tool_name(
        "mcp:filesystem:read_file"
    ) == "read_file"

    with pytest.raises(
        MCPClientError,
        match="Unable to resolve",
    ):
        client._remote_tool_name(
            "mcp:other:read_file"
        )


def test_tool_descriptors_use_risk_overrides(
    monkeypatch,
) -> None:
    client = MCPStdioClient(config())

    async def fake_list_tools():
        return [
            MCPToolDefinition(
                name="read_file",
                description="Read file",
            ),
            MCPToolDefinition(
                name="write_file",
                description="Write file",
            ),
        ]

    monkeypatch.setattr(
        client,
        "list_tools",
        fake_list_tools,
    )

    descriptors = asyncio.run(
        client.tool_descriptors(
            default_risk=ExternalToolRisk.READ_ONLY,
            risk_by_tool={
                "write_file": (
                    ExternalToolRisk.WORKSPACE_WRITE
                ),
            },
        )
    )

    by_name = {
        item.name: item
        for item in descriptors
    }

    assert (
        by_name["read_file"].risk
        is ExternalToolRisk.READ_ONLY
    )
    assert (
        by_name["write_file"].risk
        is ExternalToolRisk.WORKSPACE_WRITE
    )
    assert (
        by_name["write_file"].tool_id
        == "mcp:filesystem:write_file"
    )


def test_error_text_uses_normalized_text() -> None:
    client = MCPStdioClient(config())

    result = MCPToolCallResult(
        content=[
            {
                "type": "text",
                "text": "remote failure",
            }
        ],
        isError=True,
    )

    assert client._error_text(result) == (
        "remote failure"
    )


def test_handler_passes_remote_tool_name(
    monkeypatch,
) -> None:
    client = MCPStdioClient(config())
    captured = {}

    async def fake_call_tool(
        call,
        *,
        remote_tool_name=None,
    ):
        captured["call"] = call
        captured["remote_tool_name"] = (
            remote_tool_name
        )

        from af_core.tools.models import (
            ExternalToolResult,
        )

        return ExternalToolResult(
            call_id=call.call_id,
            tool_id=call.tool_id,
            status=ToolExecutionStatus.SUCCEEDED,
        )

    monkeypatch.setattr(
        client,
        "call_tool",
        fake_call_tool,
    )

    handler = client.handler(
        remote_tool_name="read_file"
    )

    call = ExternalToolCall(
        call_id="call-1",
        tool_id="mcp:filesystem:read_file",
        arguments={
            "path": "README.md",
        },
    )

    result = asyncio.run(
        handler(call)
    )

    assert (
        result.status
        is ToolExecutionStatus.SUCCEEDED
    )
    assert (
        captured["remote_tool_name"]
        == "read_file"
    )
    assert captured["call"] == call
