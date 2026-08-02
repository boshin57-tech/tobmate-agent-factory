from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .ecosystem_models import (
    AgentToolRequirement,
    CapabilityKind,
    CompatibilityStatus,
    MCPServerManifest,
    ProjectToolBundle,
    ToolEcosystemEntry,
    ToolHealthRecord,
    ToolHealthState,
    ToolInstallationRecord,
    ToolInstallationState,
    ToolManifest,
    ToolTrustLevel,
)
from .models import ExternalToolRisk


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ToolEcosystemRegistryError(RuntimeError):
    """Raised for invalid ecosystem registry operations."""


class ToolEcosystemSearchQuery(BaseModel):
    text: str | None = None
    capability_ids: set[str] = Field(
        default_factory=set
    )
    capability_kinds: set[CapabilityKind] = Field(
        default_factory=set
    )
    operations: set[str] = Field(
        default_factory=set
    )
    required_tags: set[str] = Field(
        default_factory=set
    )
    denied_tags: set[str] = Field(
        default_factory=set
    )
    minimum_trust_level: ToolTrustLevel | None = None
    health_states: set[ToolHealthState] = Field(
        default_factory=set
    )
    installation_states: set[
        ToolInstallationState
    ] = Field(default_factory=set)
    compatibility_states: set[
        CompatibilityStatus
    ] = Field(default_factory=set)
    include_tools: bool = True
    include_servers: bool = True


class CapabilityDiscoveryResult(BaseModel):
    capability_id: str
    entries: list[ToolEcosystemEntry] = Field(
        default_factory=list
    )

    @property
    def count(self) -> int:
        return len(self.entries)


class RoleToolSelection(BaseModel):
    role: str
    selected_entries: list[
        ToolEcosystemEntry
    ] = Field(default_factory=list)
    missing_required_capabilities: set[str] = Field(
        default_factory=set
    )
    matched_optional_capabilities: set[str] = Field(
        default_factory=set
    )

    @property
    def satisfied(self) -> bool:
        return not self.missing_required_capabilities


class ToolEcosystemSnapshot(BaseModel):
    entry_count: int
    tool_count: int
    server_count: int
    bundle_count: int
    capability_count: int
    health_counts: dict[str, int] = Field(
        default_factory=dict
    )
    installation_counts: dict[str, int] = Field(
        default_factory=dict
    )
    generated_at: datetime = Field(
        default_factory=utc_now
    )


