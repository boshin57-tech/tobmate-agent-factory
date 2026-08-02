from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field

from .ecosystem_models import (
    MCPServerManifest,
    ToolHealthRecord,
    ToolHealthState,
    ToolInstallationRecord,
    ToolInstallationState,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MCPCatalogSyncAction(StrEnum):
    CONNECT = "CONNECT"
    REFRESH = "REFRESH"
    DISCONNECT = "DISCONNECT"
    HEALTH_CHECK = "HEALTH_CHECK"


class MCPCatalogSyncRecord(BaseModel):
    server_id: str
    action: MCPCatalogSyncAction
    discovered_tool_ids: list[str] = Field(
        default_factory=list
    )
    added_tool_ids: list[str] = Field(
        default_factory=list
    )
    removed_tool_ids: list[str] = Field(
        default_factory=list
    )
    installation_state: ToolInstallationState
    health_state: ToolHealthState
    successful: bool
    error: str | None = None
    created_at: datetime = Field(
        default_factory=utc_now
    )


from .ecosystem_models import (
    CapabilityKind,
    ToolCapability,
    ToolCompatibility,
    ToolManifest,
    ToolTrustLevel,
)
from .models import (
    ExternalToolDescriptor,
    ExternalToolRisk,
)


def descriptor_to_manifest(
    descriptor: ExternalToolDescriptor,
    *,
    server_id: str,
    version: str = "discovered",
    trust_level: ToolTrustLevel = (
        ToolTrustLevel.UNTRUSTED
    ),
) -> ToolManifest:
    capability = ToolCapability(
        capability_id=(
            f"mcp.{server_id}.{descriptor.name}"
        ),
        kind=CapabilityKind.CUSTOM,
        name=descriptor.name,
        description=descriptor.description,
        operations={descriptor.name},
        tags=set(descriptor.tags),
        metadata={
            "input_schema": descriptor.input_schema,
        },
    )

    return ToolManifest(
        tool_id=descriptor.tool_id,
        name=descriptor.name,
        version=version,
        description=descriptor.description,
        server_id=server_id,
        transport=descriptor.transport,
        risk=descriptor.risk,
        trust_level=trust_level,
        capabilities=[capability],
        tags=set(descriptor.tags).union(
            {
                "mcp",
                f"mcp-server:{server_id}",
            }
        ),
        compatibility=ToolCompatibility(),
        metadata={
            "input_schema": descriptor.input_schema,
            "output_schema": descriptor.output_schema,
        },
    )


from .ecosystem_registry import (
    ToolEcosystemRegistry,
)
from .mcp_manager import MCPServerManager
from .mcp_models import MCPServerConfig


class MCPEcosystemSynchronizer:
    def __init__(
        self,
        *,
        manager: MCPServerManager,
        ecosystem: ToolEcosystemRegistry,
    ) -> None:
        self.manager = manager
        self.ecosystem = ecosystem
        self._records: list[
            MCPCatalogSyncRecord
        ] = []

    async def connect_stdio(
        self,
        *,
        manifest: MCPServerManifest,
        config: MCPServerConfig,
        default_risk: ExternalToolRisk = (
            ExternalToolRisk.READ_ONLY
        ),
        risk_by_tool: dict[
            str,
            ExternalToolRisk,
        ] | None = None,
    ) -> MCPCatalogSyncRecord:
        if manifest.server_id != config.server_id:
            raise ValueError(
                "Manifest and config server IDs "
                "must match."
            )

        self._ensure_server_entry(manifest)

        try:
            managed = await self.manager.connect_stdio(
                config=config,
                default_risk=default_risk,
                risk_by_tool=risk_by_tool,
            )

            discovered_ids = sorted(
                managed.registered_tool_ids
            )

            for tool_id in discovered_ids:
                descriptor = self.manager.registry.get(
                    tool_id
                )

                tool_manifest = descriptor_to_manifest(
                    descriptor,
                    server_id=manifest.server_id,
                    version=manifest.version,
                    trust_level=manifest.trust_level,
                )

                if self.ecosystem.contains(tool_id):
                    self.ecosystem.upsert_tool(
                        tool_manifest
                    )
                else:
                    self.ecosystem.register_tool(
                        tool_manifest,
                        installation=(
                            ToolInstallationRecord(
                                ecosystem_id=tool_id,
                                state=(
                                    ToolInstallationState
                                    .INSTALLED
                                ),
                                installed_version=(
                                    manifest.version
                                ),
                                installed_at=utc_now(),
                            )
                        ),
                        health=ToolHealthRecord(
                            ecosystem_id=tool_id,
                            state=(
                                ToolHealthState
                                .HEALTHY
                            ),
                        ),
                    )

            self._update_server_state(
                server_id=manifest.server_id,
                installation_state=(
                    ToolInstallationState.INSTALLED
                ),
                health_state=ToolHealthState.HEALTHY,
                installed_version=manifest.version,
            )

            record = MCPCatalogSyncRecord(
                server_id=manifest.server_id,
                action=MCPCatalogSyncAction.CONNECT,
                discovered_tool_ids=discovered_ids,
                added_tool_ids=discovered_ids,
                installation_state=(
                    ToolInstallationState.INSTALLED
                ),
                health_state=ToolHealthState.HEALTHY,
                successful=True,
            )

        except Exception as exc:
            self._update_server_state(
                server_id=manifest.server_id,
                installation_state=(
                    ToolInstallationState.FAILED
                ),
                health_state=(
                    ToolHealthState.UNAVAILABLE
                ),
                error=str(exc),
            )

            record = MCPCatalogSyncRecord(
                server_id=manifest.server_id,
                action=MCPCatalogSyncAction.CONNECT,
                installation_state=(
                    ToolInstallationState.FAILED
                ),
                health_state=(
                    ToolHealthState.UNAVAILABLE
                ),
                successful=False,
                error=str(exc),
            )

        self._records.append(record)
        return record.model_copy(deep=True)

    def records(
        self,
    ) -> list[MCPCatalogSyncRecord]:
        return [
            item.model_copy(deep=True)
            for item in self._records
        ]

    def latest(
        self,
    ) -> MCPCatalogSyncRecord | None:
        if not self._records:
            return None

        return self._records[-1].model_copy(
            deep=True
        )

    def _ensure_server_entry(
        self,
        manifest: MCPServerManifest,
    ) -> None:
        if self.ecosystem.contains(
            manifest.server_id
        ):
            self.ecosystem.upsert_server(
                manifest
            )
            return

        self.ecosystem.register_server(
            manifest,
            installation=ToolInstallationRecord(
                ecosystem_id=manifest.server_id,
                state=(
                    ToolInstallationState
                    .NOT_INSTALLED
                ),
            ),
            health=ToolHealthRecord(
                ecosystem_id=manifest.server_id,
                state=ToolHealthState.UNKNOWN,
            ),
        )

    def _update_server_state(
        self,
        *,
        server_id: str,
        installation_state: (
            ToolInstallationState
        ),
        health_state: ToolHealthState,
        installed_version: str | None = None,
        error: str | None = None,
    ) -> None:
        self.ecosystem.update_installation(
            ToolInstallationRecord(
                ecosystem_id=server_id,
                state=installation_state,
                installed_version=installed_version,
                installed_at=(
                    utc_now()
                    if installation_state
                    is ToolInstallationState.INSTALLED
                    else None
                ),
                error=error,
            )
        )

        self.ecosystem.update_health(
            ToolHealthRecord(
                ecosystem_id=server_id,
                state=health_state,
                message=error or "",
            )
        )

    async def refresh(
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
    ) -> MCPCatalogSyncRecord:
        server_entry = self.ecosystem.get(
            server_id
        )

        if server_entry.server is None:
            raise ValueError(
                "Ecosystem entry is not an MCP server: "
                f"{server_id}"
            )

        manifest = server_entry.server

        before = {
            entry.ecosystem_id
            for entry in self.ecosystem.list_entries()
            if (
                entry.tool is not None
                and entry.tool.server_id == server_id
            )
        }

        try:
            managed = await self.manager.refresh_tools(
                server_id,
                default_risk=default_risk,
                risk_by_tool=risk_by_tool,
            )

            discovered = set(
                managed.registered_tool_ids
            )
            added = discovered - before
            removed = before - discovered

            for tool_id in sorted(removed):
                if self.ecosystem.contains(tool_id):
                    self.ecosystem.unregister(tool_id)

            for tool_id in sorted(discovered):
                descriptor = self.manager.registry.get(
                    tool_id
                )

                tool_manifest = descriptor_to_manifest(
                    descriptor,
                    server_id=server_id,
                    version=manifest.version,
                    trust_level=manifest.trust_level,
                )

                if self.ecosystem.contains(tool_id):
                    self.ecosystem.upsert_tool(
                        tool_manifest
                    )
                else:
                    self.ecosystem.register_tool(
                        tool_manifest,
                        installation=(
                            ToolInstallationRecord(
                                ecosystem_id=tool_id,
                                state=(
                                    ToolInstallationState
                                    .INSTALLED
                                ),
                                installed_version=(
                                    manifest.version
                                ),
                                installed_at=utc_now(),
                            )
                        ),
                        health=ToolHealthRecord(
                            ecosystem_id=tool_id,
                            state=ToolHealthState.HEALTHY,
                        ),
                    )

            self._update_server_state(
                server_id=server_id,
                installation_state=(
                    ToolInstallationState.INSTALLED
                ),
                health_state=ToolHealthState.HEALTHY,
                installed_version=manifest.version,
            )

            record = MCPCatalogSyncRecord(
                server_id=server_id,
                action=MCPCatalogSyncAction.REFRESH,
                discovered_tool_ids=sorted(discovered),
                added_tool_ids=sorted(added),
                removed_tool_ids=sorted(removed),
                installation_state=(
                    ToolInstallationState.INSTALLED
                ),
                health_state=ToolHealthState.HEALTHY,
                successful=True,
            )

        except Exception as exc:
            self._update_server_state(
                server_id=server_id,
                installation_state=(
                    server_entry.installation.state
                ),
                health_state=ToolHealthState.DEGRADED,
                installed_version=(
                    server_entry
                    .installation
                    .installed_version
                ),
                error=str(exc),
            )

            record = MCPCatalogSyncRecord(
                server_id=server_id,
                action=MCPCatalogSyncAction.REFRESH,
                installation_state=(
                    server_entry.installation.state
                ),
                health_state=ToolHealthState.DEGRADED,
                successful=False,
                error=str(exc),
            )

        self._records.append(record)
        return record.model_copy(deep=True)

    async def health_check(
        self,
        server_id: str,
    ) -> MCPCatalogSyncRecord:
        entry = self.ecosystem.get(server_id)

        try:
            healthy = await self.manager.ping(
                server_id
            )

            health_state = (
                ToolHealthState.HEALTHY
                if healthy
                else ToolHealthState.DEGRADED
            )

            self.ecosystem.update_health(
                ToolHealthRecord(
                    ecosystem_id=server_id,
                    state=health_state,
                    message=(
                        ""
                        if healthy
                        else "MCP ping returned false."
                    ),
                )
            )

            for tool_entry in (
                self.ecosystem.list_entries()
            ):
                if (
                    tool_entry.tool is None
                    or tool_entry.tool.server_id
                    != server_id
                ):
                    continue

                self.ecosystem.update_health(
                    ToolHealthRecord(
                        ecosystem_id=(
                            tool_entry.ecosystem_id
                        ),
                        state=health_state,
                    )
                )

            record = MCPCatalogSyncRecord(
                server_id=server_id,
                action=(
                    MCPCatalogSyncAction
                    .HEALTH_CHECK
                ),
                discovered_tool_ids=sorted(
                    self.manager.get(
                        server_id
                    ).registered_tool_ids
                ),
                installation_state=(
                    entry.installation.state
                ),
                health_state=health_state,
                successful=healthy,
                error=(
                    None
                    if healthy
                    else "MCP ping returned false."
                ),
            )

        except Exception as exc:
            self.ecosystem.update_health(
                ToolHealthRecord(
                    ecosystem_id=server_id,
                    state=ToolHealthState.UNAVAILABLE,
                    message=str(exc),
                )
            )

            record = MCPCatalogSyncRecord(
                server_id=server_id,
                action=(
                    MCPCatalogSyncAction
                    .HEALTH_CHECK
                ),
                installation_state=(
                    entry.installation.state
                ),
                health_state=(
                    ToolHealthState.UNAVAILABLE
                ),
                successful=False,
                error=str(exc),
            )

        self._records.append(record)
        return record.model_copy(deep=True)

    async def disconnect(
        self,
        server_id: str,
    ) -> MCPCatalogSyncRecord:
        entry = self.ecosystem.get(server_id)

        tool_ids = {
            item.ecosystem_id
            for item in self.ecosystem.list_entries()
            if (
                item.tool is not None
                and item.tool.server_id == server_id
            )
        }

        try:
            await self.manager.disconnect(server_id)

            for tool_id in sorted(tool_ids):
                if self.ecosystem.contains(tool_id):
                    self.ecosystem.unregister(tool_id)

            self._update_server_state(
                server_id=server_id,
                installation_state=(
                    ToolInstallationState.REMOVED
                ),
                health_state=(
                    ToolHealthState.UNAVAILABLE
                ),
            )

            record = MCPCatalogSyncRecord(
                server_id=server_id,
                action=MCPCatalogSyncAction.DISCONNECT,
                removed_tool_ids=sorted(tool_ids),
                installation_state=(
                    ToolInstallationState.REMOVED
                ),
                health_state=(
                    ToolHealthState.UNAVAILABLE
                ),
                successful=True,
            )

        except Exception as exc:
            self._update_server_state(
                server_id=server_id,
                installation_state=(
                    entry.installation.state
                ),
                health_state=ToolHealthState.DEGRADED,
                installed_version=(
                    entry.installation.installed_version
                ),
                error=str(exc),
            )

            record = MCPCatalogSyncRecord(
                server_id=server_id,
                action=MCPCatalogSyncAction.DISCONNECT,
                installation_state=(
                    entry.installation.state
                ),
                health_state=ToolHealthState.DEGRADED,
                successful=False,
                error=str(exc),
            )

        self._records.append(record)
        return record.model_copy(deep=True)
