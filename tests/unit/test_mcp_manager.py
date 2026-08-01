import asyncio

import pytest

from af_core.tools.mcp_manager import (
    MCPServerManager,
    MCPServerManagerError,
)
from af_core.tools.mcp_models import (
    MCPServerConfig,
)
from af_core.tools.models import (
    ExternalToolCall,
    ExternalToolDescriptor,
    ExternalToolResult,
    ExternalToolRisk,
    ExternalToolTransport,
    ToolExecutionStatus,
)
from af_core.tools.registry import (
    ExternalToolRegistry,
)


class FakeMCPClient:
    def __init__(
        self,
        config,
    ) -> None:
        self.config = config
        self.connected = False
        self.closed = False
        self.tools = [
            ExternalToolDescriptor(
                tool_id=(
                    f"mcp:{config.server_id}:read_file"
                ),
                name="read_file",
                description="Read file",
                risk=ExternalToolRisk.READ_ONLY,
                transport=ExternalToolTransport.MCP_STDIO,
                server_id=config.server_id,
                tags={
                    "mcp",
                    config.server_id,
                },
            )
        ]

    async def connect(self) -> None:
        self.connected = True

    async def close(self) -> None:
        self.closed = True
        self.connected = False

    async def ping(self) -> bool:
        return self.connected

    async def tool_descriptors(
        self,
        *,
        default_risk,
        risk_by_tool=None,
    ):
        del default_risk, risk_by_tool
        return list(self.tools)

    def handler(
        self,
        *,
        remote_tool_name: str,
    ):
        async def execute(
            call: ExternalToolCall,
        ) -> ExternalToolResult:
            return ExternalToolResult(
                call_id=call.call_id,
                tool_id=call.tool_id,
                status=ToolExecutionStatus.SUCCEEDED,
                metadata={
                    "remote_tool_name": (
                        remote_tool_name
                    ),
                },
            )

        return execute


def config() -> MCPServerConfig:
    return MCPServerConfig(
        server_id="filesystem",
        transport=ExternalToolTransport.MCP_STDIO,
        command="python",
        arguments=["server.py"],
    )


def test_manager_connects_and_registers_tools(
    monkeypatch,
) -> None:
    import af_core.tools.mcp_manager as module

    monkeypatch.setattr(
        module,
        "MCPStdioClient",
        FakeMCPClient,
    )

    registry = ExternalToolRegistry()
    manager = MCPServerManager(
        registry=registry
    )

    managed = asyncio.run(
        manager.connect_stdio(
            config=config()
        )
    )

    assert manager.contains("filesystem")
    assert manager.list_server_ids() == [
        "filesystem"
    ]
    assert managed.client.connected is True
    assert managed.registered_tool_ids == {
        "mcp:filesystem:read_file"
    }
    assert registry.get(
        "mcp:filesystem:read_file"
    ).name == "read_file"

    assert asyncio.run(
        manager.ping("filesystem")
    ) is True


def test_duplicate_connection_is_rejected(
    monkeypatch,
) -> None:
    import af_core.tools.mcp_manager as module

    monkeypatch.setattr(
        module,
        "MCPStdioClient",
        FakeMCPClient,
    )

    manager = MCPServerManager(
        registry=ExternalToolRegistry()
    )

    asyncio.run(
        manager.connect_stdio(
            config=config()
        )
    )

    with pytest.raises(
        MCPServerManagerError,
        match="already connected",
    ):
        asyncio.run(
            manager.connect_stdio(
                config=config()
            )
        )


def test_refresh_adds_and_removes_tools(
    monkeypatch,
) -> None:
    import af_core.tools.mcp_manager as module

    monkeypatch.setattr(
        module,
        "MCPStdioClient",
        FakeMCPClient,
    )

    registry = ExternalToolRegistry()
    manager = MCPServerManager(
        registry=registry
    )

    managed = asyncio.run(
        manager.connect_stdio(
            config=config()
        )
    )

    managed.client.tools = [
        ExternalToolDescriptor(
            tool_id="mcp:filesystem:write_file",
            name="write_file",
            description="Write file",
            risk=ExternalToolRisk.WORKSPACE_WRITE,
            transport=ExternalToolTransport.MCP_STDIO,
            server_id="filesystem",
            tags={
                "mcp",
                "filesystem",
            },
        )
    ]

    asyncio.run(
        manager.refresh_tools(
            "filesystem"
        )
    )

    with pytest.raises(Exception):
        registry.get(
            "mcp:filesystem:read_file"
        )

    assert registry.get(
        "mcp:filesystem:write_file"
    ).name == "write_file"

    assert managed.registered_tool_ids == {
        "mcp:filesystem:write_file"
    }


def test_disconnect_unregisters_and_closes(
    monkeypatch,
) -> None:
    import af_core.tools.mcp_manager as module

    monkeypatch.setattr(
        module,
        "MCPStdioClient",
        FakeMCPClient,
    )

    registry = ExternalToolRegistry()
    manager = MCPServerManager(
        registry=registry
    )

    managed = asyncio.run(
        manager.connect_stdio(
            config=config()
        )
    )

    asyncio.run(
        manager.disconnect(
            "filesystem"
        )
    )

    assert manager.contains(
        "filesystem"
    ) is False
    assert managed.client.closed is True

    with pytest.raises(Exception):
        registry.get(
            "mcp:filesystem:read_file"
        )


def test_close_all_handles_multiple_servers(
    monkeypatch,
) -> None:
    import af_core.tools.mcp_manager as module

    monkeypatch.setattr(
        module,
        "MCPStdioClient",
        FakeMCPClient,
    )

    registry = ExternalToolRegistry()
    manager = MCPServerManager(
        registry=registry
    )

    first = config()
    second = first.model_copy(
        update={
            "server_id": "git",
        }
    )

    asyncio.run(
        manager.connect_stdio(
            config=first
        )
    )
    asyncio.run(
        manager.connect_stdio(
            config=second
        )
    )

    asyncio.run(
        manager.close_all()
    )

    assert manager.list_server_ids() == []
    assert registry.list() == []
