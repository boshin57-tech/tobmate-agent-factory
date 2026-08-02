from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field

from .ecosystem_models import (
    ToolInstallationState,
)
from .tool_installation_policy import (
    ToolInstallationEvaluation,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ToolLifecycleState(StrEnum):
    REQUESTED = "REQUESTED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    INSTALLING = "INSTALLING"
    INSTALLED = "INSTALLED"
    FAILED = "FAILED"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"
    QUARANTINED = "QUARANTINED"
    REVOKED = "REVOKED"
    REMOVED = "REMOVED"


class ToolApprovalDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class ToolLifecycleAction(StrEnum):
    REQUEST_INSTALL = "REQUEST_INSTALL"
    APPROVE_INSTALL = "APPROVE_INSTALL"
    REJECT_INSTALL = "REJECT_INSTALL"
    START_INSTALL = "START_INSTALL"
    COMPLETE_INSTALL = "COMPLETE_INSTALL"
    FAIL_INSTALL = "FAIL_INSTALL"
    START_ROLLBACK = "START_ROLLBACK"
    COMPLETE_ROLLBACK = "COMPLETE_ROLLBACK"
    QUARANTINE = "QUARANTINE"
    RELEASE_QUARANTINE = "RELEASE_QUARANTINE"
    REVOKE = "REVOKE"
    REMOVE = "REMOVE"


class ToolInstallationRequest(BaseModel):
    request_id: str
    ecosystem_id: str
    requested_by: str
    project_id: str | None = None
    reason: str = ""
    requested_version: str | None = None
    require_approval: bool = True
    metadata: dict[str, str] = Field(
        default_factory=dict
    )
    created_at: datetime = Field(
        default_factory=utc_now
    )


class ToolApprovalRecord(BaseModel):
    request_id: str
    ecosystem_id: str
    decision: ToolApprovalDecision
    decided_by: str
    reason: str = ""
    decided_at: datetime = Field(
        default_factory=utc_now
    )


class ToolLifecycleRecord(BaseModel):
    request_id: str
    ecosystem_id: str
    state: ToolLifecycleState
    action: ToolLifecycleAction
    actor: str | None = None
    message: str = ""
    installation_state: (
        ToolInstallationState | None
    ) = None
    policy_evaluation: (
        ToolInstallationEvaluation | None
    ) = None
    metadata: dict[str, str] = Field(
        default_factory=dict
    )
    created_at: datetime = Field(
        default_factory=utc_now
    )


class ToolInstallationCase(BaseModel):
    request: ToolInstallationRequest
    state: ToolLifecycleState
    approval: ToolApprovalRecord | None = None
    policy_evaluation: (
        ToolInstallationEvaluation | None
    ) = None
    records: list[ToolLifecycleRecord] = Field(
        default_factory=list
    )
    installed_version: str | None = None
    previous_version: str | None = None
    quarantined_reason: str | None = None
    revoked_reason: str | None = None
    error: str | None = None

    @property
    def terminal(self) -> bool:
        return self.state in {
            ToolLifecycleState.REJECTED,
            ToolLifecycleState.INSTALLED,
            ToolLifecycleState.ROLLED_BACK,
            ToolLifecycleState.QUARANTINED,
            ToolLifecycleState.REVOKED,
            ToolLifecycleState.REMOVED,
        }


class ToolLifecycleTransitionError(RuntimeError):
    """Raised when an invalid lifecycle transition is requested."""


class ToolApprovalRequiredError(RuntimeError):
    """Raised when installation begins before approval."""


class ToolQuarantinedError(RuntimeError):
    """Raised when a quarantined Tool is used or installed."""


class ToolRevokedError(RuntimeError):
    """Raised when a revoked Tool is used or reinstalled."""


class ToolInstallationLifecycleManager:
    def __init__(self) -> None:
        self._cases: dict[
            str,
            ToolInstallationCase,
        ] = {}

    def request_install(
        self,
        request: ToolInstallationRequest,
    ) -> ToolInstallationCase:
        if request.request_id in self._cases:
            raise ToolLifecycleTransitionError(
                "Installation request already exists: "
                f"{request.request_id}"
            )

        state = (
            ToolLifecycleState.PENDING_APPROVAL
            if request.require_approval
            else ToolLifecycleState.APPROVED
        )

        action = (
            ToolLifecycleAction.REQUEST_INSTALL
        )

        case = ToolInstallationCase(
            request=request,
            state=state,
            records=[
                ToolLifecycleRecord(
                    request_id=request.request_id,
                    ecosystem_id=(
                        request.ecosystem_id
                    ),
                    state=state,
                    action=action,
                    actor=request.requested_by,
                    message=(
                        "Installation request created."
                    ),
                )
            ],
        )

        self._cases[
            request.request_id
        ] = case

        return case.model_copy(deep=True)

    def approve(
        self,
        *,
        request_id: str,
        decided_by: str,
        reason: str = "",
    ) -> ToolInstallationCase:
        case = self._require_case(request_id)

        if case.state is not (
            ToolLifecycleState.PENDING_APPROVAL
        ):
            raise ToolLifecycleTransitionError(
                "Only pending requests can be approved."
            )

        approval = ToolApprovalRecord(
            request_id=request_id,
            ecosystem_id=(
                case.request.ecosystem_id
            ),
            decision=(
                ToolApprovalDecision.APPROVE
            ),
            decided_by=decided_by,
            reason=reason,
        )

        case.approval = approval
        case.state = ToolLifecycleState.APPROVED

        self._append_record(
            case,
            action=(
                ToolLifecycleAction.APPROVE_INSTALL
            ),
            state=ToolLifecycleState.APPROVED,
            actor=decided_by,
            message=reason or (
                "Installation request approved."
            ),
        )

        return case.model_copy(deep=True)

    def reject(
        self,
        *,
        request_id: str,
        decided_by: str,
        reason: str = "",
    ) -> ToolInstallationCase:
        case = self._require_case(request_id)

        if case.state is not (
            ToolLifecycleState.PENDING_APPROVAL
        ):
            raise ToolLifecycleTransitionError(
                "Only pending requests can be rejected."
            )

        approval = ToolApprovalRecord(
            request_id=request_id,
            ecosystem_id=(
                case.request.ecosystem_id
            ),
            decision=(
                ToolApprovalDecision.REJECT
            ),
            decided_by=decided_by,
            reason=reason,
        )

        case.approval = approval
        case.state = ToolLifecycleState.REJECTED

        self._append_record(
            case,
            action=(
                ToolLifecycleAction.REJECT_INSTALL
            ),
            state=ToolLifecycleState.REJECTED,
            actor=decided_by,
            message=reason or (
                "Installation request rejected."
            ),
        )

        return case.model_copy(deep=True)

    def start_install(
        self,
        *,
        request_id: str,
        actor: str,
        policy_evaluation: (
            ToolInstallationEvaluation
        ),
        previous_version: str | None = None,
    ) -> ToolInstallationCase:
        case = self._require_case(request_id)

        if case.state is (
            ToolLifecycleState.PENDING_APPROVAL
        ):
            raise ToolApprovalRequiredError(
                "Tool installation requires approval."
            )

        if case.state is (
            ToolLifecycleState.QUARANTINED
        ):
            raise ToolQuarantinedError(
                "Quarantined Tool cannot be installed."
            )

        if case.state is (
            ToolLifecycleState.REVOKED
        ):
            raise ToolRevokedError(
                "Revoked Tool cannot be installed."
            )

        if case.state is not (
            ToolLifecycleState.APPROVED
        ):
            raise ToolLifecycleTransitionError(
                "Installation can start only from "
                "APPROVED state."
            )

        if not policy_evaluation.allowed:
            raise PermissionError(
                "Tool installation policy blocked "
                "this request: "
                + "; ".join(
                    policy_evaluation.reasons
                    or ["Policy rejected the Tool."]
                )
            )

        case.policy_evaluation = (
            policy_evaluation
        )
        case.previous_version = previous_version
        case.state = ToolLifecycleState.INSTALLING

        self._append_record(
            case,
            action=(
                ToolLifecycleAction.START_INSTALL
            ),
            state=ToolLifecycleState.INSTALLING,
            actor=actor,
            message="Tool installation started.",
            installation_state=(
                ToolInstallationState.INSTALLING
            ),
            policy_evaluation=policy_evaluation,
        )

        return case.model_copy(deep=True)

    def get(
        self,
        request_id: str,
    ) -> ToolInstallationCase:
        return self._require_case(
            request_id
        ).model_copy(deep=True)

    def list_cases(
        self,
    ) -> list[ToolInstallationCase]:
        return [
            self._cases[key].model_copy(
                deep=True
            )
            for key in sorted(self._cases)
        ]

    def _require_case(
        self,
        request_id: str,
    ) -> ToolInstallationCase:
        try:
            return self._cases[request_id]
        except KeyError as exc:
            raise KeyError(
                "Unknown installation request: "
                f"{request_id}"
            ) from exc

    def _append_record(
        self,
        case: ToolInstallationCase,
        *,
        action: ToolLifecycleAction,
        state: ToolLifecycleState,
        actor: str | None = None,
        message: str = "",
        installation_state: (
            ToolInstallationState | None
        ) = None,
        policy_evaluation: (
            ToolInstallationEvaluation | None
        ) = None,
    ) -> None:
        case.records.append(
            ToolLifecycleRecord(
                request_id=(
                    case.request.request_id
                ),
                ecosystem_id=(
                    case.request.ecosystem_id
                ),
                state=state,
                action=action,
                actor=actor,
                message=message,
                installation_state=(
                    installation_state
                ),
                policy_evaluation=(
                    policy_evaluation
                ),
            )
        )

    def complete_install(
        self,
        *,
        request_id: str,
        actor: str,
        installed_version: str,
    ) -> ToolInstallationCase:
        case = self._require_case(request_id)

        if case.state is not (
            ToolLifecycleState.INSTALLING
        ):
            raise ToolLifecycleTransitionError(
                "Installation can complete only from "
                "INSTALLING state."
            )

        case.installed_version = installed_version
        case.error = None
        case.state = ToolLifecycleState.INSTALLED

        self._append_record(
            case,
            action=(
                ToolLifecycleAction.COMPLETE_INSTALL
            ),
            state=ToolLifecycleState.INSTALLED,
            actor=actor,
            message=(
                f"Tool version {installed_version} "
                "installed."
            ),
            installation_state=(
                ToolInstallationState.INSTALLED
            ),
        )

        return case.model_copy(deep=True)

    def fail_install(
        self,
        *,
        request_id: str,
        actor: str,
        error: str,
    ) -> ToolInstallationCase:
        case = self._require_case(request_id)

        if case.state is not (
            ToolLifecycleState.INSTALLING
        ):
            raise ToolLifecycleTransitionError(
                "Installation can fail only from "
                "INSTALLING state."
            )

        case.error = error
        case.state = ToolLifecycleState.FAILED

        self._append_record(
            case,
            action=ToolLifecycleAction.FAIL_INSTALL,
            state=ToolLifecycleState.FAILED,
            actor=actor,
            message=error,
            installation_state=(
                ToolInstallationState.FAILED
            ),
        )

        return case.model_copy(deep=True)

    def start_rollback(
        self,
        *,
        request_id: str,
        actor: str,
        reason: str = "",
    ) -> ToolInstallationCase:
        case = self._require_case(request_id)

        if case.state not in {
            ToolLifecycleState.FAILED,
            ToolLifecycleState.INSTALLED,
        }:
            raise ToolLifecycleTransitionError(
                "Rollback can start only from "
                "FAILED or INSTALLED state."
            )

        case.state = ToolLifecycleState.ROLLING_BACK

        self._append_record(
            case,
            action=(
                ToolLifecycleAction.START_ROLLBACK
            ),
            state=ToolLifecycleState.ROLLING_BACK,
            actor=actor,
            message=reason or "Rollback started.",
            installation_state=(
                ToolInstallationState.INSTALLING
            ),
        )

        return case.model_copy(deep=True)

    def complete_rollback(
        self,
        *,
        request_id: str,
        actor: str,
    ) -> ToolInstallationCase:
        case = self._require_case(request_id)

        if case.state is not (
            ToolLifecycleState.ROLLING_BACK
        ):
            raise ToolLifecycleTransitionError(
                "Rollback can complete only from "
                "ROLLING_BACK state."
            )

        case.installed_version = (
            case.previous_version
        )
        case.state = ToolLifecycleState.ROLLED_BACK

        installation_state = (
            ToolInstallationState.INSTALLED
            if case.previous_version
            else ToolInstallationState.REMOVED
        )

        self._append_record(
            case,
            action=(
                ToolLifecycleAction.COMPLETE_ROLLBACK
            ),
            state=ToolLifecycleState.ROLLED_BACK,
            actor=actor,
            message="Rollback completed.",
            installation_state=installation_state,
        )

        return case.model_copy(deep=True)

    def quarantine(
        self,
        *,
        request_id: str,
        actor: str,
        reason: str,
    ) -> ToolInstallationCase:
        case = self._require_case(request_id)

        if case.state in {
            ToolLifecycleState.REVOKED,
            ToolLifecycleState.REMOVED,
        }:
            raise ToolLifecycleTransitionError(
                "Revoked or removed Tool cannot be "
                "quarantined."
            )

        case.quarantined_reason = reason
        case.state = ToolLifecycleState.QUARANTINED

        self._append_record(
            case,
            action=ToolLifecycleAction.QUARANTINE,
            state=ToolLifecycleState.QUARANTINED,
            actor=actor,
            message=reason,
            installation_state=(
                ToolInstallationState.DISABLED
            ),
        )

        return case.model_copy(deep=True)

    def release_quarantine(
        self,
        *,
        request_id: str,
        actor: str,
        reason: str = "",
    ) -> ToolInstallationCase:
        case = self._require_case(request_id)

        if case.state is not (
            ToolLifecycleState.QUARANTINED
        ):
            raise ToolLifecycleTransitionError(
                "Only quarantined Tool can be released."
            )

        case.quarantined_reason = None
        case.state = (
            ToolLifecycleState.INSTALLED
            if case.installed_version
            else ToolLifecycleState.APPROVED
        )

        self._append_record(
            case,
            action=(
                ToolLifecycleAction
                .RELEASE_QUARANTINE
            ),
            state=case.state,
            actor=actor,
            message=reason or (
                "Tool released from quarantine."
            ),
            installation_state=(
                ToolInstallationState.INSTALLED
                if case.installed_version
                else ToolInstallationState
                .NOT_INSTALLED
            ),
        )

        return case.model_copy(deep=True)

    def revoke(
        self,
        *,
        request_id: str,
        actor: str,
        reason: str,
    ) -> ToolInstallationCase:
        case = self._require_case(request_id)

        if case.state is (
            ToolLifecycleState.REMOVED
        ):
            raise ToolLifecycleTransitionError(
                "Removed Tool cannot be revoked."
            )

        case.revoked_reason = reason
        case.state = ToolLifecycleState.REVOKED

        self._append_record(
            case,
            action=ToolLifecycleAction.REVOKE,
            state=ToolLifecycleState.REVOKED,
            actor=actor,
            message=reason,
            installation_state=(
                ToolInstallationState.DISABLED
            ),
        )

        return case.model_copy(deep=True)

    def remove(
        self,
        *,
        request_id: str,
        actor: str,
        reason: str = "",
    ) -> ToolInstallationCase:
        case = self._require_case(request_id)

        if case.state is (
            ToolLifecycleState.REMOVED
        ):
            raise ToolLifecycleTransitionError(
                "Tool is already removed."
            )

        case.installed_version = None
        case.state = ToolLifecycleState.REMOVED

        self._append_record(
            case,
            action=ToolLifecycleAction.REMOVE,
            state=ToolLifecycleState.REMOVED,
            actor=actor,
            message=reason or "Tool removed.",
            installation_state=(
                ToolInstallationState.REMOVED
            ),
        )

        return case.model_copy(deep=True)


from collections.abc import Awaitable, Callable

from .ecosystem_models import (
    ToolEcosystemEntry,
    ToolHealthRecord,
    ToolHealthState,
    ToolInstallationRecord,
)
from .ecosystem_registry import (
    ToolEcosystemRegistry,
)
from .tool_installation_policy import (
    ToolInstallationPolicy,
    ToolInstallationPolicyEvaluator,
)


ToolInstallHandler = Callable[
    [ToolEcosystemEntry, str | None],
    Awaitable[str],
]

ToolRollbackHandler = Callable[
    [ToolEcosystemEntry, str | None],
    Awaitable[None],
]

ToolRemoveHandler = Callable[
    [ToolEcosystemEntry],
    Awaitable[None],
]


class ToolInstallationAdapter:
    def __init__(
        self,
        *,
        install: ToolInstallHandler,
        rollback: ToolRollbackHandler,
        remove: ToolRemoveHandler | None = None,
    ) -> None:
        self.install = install
        self.rollback = rollback
        self.remove = remove


class ToolInstallationOrchestrator:
    def __init__(
        self,
        *,
        lifecycle: ToolInstallationLifecycleManager,
        ecosystem: ToolEcosystemRegistry,
        policy_evaluator: (
            ToolInstallationPolicyEvaluator
        ),
        adapter: ToolInstallationAdapter,
    ) -> None:
        self.lifecycle = lifecycle
        self.ecosystem = ecosystem
        self.policy_evaluator = policy_evaluator
        self.adapter = adapter

    async def install(
        self,
        *,
        request_id: str,
        actor: str,
        policy: ToolInstallationPolicy,
    ) -> ToolInstallationCase:
        case = self.lifecycle.get(request_id)

        entry = self.ecosystem.get(
            case.request.ecosystem_id
        )

        evaluation = (
            self.policy_evaluator.evaluate(
                entry,
                policy,
            )
        )

        self.policy_evaluator.enforce(
            evaluation
        )

        previous_version = (
            entry.installation
            .installed_version
        )

        self.lifecycle.start_install(
            request_id=request_id,
            actor=actor,
            policy_evaluation=evaluation,
            previous_version=previous_version,
        )

        self.ecosystem.update_installation(
            ToolInstallationRecord(
                ecosystem_id=entry.ecosystem_id,
                state=(
                    ToolInstallationState
                    .INSTALLING
                ),
                installed_version=previous_version,
            )
        )

        try:
            installed_version = (
                await self.adapter.install(
                    entry,
                    case.request.requested_version,
                )
            )

            self.ecosystem.update_installation(
                ToolInstallationRecord(
                    ecosystem_id=entry.ecosystem_id,
                    state=(
                        ToolInstallationState
                        .INSTALLED
                    ),
                    installed_version=(
                        installed_version
                    ),
                    installed_at=utc_now(),
                )
            )

            self.ecosystem.update_health(
                ToolHealthRecord(
                    ecosystem_id=entry.ecosystem_id,
                    state=ToolHealthState.HEALTHY,
                )
            )

            return self.lifecycle.complete_install(
                request_id=request_id,
                actor=actor,
                installed_version=installed_version,
            )

        except Exception as exc:
            self.ecosystem.update_installation(
                ToolInstallationRecord(
                    ecosystem_id=entry.ecosystem_id,
                    state=(
                        ToolInstallationState.FAILED
                    ),
                    installed_version=previous_version,
                    error=str(exc),
                )
            )

            self.ecosystem.update_health(
                ToolHealthRecord(
                    ecosystem_id=entry.ecosystem_id,
                    state=ToolHealthState.DEGRADED,
                    message=str(exc),
                )
            )

            self.lifecycle.fail_install(
                request_id=request_id,
                actor=actor,
                error=str(exc),
            )

            raise

    async def rollback(
        self,
        *,
        request_id: str,
        actor: str,
        reason: str = "",
    ) -> ToolInstallationCase:
        case = self.lifecycle.get(request_id)
        entry = self.ecosystem.get(
            case.request.ecosystem_id
        )

        self.lifecycle.start_rollback(
            request_id=request_id,
            actor=actor,
            reason=reason,
        )

        self.ecosystem.update_installation(
            ToolInstallationRecord(
                ecosystem_id=entry.ecosystem_id,
                state=(
                    ToolInstallationState
                    .INSTALLING
                ),
                installed_version=(
                    case.installed_version
                ),
            )
        )

        try:
            await self.adapter.rollback(
                entry,
                case.previous_version,
            )

            restored_state = (
                ToolInstallationState.INSTALLED
                if case.previous_version
                else ToolInstallationState.REMOVED
            )

            self.ecosystem.update_installation(
                ToolInstallationRecord(
                    ecosystem_id=entry.ecosystem_id,
                    state=restored_state,
                    installed_version=(
                        case.previous_version
                    ),
                    installed_at=(
                        utc_now()
                        if case.previous_version
                        else None
                    ),
                )
            )

            self.ecosystem.update_health(
                ToolHealthRecord(
                    ecosystem_id=entry.ecosystem_id,
                    state=(
                        ToolHealthState.HEALTHY
                        if case.previous_version
                        else ToolHealthState.UNKNOWN
                    ),
                )
            )

            return (
                self.lifecycle
                .complete_rollback(
                    request_id=request_id,
                    actor=actor,
                )
            )

        except Exception as exc:
            self.ecosystem.update_installation(
                ToolInstallationRecord(
                    ecosystem_id=entry.ecosystem_id,
                    state=ToolInstallationState.FAILED,
                    installed_version=(
                        case.installed_version
                    ),
                    error=str(exc),
                )
            )

            self.ecosystem.update_health(
                ToolHealthRecord(
                    ecosystem_id=entry.ecosystem_id,
                    state=(
                        ToolHealthState.UNAVAILABLE
                    ),
                    message=str(exc),
                )
            )

            raise

    def quarantine(
        self,
        *,
        request_id: str,
        actor: str,
        reason: str,
    ) -> ToolInstallationCase:
        case = self.lifecycle.quarantine(
            request_id=request_id,
            actor=actor,
            reason=reason,
        )

        self._disable_entry(
            case.request.ecosystem_id,
            reason=reason,
        )

        return case

    def release_quarantine(
        self,
        *,
        request_id: str,
        actor: str,
        reason: str = "",
    ) -> ToolInstallationCase:
        case = self.lifecycle.release_quarantine(
            request_id=request_id,
            actor=actor,
            reason=reason,
        )

        state = (
            ToolInstallationState.INSTALLED
            if case.installed_version
            else ToolInstallationState
            .NOT_INSTALLED
        )

        self.ecosystem.update_installation(
            ToolInstallationRecord(
                ecosystem_id=(
                    case.request.ecosystem_id
                ),
                state=state,
                installed_version=(
                    case.installed_version
                ),
            )
        )

        self.ecosystem.update_health(
            ToolHealthRecord(
                ecosystem_id=(
                    case.request.ecosystem_id
                ),
                state=(
                    ToolHealthState.HEALTHY
                    if case.installed_version
                    else ToolHealthState.UNKNOWN
                ),
            )
        )

        return case

    def revoke(
        self,
        *,
        request_id: str,
        actor: str,
        reason: str,
    ) -> ToolInstallationCase:
        case = self.lifecycle.revoke(
            request_id=request_id,
            actor=actor,
            reason=reason,
        )

        self._disable_entry(
            case.request.ecosystem_id,
            reason=reason,
        )

        return case

    async def remove(
        self,
        *,
        request_id: str,
        actor: str,
        reason: str = "",
    ) -> ToolInstallationCase:
        case = self.lifecycle.get(request_id)
        entry = self.ecosystem.get(
            case.request.ecosystem_id
        )

        if self.adapter.remove is not None:
            await self.adapter.remove(entry)

        removed = self.lifecycle.remove(
            request_id=request_id,
            actor=actor,
            reason=reason,
        )

        self.ecosystem.update_installation(
            ToolInstallationRecord(
                ecosystem_id=entry.ecosystem_id,
                state=ToolInstallationState.REMOVED,
            )
        )

        self.ecosystem.update_health(
            ToolHealthRecord(
                ecosystem_id=entry.ecosystem_id,
                state=ToolHealthState.UNAVAILABLE,
            )
        )

        return removed

    def _disable_entry(
        self,
        ecosystem_id: str,
        *,
        reason: str,
    ) -> None:
        entry = self.ecosystem.get(ecosystem_id)

        self.ecosystem.update_installation(
            ToolInstallationRecord(
                ecosystem_id=ecosystem_id,
                state=ToolInstallationState.DISABLED,
                installed_version=(
                    entry.installation
                    .installed_version
                ),
                error=reason,
            )
        )

        self.ecosystem.update_health(
            ToolHealthRecord(
                ecosystem_id=ecosystem_id,
                state=ToolHealthState.UNAVAILABLE,
                message=reason,
            )
        )