class ToolEcosystemRegistry:
    _TRUST_RANK = {
        ToolTrustLevel.UNTRUSTED: 0,
        ToolTrustLevel.COMMUNITY: 1,
        ToolTrustLevel.VERIFIED: 2,
        ToolTrustLevel.FIRST_PARTY: 3,
        ToolTrustLevel.SYSTEM: 4,
    }

    _RISK_RANK = {
        ExternalToolRisk.READ_ONLY: 0,
        ExternalToolRisk.WORKSPACE_WRITE: 1,
        ExternalToolRisk.EXTERNAL_WRITE: 2,
        ExternalToolRisk.PRIVILEGED: 3,
    }

    def __init__(self) -> None:
        self._entries: dict[
            str,
            ToolEcosystemEntry,
        ] = {}
        self._bundles: dict[
            str,
            ProjectToolBundle,
        ] = {}

    def register_tool(
        self,
        manifest: ToolManifest,
        *,
        installation: ToolInstallationRecord | None = None,
        health: ToolHealthRecord | None = None,
    ) -> ToolEcosystemEntry:
        ecosystem_id = manifest.tool_id.strip()

        if not ecosystem_id:
            raise ToolEcosystemRegistryError(
                "Tool ID is required."
            )

        entry = ToolEcosystemEntry(
            ecosystem_id=ecosystem_id,
            tool=manifest,
            installation=(
                installation
                or ToolInstallationRecord(
                    ecosystem_id=ecosystem_id
                )
            ),
            health=(
                health
                or ToolHealthRecord(
                    ecosystem_id=ecosystem_id
                )
            ),
        )

        self._register_entry(entry)
        return entry.model_copy(deep=True)

    def register_server(
        self,
        manifest: MCPServerManifest,
        *,
        installation: ToolInstallationRecord | None = None,
        health: ToolHealthRecord | None = None,
    ) -> ToolEcosystemEntry:
        ecosystem_id = manifest.server_id.strip()

        if not ecosystem_id:
            raise ToolEcosystemRegistryError(
                "Server ID is required."
            )

        entry = ToolEcosystemEntry(
            ecosystem_id=ecosystem_id,
            server=manifest,
            installation=(
                installation
                or ToolInstallationRecord(
                    ecosystem_id=ecosystem_id
                )
            ),
            health=(
                health
                or ToolHealthRecord(
                    ecosystem_id=ecosystem_id
                )
            ),
        )

        self._register_entry(entry)
        return entry.model_copy(deep=True)

    def get(
        self,
        ecosystem_id: str,
    ) -> ToolEcosystemEntry:
        try:
            return self._entries[
                ecosystem_id
            ].model_copy(deep=True)
        except KeyError as exc:
            raise ToolEcosystemRegistryError(
                "Unknown ecosystem entry: "
                f"{ecosystem_id}"
            ) from exc

    def contains(
        self,
        ecosystem_id: str,
    ) -> bool:
        return ecosystem_id in self._entries

    def list_entries(
        self,
    ) -> list[ToolEcosystemEntry]:
        return [
            self._entries[key].model_copy(
                deep=True
            )
            for key in sorted(self._entries)
        ]

    def _register_entry(
        self,
        entry: ToolEcosystemEntry,
    ) -> None:
        if entry.ecosystem_id in self._entries:
            raise ToolEcosystemRegistryError(
                "Ecosystem entry is already "
                f"registered: {entry.ecosystem_id}"
            )

        if (
            (entry.tool is None)
            == (entry.server is None)
        ):
            raise ToolEcosystemRegistryError(
                "Ecosystem entry must contain "
                "exactly one Tool or MCP server."
            )

        if (
            entry.installation.ecosystem_id
            != entry.ecosystem_id
        ):
            raise ToolEcosystemRegistryError(
                "Installation record ID does not "
                "match ecosystem entry."
            )

        if (
            entry.health.ecosystem_id
            != entry.ecosystem_id
        ):
            raise ToolEcosystemRegistryError(
                "Health record ID does not match "
                "ecosystem entry."
            )

        self._entries[
            entry.ecosystem_id
        ] = entry

    def snapshot(
        self,
    ) -> ToolEcosystemSnapshot:
        entries = list(self._entries.values())

        capability_ids = {
            capability.capability_id
            for entry in entries
            for capability in entry.capabilities
        }

        health_counts: dict[str, int] = {}
        installation_counts: dict[str, int] = {}

        for entry in entries:
            health_key = entry.health.state.value
            health_counts[health_key] = (
                health_counts.get(health_key, 0) + 1
            )

            install_key = (
                entry.installation.state.value
            )
            installation_counts[install_key] = (
                installation_counts.get(
                    install_key,
                    0,
                ) + 1
            )

        return ToolEcosystemSnapshot(
            entry_count=len(entries),
            tool_count=sum(
                entry.tool is not None
                for entry in entries
            ),
            server_count=sum(
                entry.server is not None
                for entry in entries
            ),
            bundle_count=len(self._bundles),
            capability_count=len(
                capability_ids
            ),
            health_counts=health_counts,
            installation_counts=installation_counts,
        )

    def search(
        self,
        query: ToolEcosystemSearchQuery,
    ) -> list[ToolEcosystemEntry]:
        results: list[ToolEcosystemEntry] = []

        for entry in self._entries.values():
            if (
                entry.tool is not None
                and not query.include_tools
            ):
                continue

            if (
                entry.server is not None
                and not query.include_servers
            ):
                continue

            tags = (
                set(entry.tool.tags)
                if entry.tool is not None
                else set(entry.server.tags)
            )

            capability_ids = {
                item.capability_id
                for item in entry.capabilities
            }
            kinds = {
                item.kind
                for item in entry.capabilities
            }
            operations = {
                operation
                for item in entry.capabilities
                for operation in item.operations
            }

            if (
                query.capability_ids
                and not query.capability_ids
                .issubset(capability_ids)
            ):
                continue

            if (
                query.capability_kinds
                and not query.capability_kinds
                .issubset(kinds)
            ):
                continue

            if (
                query.operations
                and not query.operations
                .issubset(operations)
            ):
                continue

            if (
                query.required_tags
                and not query.required_tags
                .issubset(tags)
            ):
                continue

            if query.denied_tags.intersection(tags):
                continue

            if (
                query.minimum_trust_level
                is not None
                and self._TRUST_RANK[
                    entry.trust_level
                ]
                < self._TRUST_RANK[
                    query.minimum_trust_level
                ]
            ):
                continue

            if (
                query.health_states
                and entry.health.state
                not in query.health_states
            ):
                continue

            if (
                query.installation_states
                and entry.installation.state
                not in query.installation_states
            ):
                continue

            compatibility = (
                entry.tool.compatibility
                if entry.tool is not None
                else entry.server.compatibility
            )

            if (
                query.compatibility_states
                and compatibility.status
                not in query.compatibility_states
            ):
                continue

            if query.text:
                needle = query.text.casefold()

                values = [
                    entry.ecosystem_id,
                    entry.name,
                    *tags,
                    *capability_ids,
                    *operations,
                ]

                if not any(
                    needle in str(value).casefold()
                    for value in values
                ):
                    continue

            results.append(
                entry.model_copy(deep=True)
            )

        return sorted(
            results,
            key=lambda item: (
                -self._TRUST_RANK[
                    item.trust_level
                ],
                item.ecosystem_id,
            ),
        )

    def discover_capability(
        self,
        capability_id: str,
        *,
        minimum_trust_level: (
            ToolTrustLevel | None
        ) = None,
        healthy_only: bool = False,
        installed_only: bool = False,
    ) -> CapabilityDiscoveryResult:
        query = ToolEcosystemSearchQuery(
            capability_ids={capability_id},
            minimum_trust_level=(
                minimum_trust_level
            ),
            health_states=(
                {ToolHealthState.HEALTHY}
                if healthy_only
                else set()
            ),
            installation_states=(
                {
                    ToolInstallationState.INSTALLED
                }
                if installed_only
                else set()
            ),
        )

        return CapabilityDiscoveryResult(
            capability_id=capability_id,
            entries=self.search(query),
        )

    def capability_index(
        self,
    ) -> dict[str, list[str]]:
        index: dict[str, list[str]] = {}

        for entry in self._entries.values():
            for capability in entry.capabilities:
                index.setdefault(
                    capability.capability_id,
                    [],
                ).append(
                    entry.ecosystem_id
                )

        return {
            capability_id: sorted(
                ecosystem_ids
            )
            for capability_id, ecosystem_ids
            in sorted(index.items())
        }

    def select_for_role(
        self,
        requirement: AgentToolRequirement,
    ) -> RoleToolSelection:
        candidates = self.search(
            ToolEcosystemSearchQuery(
                minimum_trust_level=(
                    requirement
                    .minimum_trust_level
                ),
                required_tags=(
                    requirement.required_tags
                ),
                denied_tags=(
                    requirement.denied_tags
                ),
                health_states={
                    ToolHealthState.HEALTHY,
                },
                compatibility_states={
                    CompatibilityStatus.COMPATIBLE,
                    CompatibilityStatus
                    .PARTIALLY_COMPATIBLE,
                },
            )
        )

        selected: list[
            ToolEcosystemEntry
        ] = []
        covered: set[str] = set()

        desired = (
            requirement.required_capabilities
            | requirement.optional_capabilities
        )

        for entry in candidates:
            if entry.tool is not None:
                allowed_roles = (
                    entry.tool.allowed_roles
                )

                if (
                    allowed_roles
                    and requirement.role
                    not in allowed_roles
                ):
                    continue

                if (
                    self._RISK_RANK[
                        entry.tool.risk
                    ]
                    > self._RISK_RANK[
                        requirement.maximum_risk
                    ]
                ):
                    continue

            entry_capabilities = {
                capability.capability_id
                for capability in (
                    entry.capabilities
                )
            }

            matched = desired.intersection(
                entry_capabilities
            )

            if not matched:
                continue

            selected.append(
                entry.model_copy(deep=True)
            )
            covered.update(matched)

        return RoleToolSelection(
            role=requirement.role,
            selected_entries=selected,
            missing_required_capabilities=(
                requirement.required_capabilities
                - covered
            ),
            matched_optional_capabilities=(
                requirement.optional_capabilities
                & covered
            ),
        )

    def update_installation(
        self,
        record: ToolInstallationRecord,
    ) -> ToolEcosystemEntry:
        entry = self._require_mutable(
            record.ecosystem_id
        )

        entry.installation = record
        entry.updated_at = utc_now()

        return entry.model_copy(deep=True)

    def update_health(
        self,
        record: ToolHealthRecord,
    ) -> ToolEcosystemEntry:
        entry = self._require_mutable(
            record.ecosystem_id
        )

        entry.health = record
        entry.updated_at = utc_now()

        return entry.model_copy(deep=True)

    def _require_mutable(
        self,
        ecosystem_id: str,
    ) -> ToolEcosystemEntry:
        try:
            return self._entries[
                ecosystem_id
            ]
        except KeyError as exc:
            raise ToolEcosystemRegistryError(
                "Unknown ecosystem entry: "
                f"{ecosystem_id}"
            ) from exc

    def register_bundle(
        self,
        bundle: ProjectToolBundle,
    ) -> ProjectToolBundle:
        bundle_id = bundle.bundle_id.strip()

        if not bundle_id:
            raise ToolEcosystemRegistryError(
                "Bundle ID is required."
            )

        if bundle_id in self._bundles:
            raise ToolEcosystemRegistryError(
                "Tool bundle already registered: "
                f"{bundle_id}"
            )

        self._validate_bundle(bundle)
        self._bundles[bundle_id] = bundle

        return bundle.model_copy(deep=True)

    def get_bundle(
        self,
        bundle_id: str,
    ) -> ProjectToolBundle:
        try:
            return self._bundles[
                bundle_id
            ].model_copy(deep=True)
        except KeyError as exc:
            raise ToolEcosystemRegistryError(
                f"Unknown Tool bundle: {bundle_id}"
            ) from exc

    def entries_for_bundle(
        self,
        bundle_id: str,
    ) -> list[ToolEcosystemEntry]:
        bundle = self.get_bundle(bundle_id)

        return [
            self.get(ecosystem_id)
            for ecosystem_id in [
                *bundle.tool_ids,
                *bundle.server_ids,
            ]
        ]

    def remove_bundle(
        self,
        bundle_id: str,
    ) -> ProjectToolBundle:
        try:
            bundle = self._bundles.pop(
                bundle_id
            )
        except KeyError as exc:
            raise ToolEcosystemRegistryError(
                f"Unknown Tool bundle: {bundle_id}"
            ) from exc

        return bundle.model_copy(deep=True)

    def unregister(
        self,
        ecosystem_id: str,
    ) -> ToolEcosystemEntry:
        try:
            entry = self._entries.pop(
                ecosystem_id
            )
        except KeyError as exc:
            raise ToolEcosystemRegistryError(
                "Ecosystem entry is not registered: "
                f"{ecosystem_id}"
            ) from exc

        for bundle_id, bundle in list(
            self._bundles.items()
        ):
            self._bundles[bundle_id] = (
                bundle.model_copy(
                    update={
                        "tool_ids": [
                            item
                            for item in bundle.tool_ids
                            if item != ecosystem_id
                        ],
                        "server_ids": [
                            item
                            for item in bundle.server_ids
                            if item != ecosystem_id
                        ],
                    }
                )
            )

        return entry.model_copy(deep=True)

    def _validate_bundle(
        self,
        bundle: ProjectToolBundle,
    ) -> None:
        ids = [
            *bundle.tool_ids,
            *bundle.server_ids,
        ]

        missing = [
            item
            for item in ids
            if item not in self._entries
        ]

        if missing:
            raise ToolEcosystemRegistryError(
                "Bundle references unknown entries: "
                + ", ".join(sorted(missing))
            )

        wrong_tools = [
            item
            for item in bundle.tool_ids
            if self._entries[item].tool is None
        ]

        wrong_servers = [
            item
            for item in bundle.server_ids
            if self._entries[item].server is None
        ]

        if wrong_tools:
            raise ToolEcosystemRegistryError(
                "Bundle Tool IDs reference "
                "non-Tool entries: "
                + ", ".join(sorted(wrong_tools))
            )

        if wrong_servers:
            raise ToolEcosystemRegistryError(
                "Bundle Server IDs reference "
                "non-server entries: "
                + ", ".join(sorted(wrong_servers))
            )
