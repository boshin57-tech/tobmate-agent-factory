import pytest

from af_core.orchestrator.workflow_recovery_engine import (
    WorkflowFailureKind,
    WorkflowFailureRecoveryEngine,
    WorkflowRecoveryAction,
    WorkflowRecoveryError,
    WorkflowRetryPolicy,
    WorkflowTimeoutPolicy,
)


def make_engine() -> WorkflowFailureRecoveryEngine:
    return WorkflowFailureRecoveryEngine(
        retry_policy=WorkflowRetryPolicy(
            max_attempts=3,
            initial_delay_seconds=2,
            multiplier=2,
            max_delay_seconds=5,
        ),
        timeout_policy=WorkflowTimeoutPolicy(
            timeout_seconds=10,
        ),
    )


def test_01_attempt_records_deadline() -> None:
    engine = make_engine()

    state = engine.begin_attempt(
        "workflow-1",
        "build",
        now=100,
    )

    assert state.attempts_started == 1
    assert state.active is True
    assert state.started_at == 100
    assert state.deadline_at == 110


def test_02_failure_schedules_exponential_retry() -> None:
    engine = make_engine()

    engine.begin_attempt(
        "workflow-1",
        "build",
        now=100,
    )

    first = engine.record_failure(
        "workflow-1",
        "build",
        kind=WorkflowFailureKind.DISPATCH_ERROR,
        now=101,
    )

    assert first.action is WorkflowRecoveryAction.RETRY
    assert first.next_eligible_at == 103

    engine.begin_attempt(
        "workflow-1",
        "build",
        now=103,
    )

    second = engine.record_failure(
        "workflow-1",
        "build",
        kind=WorkflowFailureKind.EXECUTION_FAILURE,
        now=104,
    )

    assert second.action is WorkflowRecoveryAction.RETRY
    assert second.next_eligible_at == 108


def test_03_backoff_blocks_early_attempt() -> None:
    engine = make_engine()

    engine.begin_attempt(
        "workflow-1",
        "build",
        now=100,
    )

    engine.record_failure(
        "workflow-1",
        "build",
        kind=WorkflowFailureKind.REJECTED,
        now=101,
    )

    assert engine.is_retry_ready(
        "workflow-1",
        "build",
        now=102,
    ) is False

    assert engine.is_retry_ready(
        "workflow-1",
        "build",
        now=103,
    ) is True

    with pytest.raises(
        WorkflowRecoveryError,
        match="retry backoff",
    ):
        engine.begin_attempt(
            "workflow-1",
            "build",
            now=102,
        )


def test_04_timeout_becomes_retryable_failure() -> None:
    engine = make_engine()

    engine.begin_attempt(
        "workflow-1",
        "test",
        now=50,
    )

    assert engine.check_timeout(
        "workflow-1",
        "test",
        now=59,
    ) is None

    decision = engine.check_timeout(
        "workflow-1",
        "test",
        now=60,
    )

    assert decision is not None
    assert decision.action is WorkflowRecoveryAction.RETRY
    assert decision.failure_kind is WorkflowFailureKind.TIMEOUT
    assert decision.next_eligible_at == 62


def test_05_maximum_attempts_become_exhausted() -> None:
    engine = make_engine()

    for attempt_time in (0, 3, 8):
        engine.begin_attempt(
            "workflow-1",
            "deploy",
            now=attempt_time,
        )

        decision = engine.record_failure(
            "workflow-1",
            "deploy",
            kind=WorkflowFailureKind.EXECUTION_FAILURE,
            now=attempt_time + 1,
        )

    assert decision.action is WorkflowRecoveryAction.EXHAUSTED
    assert decision.attempts_started == 3

    state = engine.get("workflow-1", "deploy")

    assert state.terminal is True
    assert state.succeeded is False


def test_06_non_retryable_cancel_is_terminal() -> None:
    engine = make_engine()

    engine.begin_attempt(
        "workflow-1",
        "deploy",
        now=10,
    )

    decision = engine.record_failure(
        "workflow-1",
        "deploy",
        kind=WorkflowFailureKind.CANCELLED,
        now=11,
        reason="operator cancellation",
    )

    assert decision.action is WorkflowRecoveryAction.TERMINAL
    assert engine.get(
        "workflow-1",
        "deploy",
    ).terminal is True


def test_07_success_closes_recovery_state() -> None:
    engine = make_engine()

    engine.begin_attempt(
        "workflow-1",
        "build",
        now=10,
    )

    decision = engine.record_success(
        "workflow-1",
        "build",
        now=12,
    )

    assert decision.action is WorkflowRecoveryAction.SUCCEEDED

    state = engine.get("workflow-1", "build")

    assert state.terminal is True
    assert state.succeeded is True
    assert state.active is False


def test_08_duplicate_active_attempt_is_rejected() -> None:
    engine = make_engine()

    engine.begin_attempt(
        "workflow-1",
        "build",
        now=10,
    )

    with pytest.raises(
        WorkflowRecoveryError,
        match="active attempt",
    ):
        engine.begin_attempt(
            "workflow-1",
            "build",
            now=11,
        )


def test_09_clear_workflow_preserves_other_state() -> None:
    engine = make_engine()

    engine.get("workflow-1", "build")
    engine.get("workflow-1", "test")
    engine.get("workflow-2", "deploy")

    removed = engine.clear_workflow("workflow-1")

    assert tuple(
        state.step_id for state in removed
    ) == ("build", "test")

    assert engine.get(
        "workflow-2",
        "deploy",
    ).workflow_id == "workflow-2"
