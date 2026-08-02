from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class GovernanceDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    PAUSE = "pause"
    RECOVER = "recover"


class RecoveryAction(StrEnum):
    NONE = "none"
    RETRY = "retry"
    COMPENSATE = "compensate"
    RESTORE_CHECKPOINT = "restore_checkpoint"


class ExecutionGovernanceState(StrEnum):
    CREATED = "created"
    EVALUATING = "evaluating"
    APPROVED = "approved"
    BLOCKED = "blocked"
    RECOVERING = "recovering"
    COMPLETED = "completed"


class ExecutionGovernanceRequest(BaseModel):
    run_id: str
    step_id: str
    agent_id: str | None = None
    capability_ids: frozenset[str] = (
        Field(default_factory=frozenset)
    )


class ExecutionGovernanceResult(BaseModel):
    run_id: str
    step_id: str

    decision: GovernanceDecision

    recovery_action: RecoveryAction = (
        RecoveryAction.NONE
    )

    state: ExecutionGovernanceState

    reasons: tuple[str, ...] = ()

    metadata: dict[str, str] = (
        Field(default_factory=dict)
    )


class ExecutionGovernanceEvent(BaseModel):
    event_id: str
    run_id: str
    step_id: str

    decision: GovernanceDecision

    state: ExecutionGovernanceState

    message: str
