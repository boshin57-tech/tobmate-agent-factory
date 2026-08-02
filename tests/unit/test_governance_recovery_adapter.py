from __future__ import annotations

from af_core.orchestrator.execution_governance_engine import (
    ExecutionGovernanceEngine,
)

from af_core.orchestrator.execution_governance_models import (
    ExecutionGovernanceRequest,
    GovernanceDecision,
)

from af_core.orchestrator.governance_recovery_adapter import (
    GovernanceRecoveryAdapter,
)

from af_core.orchestrator.recovery_policy_engine import (
    RecoveryPolicyEngine,
    RecoveryDecision,
    RecoveryPolicyRequest,
    RecoveryReason,
)


class AllowPolicy:

    def evaluate(self, request):
        return True


class DenyPolicy:

    def evaluate(self, request):
        return False


def test_governance_allow_without_recovery():

    adapter = GovernanceRecoveryAdapter(
        governance_engine=(
            ExecutionGovernanceEngine(
                policy_engine=AllowPolicy()
            )
        ),
        recovery_engine=RecoveryPolicyEngine(),
    )

    governance, recovery = (
        adapter.evaluate_execution(
            ExecutionGovernanceRequest(
                run_id="run-1",
                step_id="step-1",
            )
        )
    )

    assert governance.decision is (
        GovernanceDecision.ALLOW
    )

    assert recovery is None


def test_governance_deny_triggers_recovery():

    adapter = GovernanceRecoveryAdapter(
        governance_engine=(
            ExecutionGovernanceEngine(
                policy_engine=DenyPolicy()
            )
        ),
        recovery_engine=RecoveryPolicyEngine(),
    )

    governance, recovery = (
        adapter.evaluate_execution(
            ExecutionGovernanceRequest(
                run_id="run-2",
                step_id="step-2",
            )
        )
    )

    assert governance.decision is (
        GovernanceDecision.DENY
    )

    assert recovery is not None

    assert recovery.decision is (
        RecoveryDecision.RETRY
    )


def test_retry_policy_when_attempt_available():

    engine = RecoveryPolicyEngine()

    result = engine.evaluate(
        RecoveryPolicyRequest(
            run_id="run-3",
            step_id="step-3",
            reason=(
                RecoveryReason
                .EXECUTION_FAILURE
            ),
            attempt_count=1,
            maximum_attempts=3,
        )
    )

    assert result.decision is (
        RecoveryDecision.RETRY
    )


def test_compensation_policy_after_retry_limit():

    engine = RecoveryPolicyEngine()

    result = engine.evaluate(
        RecoveryPolicyRequest(
            run_id="run-4",
            step_id="step-4",
            reason=(
                RecoveryReason
                .EXECUTION_FAILURE
            ),
            attempt_count=3,
            maximum_attempts=3,
            compensation_available=True,
        )
    )

    assert result.decision is (
        RecoveryDecision.COMPENSATE
    )


def test_checkpoint_restore_when_no_compensation():

    engine = RecoveryPolicyEngine()

    result = engine.evaluate(
        RecoveryPolicyRequest(
            run_id="run-5",
            step_id="step-5",
            reason=(
                RecoveryReason
                .EXECUTION_FAILURE
            ),
            attempt_count=3,
            maximum_attempts=3,
            compensation_available=False,
        )
    )

    assert result.decision is (
        RecoveryDecision.RESTORE_CHECKPOINT
    )


def test_recovery_history_recorded():

    engine = RecoveryPolicyEngine()

    engine.evaluate(
        RecoveryPolicyRequest(
            run_id="run-6",
            step_id="step-6",
            reason=(
                RecoveryReason.TIMEOUT
            ),
        )
    )

    assert len(
        engine.history()
    ) == 1


def test_governance_event_history():

    engine = ExecutionGovernanceEngine(
        policy_engine=AllowPolicy()
    )

    engine.evaluate(
        ExecutionGovernanceRequest(
            run_id="run-7",
            step_id="step-7",
        )
    )

    assert len(
        engine.events()
    ) == 1
