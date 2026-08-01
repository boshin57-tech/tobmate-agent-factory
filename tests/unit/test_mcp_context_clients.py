from af_core.tools.mcp_http_client import (
    MCPHTTPClient,
)
from af_core.tools.mcp_models import (
    MCPServerConfig,
)
from af_core.tools.mcp_stdio_client import (
    MCPStdioClient,
)
from af_core.tools.models import (
    ExternalToolTransport,
)


def stdio():
    return MCPServerConfig(
        server_id="stdio",
        transport=ExternalToolTransport.MCP_STDIO,
        command="python",
    )


def http():
    return MCPServerConfig(
        server_id="http",
        transport=ExternalToolTransport.MCP_HTTP,
        url="https://example.invalid/mcp",
    )


def test_stdio_context_methods():
    client = MCPStdioClient(stdio())

    assert callable(client.context_operations)
    assert callable(client.discover_context)
    assert callable(client.list_resources)
    assert callable(client.list_resource_templates)
    assert callable(client.read_resource)
    assert callable(client.list_prompts)
    assert callable(client.get_prompt)


def test_http_context_methods():
    client = MCPHTTPClient(http())

    assert callable(client.context_operations)
    assert callable(client.discover_context)
    assert callable(client.list_resources)
    assert callable(client.list_resource_templates)
    assert callable(client.read_resource)
    assert callable(client.list_prompts)
    assert callable(client.get_prompt)
