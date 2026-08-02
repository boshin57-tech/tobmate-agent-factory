from __future__ import annotations

from .execution_governance_engine import (
    ExecutionGovernanceEngine,
)
from .execution_governance_models import (
    ExecutionGovernanceRequest,
    ExecutionGovernanceResult,
    GovernanceDecision,
)
from .recovery_policy_engine import (
    RecoveryPolicyEngine,
    RecoveryPolicyRequest,
    RecoveryReason,
    RecoveryPolicyResult,
)


class GovernanceRecoveryAdapterError(
    RuntimeError
):
    pass


class GovernanceRecoveryAdapter:
    """
    Connects execution governance decisions
    with recovery policy decisions.
    """

    def __init__(
        self,
        *,
        governance_engine: (
            ExecutionGovernanceEngine
        ),
        recovery_engine: (
            RecoveryPolicyEngine
        ),
    ) -> None:
        self.governance_engine = (
            governance_engine
        )
        self.recovery_engine = (
            recovery_engine
        )

    def evaluate_execution(
        self,
        request: ExecutionGovernanceRequest,
        *,
        attempt_count: int = 0,
        maximum_attempts: int = 3,
        compensation_available: bool = False,
    ) -> tuple[
        ExecutionGovernanceResult,
        RecoveryPolicyResult | None,
    ]:

        governance = (
            self.governance_engine
            .evaluate(
                request
            )
        )

        if (
            governance.decision
            is GovernanceDecision.ALLOW
        ):
            return (
                governance,
                None,
            )

        recovery = (
            self.recovery_engine
            .evaluate(
                RecoveryPolicyRequest(
                    run_id=request.run_id,
                    step_id=request.step_id,
                    reason=(
                        RecoveryReason
                        .POLICY_DENIED
                    ),
                    attempt_count=(
                        attempt_count
                    ),
                    maximum_attempts=(
                        maximum_attempts
                    ),
                    compensation_available=(
                        compensation_available
                    ),
                )
            )
        )

        return (
            governance,
            recovery,
        )

    def evaluate_failure(
        self,
        *,
        run_id: str,
        step_id: str,
        attempt_count: int,
        maximum_attempts: int,
        compensation_available: bool,
        reason: RecoveryReason = (
            RecoveryReason
            .EXECUTION_FAILURE
        ),
    ) -> RecoveryPolicyResult:

        return (
            self.recovery_engine.evaluate(
                RecoveryPolicyRequest(
                    run_id=run_id,
                    step_id=step_id,
                    reason=reason,
                    attempt_count=(
                        attempt_count
                    ),
                    maximum_attempts=(
                        maximum_attempts
                    ),
                    compensation_available=(
                        compensation_available
                    ),
                )
            )
        )
