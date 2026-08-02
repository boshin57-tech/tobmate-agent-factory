from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class AuditEventType(StrEnum):
    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"
    POLICY_EVALUATED = "policy_evaluated"
    RECOVERY_TRIGGERED = "recovery_triggered"
    COMPLETION_VERIFIED = "completion_verified"


class CompletionState(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    REJECTED = "rejected"


class ExecutionEvidence(BaseModel):
    evidence_id: str

    run_id: str
    step_id: str

    agent_id: str | None = None

    output_hash: str | None = None

    metadata: dict[str, str] = (
        Field(default_factory=dict)
    )


class ExecutionAuditRecord(BaseModel):
    audit_id: str

    run_id: str
    step_id: str

    event_type: AuditEventType

    completion_state: CompletionState = (
        CompletionState.PENDING
    )

    message: str

    evidence: tuple[
        ExecutionEvidence,
        ...
    ] = ()

    metadata: dict[str, str] = (
        Field(default_factory=dict)
    )


class CompletionVerificationRequest(BaseModel):
    run_id: str
    step_id: str

    expected_state: CompletionState = (
        CompletionState.VERIFIED
    )

    evidence_ids: tuple[str, ...] = ()
