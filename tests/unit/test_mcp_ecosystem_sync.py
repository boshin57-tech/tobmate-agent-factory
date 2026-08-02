from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from af_core.tools.ecosystem_models import (
    MCPServerManifest,
    ToolHealthState,
    ToolInstallationState,
    ToolTrustLevel,
)
from af_core.tools.ecosystem_registry import (
    ToolEcosystemRegistry,
)
from af_core.tools.mcp_ecosystem_sync import (
    MCPCatalogSyncAction,
    MCPEcosystemSynchronizer,
)
from af_core.tools.mcp_models import (
    MCPServerConfig,
)
from af_core.tools.models import (
    ExternalToolDescriptor,
    ExternalToolRisk,
    ExternalToolTransport,
)
from af_core.tools.registry import (
    ExternalToolRegistry,
)


@dataclass
class FakeManagedServer:
    config: MCPServerConfig
    registered_tool_ids: set[str] = field(
        default_factory=set
    )


class FakeMCPManager:
    def __init__(
        self,
        registry: ExternalToolRegistry,
    ) -> None:
        self.registry = registry
        self.managed: dict[
            str,
            FakeManagedServer,
        ] = {}
        self.discovery: dict[
            str,
            list[ExternalToolDescriptor],
        ] = {}
        self.ping_result = True
        self.disconnected: list[str] = []

    def set_discovery(
        self,
        server_id: str,
        descriptors: list[
            ExternalToolDescriptor
        ],
    ) -> None:
        self.discovery[server_id] = descriptors

    def get(
        self,
        server_id: str,
    ) -> FakeManagedServer:
        return self.managed[server_id]

    async def connect_stdio(
        self,
        *,
        config: MCPServerConfig,
        default_risk: ExternalToolRisk = (
            ExternalToolRisk.READ_ONLY
        ),
        risk_by_tool: dict[
            str,
            ExternalToolRisk,
        ] | None = None,
    ) -> FakeManagedServer:
        del default_risk, risk_by_tool

        descriptors = self.discovery.get(
            config.server_id,
            [],
        )

        managed = FakeManagedServer(
            config=config
        )

        for descriptor in descriptors:
            self.registry.register(
                descriptor=descriptor,
                handler=self._handler,
            )
            managed.registered_tool_ids.add(
                descriptor.tool_id
            )

        self.managed[config.server_id] = managed
        return managed

    async def refresh_tools(
        self,
        server_id: str,
        *,
        default_risk: ExternalToolRisk = (
            ExternalToolRisk.READ_ONLY
        ),
        risk_by_tool: dict[
            str,
            ExternalToolRisk,
        ] | None = None,
    ) -> FakeManagedServer:
        del default_risk, risk_by_tool

        managed = self.managed[server_id]

        discovered = {
            item.tool_id: item
            for item in self.discovery.get(
                server_id,
                [],
            )
        }

        stale = (
            managed.registered_tool_ids
            - set(discovered)
        )

        for tool_id in stale:
            self.registry.unregister(tool_id)
            managed.registered_tool_ids.remove(
                tool_id
            )

        new_ids = (
            set(discovered)
            - managed.registered_tool_ids
        )

        for tool_id in new_ids:
            descriptor = discovered[tool_id]

            self.registry.register(
                descriptor=descriptor,
                handler=self._handler,
            )
            managed.registered_tool_ids.add(
                tool_id
            )

        return managed

    async def ping(
        self,
        server_id: str,
    ) -> bool:
        if server_id not in self.managed:
            raise RuntimeError(
                f"Server not connected: {server_id}"
            )

        return self.ping_result

    async def disconnect(
        self,
        server_id: str,
    ) -> None:
        managed = self.managed.pop(
            server_id
        )

        for tool_id in list(
            managed.registered_tool_ids
        ):
            self.registry.unregister(tool_id)

        self.disconnected.append(server_id)

    async def _handler(self, call):
        raise NotImplementedError


def manifest() -> MCPServerManifest:
    return MCPServerManifest(
        server_id="server.fs",
        name="Filesystem MCP",
        version="1.0.0",
        transport=ExternalToolTransport.MCP_STDIO,
        trust_level=ToolTrustLevel.VERIFIED,
    )


def config() -> MCPServerConfig:
    return MCPServerConfig(
        server_id="server.fs",
        transport=ExternalToolTransport.MCP_STDIO,
        command="python",
        arguments=["fake_server.py"],
    )


def descriptor(
    tool_id: str,
    name: str,
) -> ExternalToolDescriptor:
    return ExternalToolDescriptor(
        tool_id=tool_id,
        name=name,
        description=f"Tool {name}",
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        risk=ExternalToolRisk.READ_ONLY,
        transport=ExternalToolTransport.MCP_STDIO,
        tags={"filesystem"},
    )


