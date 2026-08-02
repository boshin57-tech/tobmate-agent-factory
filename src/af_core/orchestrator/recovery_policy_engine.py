from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class RecoveryReason(StrEnum):
    EXECUTION_FAILURE = "execution_failure"
    POLICY_DENIED = "policy_denied"
    AUTHORITY_FAILURE = "authority_failure"
    TIMEOUT = "timeout"
    RESOURCE_FAILURE = "resource_failure"


class RecoveryDecision(StrEnum):
    RETRY = "retry"
    COMPENSATE = "compensate"
    RESTORE_CHECKPOINT = "restore_checkpoint"
    ESCALATE = "escalate"
    STOP = "stop"


class RecoveryPolicyRequest(BaseModel):
    run_id: str
    step_id: str

    reason: RecoveryReason

    attempt_count: int = Field(
        default=0,
        ge=0,
    )

    maximum_attempts: int = Field(
        default=3,
        ge=1,
    )

    compensation_available: bool = False


class RecoveryPolicyResult(BaseModel):
    run_id: str
    step_id: str

    decision: RecoveryDecision

    reason: RecoveryReason

    message: str


class RecoveryPolicyEngine:

    def __init__(
        self,
        *,
        retry_limit: int = 3,
    ) -> None:
        self.retry_limit = retry_limit

        self._history: list[
            RecoveryPolicyResult
        ] = []

    def evaluate(
        self,
        request: RecoveryPolicyRequest,
    ) -> RecoveryPolicyResult:

        if (
            request.attempt_count
            < request.maximum_attempts
            and request.attempt_count
            < self.retry_limit
        ):
            return self._record(
                RecoveryPolicyResult(
                    run_id=request.run_id,
                    step_id=request.step_id,
                    decision=RecoveryDecision.RETRY,
                    reason=request.reason,
                    message=(
                        "Retry permitted by policy"
                    ),
                )
            )

        if request.compensation_available:
            return self._record(
                RecoveryPolicyResult(
                    run_id=request.run_id,
                    step_id=request.step_id,
                    decision=RecoveryDecision.COMPENSATE,
                    reason=request.reason,
                    message=(
                        "Compensation required"
                    ),
                )
            )

        return self._record(
            RecoveryPolicyResult(
                run_id=request.run_id,
                step_id=request.step_id,
                decision=(
                    RecoveryDecision
                    .RESTORE_CHECKPOINT
                ),
                reason=request.reason,
                message=(
                    "Checkpoint restoration required"
                ),
            )
        )

    def history(
        self,
    ) -> tuple[RecoveryPolicyResult, ...]:
        return tuple(self._history)

    def _record(
        self,
        result: RecoveryPolicyResult,
    ) -> RecoveryPolicyResult:

        self._history.append(result)

        return result
