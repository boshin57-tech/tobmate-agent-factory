from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field

from .ecosystem_models import (
    AgentToolRequirement,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ToolProvisionAction(StrEnum):
    ACTIVATE_BUNDLE = "ACTIVATE_BUNDLE"
    DEACTIVATE_BUNDLE = "DEACTIVATE_BUNDLE"
    PROVISION_ROLE = "PROVISION_ROLE"
    RELEASE_ROLE = "RELEASE_ROLE"
    SYNC_RUNTIME = "SYNC_RUNTIME"


class ToolProvisionStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    PARTIALLY_SUCCEEDED = "PARTIALLY_SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class ActiveProjectToolBundle(BaseModel):
    project_id: str
    bundle_id: str
    activated_at: datetime = Field(
        default_factory=utc_now
    )
    activated_by: str | None = None
    enabled: bool = True


class AgentToolProvisionRequest(BaseModel):
    project_id: str
    agent_id: str
    role: str
    requirement: AgentToolRequirement
    bundle_ids: list[str] = Field(
        default_factory=list
    )


class AgentToolProvisionResult(BaseModel):
    project_id: str
    agent_id: str
    role: str
    status: ToolProvisionStatus
    selected_tool_ids: list[str] = Field(
        default_factory=list
    )
    selected_server_ids: list[str] = Field(
        default_factory=list
    )
    runtime_tool_ids: list[str] = Field(
        default_factory=list
    )
    missing_required_capabilities: set[str] = Field(
        default_factory=set
    )
    warnings: list[str] = Field(
        default_factory=list
    )
    error: str | None = None

    @property
    def successful(self) -> bool:
        return self.status is ToolProvisionStatus.SUCCEEDED


class RuntimeToolBridgeRecord(BaseModel):
    project_id: str
    agent_id: str | None = None
    action: ToolProvisionAction
    added_tool_ids: list[str] = Field(
        default_factory=list
    )
    removed_tool_ids: list[str] = Field(
        default_factory=list
    )
    status: ToolProvisionStatus
    error: str | None = None
    created_at: datetime = Field(
        default_factory=utc_now
    )


class ProjectToolBundleActivationRegistry:
    def __init__(self) -> None:
        self._active: dict[
            tuple[str, str],
            ActiveProjectToolBundle,
        ] = {}
        self._records: list[
            RuntimeToolBridgeRecord
        ] = []

    def is_active(
        self,
        *,
        project_id: str,
        bundle_id: str,
    ) -> bool:
        key = (
            project_id,
            bundle_id,
        )

        value = self._active.get(key)

        return bool(
            value is not None
            and value.enabled
        )

    def get(
        self,
        *,
        project_id: str,
        bundle_id: str,
    ) -> ActiveProjectToolBundle:
        key = (
            project_id,
            bundle_id,
        )

        try:
            return self._active[
                key
            ].model_copy(deep=True)
        except KeyError as exc:
            raise KeyError(
                "Project Tool bundle is not active: "
                f"{project_id}:{bundle_id}"
            ) from exc

    def activate(
        self,
        *,
        project_id: str,
        bundle_id: str,
        activated_by: str | None = None,
    ) -> ActiveProjectToolBundle:
        key = (
            project_id,
            bundle_id,
        )

        current = self._active.get(key)

        if (
            current is not None
            and current.enabled
        ):
            return current.model_copy(
                deep=True
            )

        active = ActiveProjectToolBundle(
            project_id=project_id,
            bundle_id=bundle_id,
            activated_by=activated_by,
            enabled=True,
        )

        self._active[key] = active

        self._records.append(
            RuntimeToolBridgeRecord(
                project_id=project_id,
                action=(
                    ToolProvisionAction
                    .ACTIVATE_BUNDLE
                ),
                status=(
                    ToolProvisionStatus.SUCCEEDED
                ),
            )
        )

        return active.model_copy(deep=True)

    def deactivate(
        self,
        *,
        project_id: str,
        bundle_id: str,
    ) -> ActiveProjectToolBundle:
        key = (
            project_id,
            bundle_id,
        )

        current = self._active.get(key)

        if current is None:
            raise KeyError(
                "Project Tool bundle is not active: "
                f"{project_id}:{bundle_id}"
            )

        updated = current.model_copy(
            update={
                "enabled": False,
            }
        )

        self._active[key] = updated

        self._records.append(
            RuntimeToolBridgeRecord(
                project_id=project_id,
                action=(
                    ToolProvisionAction
                    .DEACTIVATE_BUNDLE
                ),
                status=(
                    ToolProvisionStatus.SUCCEEDED
                ),
            )
        )

        return updated.model_copy(deep=True)

    def list_active(
        self,
        *,
        project_id: str | None = None,
    ) -> list[ActiveProjectToolBundle]:
        values: list[
            ActiveProjectToolBundle
        ] = []

        for item in self._active.values():
            if not item.enabled:
                continue

            if (
                project_id is not None
                and item.project_id
                != project_id
            ):
                continue

            values.append(
                item.model_copy(deep=True)
            )

        return sorted(
            values,
            key=lambda item: (
                item.project_id,
                item.bundle_id,
            ),
        )

    def active_bundle_ids(
        self,
        project_id: str,
    ) -> list[str]:
        return [
            item.bundle_id
            for item in self.list_active(
                project_id=project_id
            )
        ]

    def records(
        self,
    ) -> list[RuntimeToolBridgeRecord]:
        return [
            item.model_copy(deep=True)
            for item in self._records
        ]

    def latest_record(
        self,
    ) -> RuntimeToolBridgeRecord | None:
        if not self._records:
            return None

        return self._records[-1].model_copy(
            deep=True
        )


from .ecosystem_models import (
    ToolEcosystemEntry,
    ToolHealthState,
    ToolInstallationState,
)
from .ecosystem_registry import (
    ToolEcosystemRegistry,
)


class AgentToolProvisioner:
    def __init__(
        self,
        *,
        ecosystem: ToolEcosystemRegistry,
        activations: (
            ProjectToolBundleActivationRegistry
        ),
    ) -> None:
        self.ecosystem = ecosystem
        self.activations = activations
        self._results: list[
            AgentToolProvisionResult
        ] = []
        self._records: list[
            RuntimeToolBridgeRecord
        ] = []

    def active_bundle_ids(
        self,
        project_id: str,
        requested_bundle_ids: (
            list[str] | None
        ) = None,
    ) -> list[str]:
        active = set(
            self.activations.active_bundle_ids(
                project_id
            )
        )

        if requested_bundle_ids:
            active.intersection_update(
                requested_bundle_ids
            )

        return sorted(active)

    def bundle_entries(
        self,
        *,
        project_id: str,
        bundle_ids: list[str] | None = None,
    ) -> list[ToolEcosystemEntry]:
        selected_ids = self.active_bundle_ids(
            project_id,
            bundle_ids,
        )

        entries: dict[
            str,
            ToolEcosystemEntry,
        ] = {}

        for bundle_id in selected_ids:
            bundle = self.ecosystem.get_bundle(
                bundle_id
            )

            if bundle.project_id != project_id:
                continue

            if not bundle.enabled:
                continue

            for entry in (
                self.ecosystem
                .entries_for_bundle(bundle_id)
            ):
                entries[
                    entry.ecosystem_id
                ] = entry

        return [
            entries[key]
            for key in sorted(entries)
        ]

    def provision(
        self,
        request: AgentToolProvisionRequest,
    ) -> AgentToolProvisionResult:
        entries = self.bundle_entries(
            project_id=request.project_id,
            bundle_ids=(
                request.bundle_ids or None
            ),
        )

        selected_tools: list[str] = []
        selected_servers: list[str] = []
        covered: set[str] = set()
        warnings: list[str] = []

        requirement = request.requirement

        for entry in entries:
            if not self._runtime_ready(entry):
                continue

            if not self._trust_allowed(
                entry,
                requirement,
            ):
                continue

            if not self._role_allowed(
                entry,
                requirement.role,
            ):
                continue

            if not self._risk_allowed(
                entry,
                requirement,
            ):
                continue

            capability_ids = {
                capability.capability_id
                for capability in entry.capabilities
            }

            desired = (
                requirement.required_capabilities
                | requirement.optional_capabilities
            )

            matched = desired.intersection(
                capability_ids
            )

            if not matched:
                continue

            covered.update(matched)

            if entry.tool is not None:
                selected_tools.append(
                    entry.ecosystem_id
                )
            elif entry.server is not None:
                selected_servers.append(
                    entry.ecosystem_id
                )

        missing = (
            requirement.required_capabilities
            - covered
        )

        if missing:
            status = ToolProvisionStatus.BLOCKED
            warnings.append(
                "Required Tool capabilities are missing: "
                + ", ".join(sorted(missing))
            )
        else:
            status = ToolProvisionStatus.SUCCEEDED

        result = AgentToolProvisionResult(
            project_id=request.project_id,
            agent_id=request.agent_id,
            role=request.role,
            status=status,
            selected_tool_ids=sorted(
                set(selected_tools)
            ),
            selected_server_ids=sorted(
                set(selected_servers)
            ),
            runtime_tool_ids=sorted(
                set(selected_tools)
            ),
            missing_required_capabilities=missing,
            warnings=warnings,
        )

        self._results.append(result)

        self._records.append(
            RuntimeToolBridgeRecord(
                project_id=request.project_id,
                agent_id=request.agent_id,
                action=(
                    ToolProvisionAction
                    .PROVISION_ROLE
                ),
                added_tool_ids=(
                    result.runtime_tool_ids
                ),
                status=result.status,
                error=(
                    "; ".join(warnings)
                    if warnings
                    else None
                ),
            )
        )

        return result.model_copy(deep=True)

    def _runtime_ready(
        self,
        entry: ToolEcosystemEntry,
    ) -> bool:
        return (
            entry.installation.state
            is ToolInstallationState.INSTALLED
            and entry.health.state
            is ToolHealthState.HEALTHY
        )

    def _role_allowed(
        self,
        entry: ToolEcosystemEntry,
        role: str,
    ) -> bool:
        if entry.tool is None:
            return True

        allowed = entry.tool.allowed_roles

        return (
            not allowed
            or role in allowed
        )

    def _trust_allowed(
        self,
        entry: ToolEcosystemEntry,
        requirement: AgentToolRequirement,
    ) -> bool:
        rank = {
            "UNTRUSTED": 0,
            "COMMUNITY": 1,
            "VERIFIED": 2,
            "FIRST_PARTY": 3,
            "SYSTEM": 4,
        }

        return (
            rank[entry.trust_level.value]
            >= rank[
                requirement
                .minimum_trust_level
                .value
            ]
        )

    def _risk_allowed(
        self,
        entry: ToolEcosystemEntry,
        requirement: AgentToolRequirement,
    ) -> bool:
        if entry.tool is None:
            return True

        rank = {
            "READ_ONLY": 0,
            "WORKSPACE_WRITE": 1,
            "EXTERNAL_WRITE": 2,
            "PRIVILEGED": 3,
        }

        return (
            rank[entry.tool.risk.value]
            <= rank[
                requirement.maximum_risk.value
            ]
        )

    def results(
        self,
    ) -> list[AgentToolProvisionResult]:
        return [
            item.model_copy(deep=True)
            for item in self._results
        ]

    def records(
        self,
    ) -> list[RuntimeToolBridgeRecord]:
        return [
            item.model_copy(deep=True)
            for item in self._records
        ]


from typing import Any

from .models import (
    ExternalToolCall,
    ExternalToolDescriptor,
    ExternalToolResult,
)
from .registry import (
    ExternalToolRegistry,
    ExternalToolRegistryError,
)


class AgentRuntimeToolView:
    def __init__(
        self,
        *,
        source: ExternalToolRegistry,
        project_id: str,
        agent_id: str,
        allowed_tool_ids: set[str],
    ) -> None:
        self.source = source
        self.project_id = project_id
        self.agent_id = agent_id
        self._allowed_tool_ids = set(
            allowed_tool_ids
        )

    def contains(
        self,
        tool_id: str,
    ) -> bool:
        return (
            tool_id in self._allowed_tool_ids
            and self._source_contains(tool_id)
        )

    def get(
        self,
        tool_id: str,
    ) -> ExternalToolDescriptor:
        self._enforce_allowed(tool_id)
        return self.source.get(tool_id)

    def allowed_tool_ids(self) -> list[str]:
        return sorted(self._allowed_tool_ids)

    def descriptors(
        self,
    ) -> list[ExternalToolDescriptor]:
        return [
            self.source.get(tool_id)
            for tool_id in self.allowed_tool_ids()
            if self._source_contains(tool_id)
        ]

    def list(
        self,
    ) -> list[ExternalToolDescriptor]:
        """Return only Tools provisioned to this Agent."""
        return self.descriptors()

    async def execute(
        self,
        call: ExternalToolCall,
        *,
        approved: bool = False,
    ) -> ExternalToolResult:
        self._enforce_allowed(call.tool_id)

        scoped_call = call.model_copy(
            update={
                "project_id": (
                    call.project_id
                    or self.project_id
                ),
                "agent_name": (
                    call.agent_name
                    or self.agent_id
                ),
            }
        )

        return await self.source.execute(
            scoped_call,
            approved=approved,
        )

    def _enforce_allowed(
        self,
        tool_id: str,
    ) -> None:
        if tool_id not in self._allowed_tool_ids:
            raise ExternalToolRegistryError(
                "Tool is not provisioned for Agent "
                f"{self.agent_id}: {tool_id}"
            )

        if not self._source_contains(tool_id):
            raise ExternalToolRegistryError(
                "Provisioned Tool is unavailable in "
                f"Runtime Registry: {tool_id}"
            )

    def _source_contains(
        self,
        tool_id: str,
    ) -> bool:
        try:
            self.source.get(tool_id)
        except ExternalToolRegistryError:
            return False

        return True


class RuntimeToolRegistryBridge:
    def __init__(
        self,
        *,
        source_registry: ExternalToolRegistry,
    ) -> None:
        self.source_registry = source_registry
        self._views: dict[
            tuple[str, str],
            AgentRuntimeToolView,
        ] = {}
        self._records: list[
            RuntimeToolBridgeRecord
        ] = []

    def provision(
        self,
        result: AgentToolProvisionResult,
    ) -> AgentRuntimeToolView:
        if result.status not in {
            ToolProvisionStatus.SUCCEEDED,
            ToolProvisionStatus.PARTIALLY_SUCCEEDED,
        }:
            raise RuntimeError(
                "Blocked or failed Tool provision "
                "result cannot enter Runtime Registry."
            )

        available: set[str] = set()
        missing: list[str] = []

        for tool_id in result.runtime_tool_ids:
            try:
                self.source_registry.get(tool_id)
            except ExternalToolRegistryError:
                missing.append(tool_id)
            else:
                available.add(tool_id)

        if missing:
            raise RuntimeError(
                "Provisioned Tool IDs are unavailable: "
                + ", ".join(sorted(missing))
            )

        key = (
            result.project_id,
            result.agent_id,
        )

        previous = self._views.get(key)
        previous_ids = (
            set(previous.allowed_tool_ids())
            if previous is not None
            else set()
        )

        view = AgentRuntimeToolView(
            source=self.source_registry,
            project_id=result.project_id,
            agent_id=result.agent_id,
            allowed_tool_ids=available,
        )

        self._views[key] = view

        self._records.append(
            RuntimeToolBridgeRecord(
                project_id=result.project_id,
                agent_id=result.agent_id,
                action=ToolProvisionAction.SYNC_RUNTIME,
                added_tool_ids=sorted(
                    available - previous_ids
                ),
                removed_tool_ids=sorted(
                    previous_ids - available
                ),
                status=ToolProvisionStatus.SUCCEEDED,
            )
        )

        return view

    def get_view(
        self,
        *,
        project_id: str,
        agent_id: str,
    ) -> AgentRuntimeToolView:
        key = (
            project_id,
            agent_id,
        )

        try:
            return self._views[key]
        except KeyError as exc:
            raise KeyError(
                "Agent Runtime Tool View does not "
                f"exist: {project_id}:{agent_id}"
            ) from exc

    def release(
        self,
        *,
        project_id: str,
        agent_id: str,
    ) -> list[str]:
        key = (
            project_id,
            agent_id,
        )

        try:
            view = self._views.pop(key)
        except KeyError as exc:
            raise KeyError(
                "Agent Runtime Tool View does not "
                f"exist: {project_id}:{agent_id}"
            ) from exc

        removed = view.allowed_tool_ids()

        self._records.append(
            RuntimeToolBridgeRecord(
                project_id=project_id,
                agent_id=agent_id,
                action=ToolProvisionAction.RELEASE_ROLE,
                removed_tool_ids=removed,
                status=ToolProvisionStatus.SUCCEEDED,
            )
        )

        return removed

    def contains_view(
        self,
        *,
        project_id: str,
        agent_id: str,
    ) -> bool:
        return (
            project_id,
            agent_id,
        ) in self._views

    def list_agent_ids(
        self,
        project_id: str,
    ) -> list[str]:
        return sorted(
            agent_id
            for (
                stored_project_id,
                agent_id,
            ) in self._views
            if stored_project_id == project_id
        )

    def records(
        self,
    ) -> list[RuntimeToolBridgeRecord]:
        return [
            item.model_copy(deep=True)
            for item in self._records
        ]

    def latest_record(
        self,
    ) -> RuntimeToolBridgeRecord | None:
        if not self._records:
            return None

        return self._records[-1].model_copy(
            deep=True
        )
