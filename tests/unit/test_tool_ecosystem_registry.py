import pytest

from af_core.tools.ecosystem_models import (
    AgentToolRequirement,
    CapabilityKind,
    CompatibilityStatus,
    MCPServerManifest,
    ProjectToolBundle,
    ToolCapability,
    ToolCompatibility,
    ToolHealthRecord,
    ToolHealthState,
    ToolInstallationRecord,
    ToolInstallationState,
    ToolManifest,
    ToolTrustLevel,
)
from af_core.tools.ecosystem_registry import (
    ToolEcosystemRegistry,
    ToolEcosystemRegistryError,
    ToolEcosystemSearchQuery,
)
from af_core.tools.models import (
    ExternalToolRisk,
    ExternalToolTransport,
)


def capability(
    capability_id: str,
    *,
    kind: CapabilityKind = (
        CapabilityKind.FILESYSTEM
    ),
    operations: set[str] | None = None,
) -> ToolCapability:
    return ToolCapability(
        capability_id=capability_id,
        kind=kind,
        name=capability_id,
        operations=operations or set(),
    )


def tool(
    tool_id: str = "tool.fs.read",
) -> ToolManifest:
    return ToolManifest(
        tool_id=tool_id,
        name="Filesystem Reader",
        version="1.0.0",
        risk=ExternalToolRisk.READ_ONLY,
        trust_level=ToolTrustLevel.FIRST_PARTY,
        allowed_roles={"reviewer"},
        capabilities=[
            capability(
                "filesystem.read",
                operations={"read", "list"},
            )
        ],
        tags={"core", "filesystem"},
        compatibility=ToolCompatibility(
            status=CompatibilityStatus.COMPATIBLE
        ),
    )


def server() -> MCPServerManifest:
    return MCPServerManifest(
        server_id="server.fs",
        name="Filesystem MCP",
        version="1.0.0",
        transport=ExternalToolTransport.MCP_STDIO,
        trust_level=ToolTrustLevel.VERIFIED,
        capabilities=[
            capability("filesystem.read")
        ],
        compatibility=ToolCompatibility(
            status=CompatibilityStatus.COMPATIBLE
        ),
    )


def populated_registry() -> ToolEcosystemRegistry:
    registry = ToolEcosystemRegistry()

    registry.register_tool(
        tool(),
        installation=ToolInstallationRecord(
            ecosystem_id="tool.fs.read",
            state=ToolInstallationState.INSTALLED,
            installed_version="1.0.0",
        ),
        health=ToolHealthRecord(
            ecosystem_id="tool.fs.read",
            state=ToolHealthState.HEALTHY,
        ),
    )

    registry.register_server(
        server(),
        installation=ToolInstallationRecord(
            ecosystem_id="server.fs",
            state=ToolInstallationState.INSTALLED,
            installed_version="1.0.0",
        ),
        health=ToolHealthRecord(
            ecosystem_id="server.fs",
            state=ToolHealthState.HEALTHY,
        ),
    )

    return registry


def test_register_and_get_tool_and_server() -> None:
    registry = populated_registry()

    assert registry.contains("tool.fs.read")
    assert registry.contains("server.fs")

    assert registry.get(
        "tool.fs.read"
    ).tool is not None

    assert registry.get(
        "server.fs"
    ).server is not None

    assert len(registry.list_entries()) == 2


def test_duplicate_registration_is_rejected() -> None:
    registry = ToolEcosystemRegistry()
    registry.register_tool(tool())

    with pytest.raises(
        ToolEcosystemRegistryError,
        match="already registered",
    ):
        registry.register_tool(tool())


def test_unknown_entry_is_rejected() -> None:
    registry = ToolEcosystemRegistry()

    with pytest.raises(
        ToolEcosystemRegistryError,
        match="Unknown ecosystem entry",
    ):
        registry.get("missing")


def test_installation_and_health_update() -> None:
    registry = ToolEcosystemRegistry()
    registry.register_tool(tool())

    updated = registry.update_installation(
        ToolInstallationRecord(
            ecosystem_id="tool.fs.read",
            state=ToolInstallationState.INSTALLED,
            installed_version="1.0.0",
        )
    )

    assert updated.installation.state is (
        ToolInstallationState.INSTALLED
    )

    updated = registry.update_health(
        ToolHealthRecord(
            ecosystem_id="tool.fs.read",
            state=ToolHealthState.HEALTHY,
            latency_ms=12.5,
        )
    )

    assert updated.health.state is (
        ToolHealthState.HEALTHY
    )
    assert updated.health.latency_ms == 12.5


def test_search_filters_capability_trust_and_health() -> None:
    registry = populated_registry()

    results = registry.search(
        ToolEcosystemSearchQuery(
            text="filesystem",
            capability_ids={
                "filesystem.read",
            },
            capability_kinds={
                CapabilityKind.FILESYSTEM,
            },
            operations={"read"},
            required_tags={"core"},
            minimum_trust_level=(
                ToolTrustLevel.VERIFIED
            ),
            health_states={
                ToolHealthState.HEALTHY,
            },
            installation_states={
                ToolInstallationState.INSTALLED,
            },
            compatibility_states={
                CompatibilityStatus.COMPATIBLE,
            },
            include_servers=False,
        )
    )

    assert len(results) == 1
    assert results[0].ecosystem_id == (
        "tool.fs.read"
    )


def test_capability_discovery_filters_runtime_state() -> None:
    registry = populated_registry()

    discovery = registry.discover_capability(
        "filesystem.read",
        minimum_trust_level=(
            ToolTrustLevel.VERIFIED
        ),
        healthy_only=True,
        installed_only=True,
    )

    assert discovery.count == 2

    ids = {
        entry.ecosystem_id
        for entry in discovery.entries
    }

    assert ids == {
        "tool.fs.read",
        "server.fs",
    }


