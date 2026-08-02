from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from .execution_governance_models import (
    ExecutionGovernanceEvent,
    ExecutionGovernanceRequest,
    ExecutionGovernanceResult,
    ExecutionGovernanceState,
    GovernanceDecision,
    RecoveryAction,
)


class ExecutionGovernanceError(RuntimeError):
    pass


class ExecutionGovernanceEngine:
    """
    Central execution governance layer.

    Responsible for deciding whether a workflow
    execution step can proceed and selecting
    recovery actions when execution is blocked.
    """

    def __init__(
        self,
        *,
        policy_engine=None,
        authority_engine=None,
    ) -> None:
        self.policy_engine = policy_engine
        self.authority_engine = authority_engine

        self._events: list[
            ExecutionGovernanceEvent
        ] = []

    def evaluate(
        self,
        request: ExecutionGovernanceRequest,
    ) -> ExecutionGovernanceResult:

        reasons: list[str] = []

        if self.policy_engine is not None:
            allowed = self.policy_engine.evaluate(
                request
            )

            if not allowed:
                return self._deny(
                    request,
                    "Execution policy denied",
                )

        if self.authority_engine is not None:
            authorized = self.authority_engine.check(
                request
            )

            if not authorized:
                return self._deny(
                    request,
                    "Authority denied",
                )

        result = ExecutionGovernanceResult(
            run_id=request.run_id,
            step_id=request.step_id,
            decision=(
                GovernanceDecision.ALLOW
            ),
            state=(
                ExecutionGovernanceState.APPROVED
            ),
            reasons=tuple(reasons),
        )

        self._record(
            result
        )

        return result

    def recover(
        self,
        result: ExecutionGovernanceResult,
    ) -> ExecutionGovernanceResult:

        updated = result.model_copy(
            update={
                "decision": (
                    GovernanceDecision.RECOVER
                ),
                "state": (
                    ExecutionGovernanceState
                    .RECOVERING
                ),
                "recovery_action": (
                    RecoveryAction
                    .RESTORE_CHECKPOINT
                ),
            }
        )

        self._record(
            updated
        )

        return updated

    def events(
        self,
    ) -> tuple[
        ExecutionGovernanceEvent,
        ...,
    ]:
        return tuple(self._events)

    def _deny(
        self,
        request: ExecutionGovernanceRequest,
        reason: str,
    ) -> ExecutionGovernanceResult:

        result = ExecutionGovernanceResult(
            run_id=request.run_id,
            step_id=request.step_id,
            decision=(
                GovernanceDecision.DENY
            ),
            state=(
                ExecutionGovernanceState
                .BLOCKED
            ),
            recovery_action=(
                RecoveryAction.RETRY
            ),
            reasons=(reason,),
        )

        self._record(
            result
        )

        return result

    def _record(
        self,
        result: ExecutionGovernanceResult,
    ) -> None:

        self._events.append(
            ExecutionGovernanceEvent(
                event_id=str(uuid4()),
                run_id=result.run_id,
                step_id=result.step_id,
                decision=result.decision,
                state=result.state,
                message="Execution governance evaluated",
            )
        )