def test_connect_stdio_syncs_server_and_tools() -> None:
    external = ExternalToolRegistry()
    manager = FakeMCPManager(external)
    ecosystem = ToolEcosystemRegistry()

    manager.set_discovery(
        "server.fs",
        [
            descriptor(
                "mcp:server.fs:read_file",
                "read_file",
            ),
            descriptor(
                "mcp:server.fs:list_files",
                "list_files",
            ),
        ],
    )

    sync = MCPEcosystemSynchronizer(
        manager=manager,
        ecosystem=ecosystem,
    )

    record = asyncio.run(
        sync.connect_stdio(
            manifest=manifest(),
            config=config(),
        )
    )

    assert record.successful is True
    assert record.action is (
        MCPCatalogSyncAction.CONNECT
    )
    assert record.discovered_tool_ids == [
        "mcp:server.fs:list_files",
        "mcp:server.fs:read_file",
    ]
    assert record.added_tool_ids == (
        record.discovered_tool_ids
    )

    server_entry = ecosystem.get(
        "server.fs"
    )

    assert server_entry.server is not None
    assert server_entry.installation.state is (
        ToolInstallationState.INSTALLED
    )
    assert server_entry.health.state is (
        ToolHealthState.HEALTHY
    )

    for tool_id in record.discovered_tool_ids:
        entry = ecosystem.get(tool_id)

        assert entry.tool is not None
        assert entry.tool.server_id == "server.fs"
        assert entry.installation.state is (
            ToolInstallationState.INSTALLED
        )
        assert entry.health.state is (
            ToolHealthState.HEALTHY
        )

    assert sync.latest() is not None
    assert len(sync.records()) == 1


def test_refresh_adds_and_removes_discovered_tools() -> None:
    external = ExternalToolRegistry()
    manager = FakeMCPManager(external)
    ecosystem = ToolEcosystemRegistry()

    manager.set_discovery(
        "server.fs",
        [
            descriptor(
                "mcp:server.fs:read_file",
                "read_file",
            ),
            descriptor(
                "mcp:server.fs:list_files",
                "list_files",
            ),
        ],
    )

    sync = MCPEcosystemSynchronizer(
        manager=manager,
        ecosystem=ecosystem,
    )

    asyncio.run(
        sync.connect_stdio(
            manifest=manifest(),
            config=config(),
        )
    )

    manager.set_discovery(
        "server.fs",
        [
            descriptor(
                "mcp:server.fs:read_file",
                "read_file",
            ),
            descriptor(
                "mcp:server.fs:search_files",
                "search_files",
            ),
        ],
    )

    record = asyncio.run(
        sync.refresh("server.fs")
    )

    assert record.successful is True
    assert record.action is (
        MCPCatalogSyncAction.REFRESH
    )
    assert record.added_tool_ids == [
        "mcp:server.fs:search_files",
    ]
    assert record.removed_tool_ids == [
        "mcp:server.fs:list_files",
    ]

    assert ecosystem.contains(
        "mcp:server.fs:read_file"
    )
    assert ecosystem.contains(
        "mcp:server.fs:search_files"
    )
    assert ecosystem.contains(
        "mcp:server.fs:list_files"
    ) is False

    assert external.get(
        "mcp:server.fs:search_files"
    ).name == "search_files"


def test_health_check_updates_server_and_tool_health() -> None:
    external = ExternalToolRegistry()
    manager = FakeMCPManager(external)
    ecosystem = ToolEcosystemRegistry()

    manager.set_discovery(
        "server.fs",
        [
            descriptor(
                "mcp:server.fs:read_file",
                "read_file",
            ),
        ],
    )

    sync = MCPEcosystemSynchronizer(
        manager=manager,
        ecosystem=ecosystem,
    )

    asyncio.run(
        sync.connect_stdio(
            manifest=manifest(),
            config=config(),
        )
    )

    manager.ping_result = False

    record = asyncio.run(
        sync.health_check("server.fs")
    )

    assert record.successful is False
    assert record.action is (
        MCPCatalogSyncAction.HEALTH_CHECK
    )
    assert record.health_state is (
        ToolHealthState.DEGRADED
    )
    assert record.error == (
        "MCP ping returned false."
    )

    assert ecosystem.get(
        "server.fs"
    ).health.state is (
        ToolHealthState.DEGRADED
    )

    assert ecosystem.get(
        "mcp:server.fs:read_file"
    ).health.state is (
        ToolHealthState.DEGRADED
    )

    manager.ping_result = True

    healthy = asyncio.run(
        sync.health_check("server.fs")
    )

    assert healthy.successful is True
    assert healthy.health_state is (
        ToolHealthState.HEALTHY
    )


def test_disconnect_removes_tools_and_updates_server() -> None:
    external = ExternalToolRegistry()
    manager = FakeMCPManager(external)
    ecosystem = ToolEcosystemRegistry()

    manager.set_discovery(
        "server.fs",
        [
            descriptor(
                "mcp:server.fs:read_file",
                "read_file",
            ),
            descriptor(
                "mcp:server.fs:list_files",
                "list_files",
            ),
        ],
    )

    sync = MCPEcosystemSynchronizer(
        manager=manager,
        ecosystem=ecosystem,
    )

    asyncio.run(
        sync.connect_stdio(
            manifest=manifest(),
            config=config(),
        )
    )

    record = asyncio.run(
        sync.disconnect("server.fs")
    )

    assert record.successful is True
    assert record.action is (
        MCPCatalogSyncAction.DISCONNECT
    )
    assert record.removed_tool_ids == [
        "mcp:server.fs:list_files",
        "mcp:server.fs:read_file",
    ]

    assert ecosystem.contains(
        "mcp:server.fs:read_file"
    ) is False
    assert ecosystem.contains(
        "mcp:server.fs:list_files"
    ) is False

    server_entry = ecosystem.get(
        "server.fs"
    )

    assert server_entry.installation.state is (
        ToolInstallationState.REMOVED
    )
    assert server_entry.health.state is (
        ToolHealthState.UNAVAILABLE
    )

    assert manager.disconnected == [
        "server.fs",
    ]
    assert manager.managed == {}
