from af_core.tools.mcp_models import (
    MCPServerConfig,
    MCPToolCallResult,
    MCPToolDefinition,
)
from af_core.tools.models import (
    ExternalToolRisk,
    ExternalToolTransport,
    ToolContentType,
)


def test_tool_definition_conversion() -> None:
    tool = MCPToolDefinition(
        name="read_file",
        title="Read file",
        description="Read a file",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                }
            },
            "required": ["path"],
        },
        outputSchema={
            "type": "object",
        },
        annotations={
            "readOnlyHint": True,
        },
        _meta={
            "vendor": "test",
        },
    )

    descriptor = tool.to_external_descriptor(
        server_id="filesystem",
        risk=ExternalToolRisk.READ_ONLY,
        transport=ExternalToolTransport.MCP_STDIO,
    )

    assert descriptor.tool_id == (
        "mcp:filesystem:read_file"
    )
    assert descriptor.server_id == "filesystem"
    assert descriptor.transport is (
        ExternalToolTransport.MCP_STDIO
    )
    assert descriptor.input_schema["required"] == [
        "path"
    ]
    assert descriptor.tags == {
        "mcp",
        "filesystem",
    }


def test_result_content_normalization() -> None:
    result = MCPToolCallResult(
        content=[
            {
                "type": "text",
                "text": "completed",
            },
            {
                "type": "resource_link",
                "uri": "file:///workspace/report.txt",
                "name": "report",
                "mimeType": "text/plain",
            },
            {
                "type": "image",
                "data": "base64-data",
                "mimeType": "image/png",
            },
        ],
        structuredContent={
            "success": True,
        },
        isError=False,
        _meta={
            "request": "mcp-1",
        },
    )

    content = result.normalized_content()

    assert [
        item.type
        for item in content
    ] == [
        ToolContentType.TEXT,
        ToolContentType.RESOURCE,
        ToolContentType.IMAGE,
        ToolContentType.JSON,
    ]

    assert content[0].text == "completed"
    assert content[1].uri == (
        "file:///workspace/report.txt"
    )
    assert content[2].metadata["data"] == (
        "base64-data"
    )
    assert content[3].json_value == {
        "success": True,
    }


def test_server_config_supports_transports() -> None:
    stdio = MCPServerConfig(
        server_id="filesystem",
        transport=ExternalToolTransport.MCP_STDIO,
        command="python",
        arguments=["server.py"],
        environment={
            "MODE": "test",
        },
    )

    http = MCPServerConfig(
        server_id="remote",
        transport=ExternalToolTransport.MCP_HTTP,
        url="https://example.invalid/mcp",
        headers={
            "Authorization": "Bearer token",
        },
    )

    assert stdio.command == "python"
    assert stdio.arguments == ["server.py"]
    assert http.url == "https://example.invalid/mcp"