def test_capability_index_lists_matching_entries() -> None:
    registry = populated_registry()

    registry.register_tool(
        ToolManifest(
            tool_id="tool.code.search",
            name="Code Search",
            version="1.0.0",
            capabilities=[
                capability(
                    "filesystem.read"
                ),
                capability(
                    "code.search",
                    kind=(
                        CapabilityKind.CODE_ANALYSIS
                    ),
                    operations={"search"},
                ),
            ],
        )
    )

    index = registry.capability_index()

    assert index["filesystem.read"] == [
        "server.fs",
        "tool.code.search",
        "tool.fs.read",
    ]
    assert index["code.search"] == [
        "tool.code.search",
    ]


def test_role_selection_applies_role_risk_and_trust() -> None:
    registry = populated_registry()

    selection = registry.select_for_role(
        AgentToolRequirement(
            role="reviewer",
            required_capabilities={
                "filesystem.read",
            },
            minimum_trust_level=(
                ToolTrustLevel.VERIFIED
            ),
            maximum_risk=(
                ExternalToolRisk.READ_ONLY
            ),
        )
    )

    assert selection.satisfied is True
    assert selection.missing_required_capabilities == (
        set()
    )

    selected_ids = {
        entry.ecosystem_id
        for entry in selection.selected_entries
    }

    assert selected_ids == {
        "tool.fs.read",
        "server.fs",
    }

    missing = registry.select_for_role(
        AgentToolRequirement(
            role="tester",
            required_capabilities={
                "filesystem.read",
            },
            minimum_trust_level=(
                ToolTrustLevel.FIRST_PARTY
            ),
            maximum_risk=(
                ExternalToolRisk.READ_ONLY
            ),
        )
    )

    assert missing.satisfied is False
    assert missing.missing_required_capabilities == {
        "filesystem.read",
    }


def test_bundle_register_lookup_and_entries() -> None:
    registry = populated_registry()

    bundle = registry.register_bundle(
        ProjectToolBundle(
            bundle_id="bundle-core",
            project_id="project-1",
            name="Core Tools",
            tool_ids=["tool.fs.read"],
            server_ids=["server.fs"],
        )
    )

    assert bundle.bundle_id == "bundle-core"

    loaded = registry.get_bundle(
        "bundle-core"
    )

    assert loaded.tool_ids == [
        "tool.fs.read",
    ]
    assert loaded.server_ids == [
        "server.fs",
    ]

    entries = registry.entries_for_bundle(
        "bundle-core"
    )

    assert {
        entry.ecosystem_id
        for entry in entries
    } == {
        "tool.fs.read",
        "server.fs",
    }


def test_unregister_cleans_bundle_references() -> None:
    registry = populated_registry()

    registry.register_bundle(
        ProjectToolBundle(
            bundle_id="bundle-core",
            project_id="project-1",
            name="Core Tools",
            tool_ids=["tool.fs.read"],
            server_ids=["server.fs"],
        )
    )

    removed = registry.unregister(
        "tool.fs.read"
    )

    assert removed.ecosystem_id == (
        "tool.fs.read"
    )
    assert registry.contains(
        "tool.fs.read"
    ) is False

    bundle = registry.get_bundle(
        "bundle-core"
    )

    assert bundle.tool_ids == []
    assert bundle.server_ids == [
        "server.fs",
    ]


def test_snapshot_reports_registry_state() -> None:
    registry = populated_registry()

    registry.register_bundle(
        ProjectToolBundle(
            bundle_id="bundle-core",
            project_id="project-1",
            name="Core Tools",
            tool_ids=["tool.fs.read"],
            server_ids=["server.fs"],
        )
    )

    snapshot = registry.snapshot()

    assert snapshot.entry_count == 2
    assert snapshot.tool_count == 1
    assert snapshot.server_count == 1
    assert snapshot.bundle_count == 1
    assert snapshot.capability_count == 1

    assert snapshot.health_counts == {
        "HEALTHY": 2,
    }
    assert snapshot.installation_counts == {
        "INSTALLED": 2,
    }


def test_bundle_validation_and_missing_removal_errors() -> None:
    registry = populated_registry()

    with pytest.raises(
        ToolEcosystemRegistryError,
        match="unknown entries",
    ):
        registry.register_bundle(
            ProjectToolBundle(
                bundle_id="bundle-missing",
                project_id="project-1",
                name="Missing",
                tool_ids=["tool.missing"],
            )
        )

    with pytest.raises(
        ToolEcosystemRegistryError,
        match="non-Tool entries",
    ):
        registry.register_bundle(
            ProjectToolBundle(
                bundle_id="bundle-wrong-tool",
                project_id="project-1",
                name="Wrong Tool",
                tool_ids=["server.fs"],
            )
        )

    with pytest.raises(
        ToolEcosystemRegistryError,
        match="non-server entries",
    ):
        registry.register_bundle(
            ProjectToolBundle(
                bundle_id="bundle-wrong-server",
                project_id="project-1",
                name="Wrong Server",
                server_ids=["tool.fs.read"],
            )
        )

    with pytest.raises(
        ToolEcosystemRegistryError,
        match="not registered",
    ):
        registry.unregister(
            "missing"
        )

    with pytest.raises(
        ToolEcosystemRegistryError,
        match="Unknown Tool bundle",
    ):
        registry.remove_bundle(
            "missing-bundle"
        )
