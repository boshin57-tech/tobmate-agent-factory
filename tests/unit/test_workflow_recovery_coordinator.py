from af_core.orchestrator.workflow_dispatch_coordinator import (
    WorkflowDispatchCoordinator,
    WorkflowDispatchRequest,
)
from af_core.orchestrator.workflow_recovery_coordinator import (
    WorkflowRecoveryCoordinator,
)
from af_core.orchestrator.workflow_recovery_engine import (
    WorkflowFailureRecoveryEngine,
    WorkflowRecoveryAction,
    WorkflowRetryPolicy,
    WorkflowTimeoutPolicy,
)
from af_core.orchestrator.workflow_trigger_engine import (
    WorkflowTriggerActivation,
    WorkflowTriggerKind,
)


def activation(
    step_id: str,
    *,
    priority: int = 100,
) -> WorkflowTriggerActivation:
    return WorkflowTriggerActivation(
        workflow_id="workflow-1",
        trigger_id=f"trigger:{step_id}",
        target_step_id=step_id,
        kind=WorkflowTriggerKind.DEPENDENCY_READY,
        event_identity=f"event:{step_id}",
        priority=priority,
    )


def make_coordinator(
    *,
    max_attempts: int = 3,
    delay: float = 2,
    timeout: float = 5,
) -> WorkflowRecoveryCoordinator:
    dispatch = WorkflowDispatchCoordinator()

    recovery = WorkflowFailureRecoveryEngine(
        retry_policy=WorkflowRetryPolicy(
            max_attempts=max_attempts,
            initial_delay_seconds=delay,
            multiplier=2,
            max_delay_seconds=10,
        ),
        timeout_policy=WorkflowTimeoutPolicy(
            timeout_seconds=timeout,
        ),
    )

    return WorkflowRecoveryCoordinator(
        dispatch,
        recovery,
    )


class AcceptedLifecycle:
    def __init__(self) -> None:
        self.requests: list[WorkflowDispatchRequest] = []

    def dispatch(
        self,
        request: WorkflowDispatchRequest,
    ) -> bool:
        self.requests.append(request)
        return True


class RejectedLifecycle:
    def __init__(self) -> None:
        self.requests: list[WorkflowDispatchRequest] = []

    def dispatch(
        self,
        request: WorkflowDispatchRequest,
    ) -> bool:
        self.requests.append(request)
        return False


class FailedLifecycle:
    def dispatch(
        self,
        request: WorkflowDispatchRequest,
    ) -> bool:
        raise RuntimeError("dispatcher unavailable")


def test_01_accepted_dispatch_becomes_inflight() -> None:
    coordinator = make_coordinator()
    lifecycle = AcceptedLifecycle()

    coordinator.dispatch_coordinator.enqueue_activations(
        (activation("build", priority=10),)
    )

    cycle = coordinator.dispatch_ready(
        lifecycle,
        now=100,
        limit=1,
    )

    assert cycle.accepted_count == 1
    assert len(coordinator.inflight()) == 1
    assert coordinator.inflight()[0].step_id == "build"
    assert len(coordinator.dispatch_coordinator.scheduler) == 0

    state = coordinator.recovery_engine.get(
        "workflow-1",
        "build",
    )

    assert state.active is True
    assert state.attempts_started == 1
    assert state.deadline_at == 105


def test_02_rejected_dispatch_obeys_backoff() -> None:
    coordinator = make_coordinator(delay=2)
    rejected = RejectedLifecycle()

    coordinator.dispatch_coordinator.enqueue_activations(
        (activation("deploy"),)
    )

    first = coordinator.dispatch_ready(
        rejected,
        now=100,
        limit=1,
    )

    assert first.rejected_count == 1
    assert len(coordinator.dispatch_coordinator.scheduler) == 1

    blocked = coordinator.dispatch_ready(
        rejected,
        now=101,
        limit=1,
    )

    assert blocked.outcomes == ()
    assert len(rejected.requests) == 1

    accepted = AcceptedLifecycle()

    second = coordinator.dispatch_ready(
        accepted,
        now=102,
        limit=1,
    )

    assert second.accepted_count == 1
    assert len(accepted.requests) == 1

    state = coordinator.recovery_engine.get(
        "workflow-1",
        "deploy",
    )

    assert state.attempts_started == 2
    assert state.active is True


def test_03_execution_failure_releases_retry() -> None:
    coordinator = make_coordinator(delay=2)
    lifecycle = AcceptedLifecycle()

    coordinator.dispatch_coordinator.enqueue_activations(
        (activation("test"),)
    )

    coordinator.dispatch_ready(
        lifecycle,
        now=100,
        limit=1,
    )

    decision = coordinator.record_execution_failure(
        "workflow-1",
        "test",
        now=101,
        reason="tests failed",
    )

    assert decision.action is WorkflowRecoveryAction.RETRY
    assert len(coordinator.inflight()) == 0
    assert len(coordinator.waiting_retries()) == 1

    assert coordinator.release_ready_retries(
        now=102,
    ) == ()

    released = coordinator.release_ready_retries(
        now=103,
    )

    assert len(released) == 1
    assert released[0].step_id == "test"
    assert released[0].metadata["retry_attempt"] == 2


def test_04_timeout_releases_retry_after_backoff() -> None:
    coordinator = make_coordinator(
        delay=2,
        timeout=5,
    )

    coordinator.dispatch_coordinator.enqueue_activations(
        (activation("long-task"),)
    )

    coordinator.dispatch_ready(
        AcceptedLifecycle(),
        now=50,
        limit=1,
    )

    assert coordinator.check_timeouts(now=54) == ()

    decisions = coordinator.check_timeouts(now=55)

    assert len(decisions) == 1
    assert decisions[0].action is WorkflowRecoveryAction.RETRY
    assert len(coordinator.waiting_retries()) == 1

    assert coordinator.release_ready_retries(
        now=56,
    ) == ()

    released = coordinator.release_ready_retries(
        now=57,
    )

    assert len(released) == 1
    assert released[0].step_id == "long-task"


def test_05_execution_success_closes_attempt() -> None:
    coordinator = make_coordinator()

    coordinator.dispatch_coordinator.enqueue_activations(
        (activation("build"),)
    )

    coordinator.dispatch_ready(
        AcceptedLifecycle(),
        now=10,
        limit=1,
    )

    decision = coordinator.record_execution_success(
        "workflow-1",
        "build",
        now=12,
    )

    assert decision.action is WorkflowRecoveryAction.SUCCEEDED
    assert coordinator.inflight() == ()

    state = coordinator.recovery_engine.get(
        "workflow-1",
        "build",
    )

    assert state.terminal is True
    assert state.succeeded is True
    assert state.active is False


def test_06_exhausted_rejection_removes_pending() -> None:
    coordinator = make_coordinator(
        max_attempts=1,
        delay=2,
    )

    coordinator.dispatch_coordinator.enqueue_activations(
        (activation("deploy"),)
    )

    cycle = coordinator.dispatch_ready(
        RejectedLifecycle(),
        now=100,
        limit=1,
    )

    assert cycle.rejected_count == 1
    assert len(coordinator.dispatch_coordinator.scheduler) == 0

    state = coordinator.recovery_engine.get(
        "workflow-1",
        "deploy",
    )

    assert state.terminal is True
    assert state.attempts_started == 1


def test_07_dispatch_exception_is_retryable() -> None:
    coordinator = make_coordinator(delay=2)

    coordinator.dispatch_coordinator.enqueue_activations(
        (activation("build"),)
    )

    cycle = coordinator.dispatch_ready(
        FailedLifecycle(),
        now=100,
        limit=1,
    )

    assert cycle.failed_count == 1
    assert "dispatcher unavailable" in cycle.outcomes[0].reason
    assert len(coordinator.dispatch_coordinator.scheduler) == 1

    state = coordinator.recovery_engine.get(
        "workflow-1",
        "build",
    )

    assert state.active is False
    assert state.terminal is False
    assert state.next_eligible_at == 102


def test_08_priority_order_is_preserved() -> None:
    coordinator = make_coordinator()
    lifecycle = AcceptedLifecycle()

    coordinator.dispatch_coordinator.enqueue_activations(
        (
            activation("normal", priority=100),
            activation("urgent", priority=10),
            activation("high", priority=50),
        )
    )

    cycle = coordinator.dispatch_ready(
        lifecycle,
        now=100,
        limit=3,
    )

    assert cycle.accepted_count == 3

    assert tuple(
        request.step_id
        for request in lifecycle.requests
    ) == (
        "urgent",
        "high",
        "normal",
    )

    assert tuple(
        candidate.step_id
        for candidate in coordinator.inflight()
    ) == (
        "high",
        "normal",
        "urgent",
    )
