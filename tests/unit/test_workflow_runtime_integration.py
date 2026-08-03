from af_core.orchestrator.workflow_dependency_graph import (
    WorkflowDependencyGraph,
)
from af_core.orchestrator.workflow_recovery_engine import (
    WorkflowFailureRecoveryEngine,
    WorkflowRetryPolicy,
    WorkflowTimeoutPolicy,
)
from af_core.orchestrator.workflow_runtime_engine import (
    WorkflowRuntimeEngine,
)
from af_core.orchestrator.workflow_runtime_models import (
    WorkflowRuntimeError,
)
from af_core.orchestrator.workflow_runtime_observability import (
    WorkflowRuntimeEventKind,
    WorkflowRuntimeObserver,
)
from af_core.orchestrator.workflow_trigger_engine import (
    WorkflowTriggerEvent,
    WorkflowTriggerKind,
)


class AcceptedLifecycle:
    def dispatch(self, request):
        return True


class RejectedLifecycle:
    def dispatch(self, request):
        return False


def single_step_graph() -> WorkflowDependencyGraph:
    graph = WorkflowDependencyGraph()
    graph.add_step("build")
    return graph


def linear_graph() -> WorkflowDependencyGraph:
    graph = WorkflowDependencyGraph()
    graph.connect("build", "test")
    graph.connect("test", "deploy")
    return graph


def make_runtime(
    *,
    delay: float = 2,
    timeout: float = 5,
    max_attempts: int = 3,
) -> WorkflowRuntimeEngine:
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

    return WorkflowRuntimeEngine(
        recovery_engine=recovery,
    )


def start(
    runtime: WorkflowRuntimeEngine,
    workflow_id: str,
    graph: WorkflowDependencyGraph,
    *,
    now: float = 100,
) -> None:
    runtime.register_workflow(
        workflow_id,
        graph,
    )

    result = runtime.process_event(
        WorkflowTriggerEvent(
            workflow_id=workflow_id,
            event_id=f"start:{workflow_id}",
            kind=WorkflowTriggerKind.WORKFLOW_STARTED,
        ),
        now=now,
    )

    assert len(result.queued) == 1


def test_01_observer_filters_and_metrics() -> None:
    observer = WorkflowRuntimeObserver()

    observer.record(
        workflow_id="workflow-1",
        step_id="build",
        kind=WorkflowRuntimeEventKind.TRIGGER_PROCESSED,
        occurred_at=10,
    )
    observer.record(
        workflow_id="workflow-1",
        step_id="build",
        kind=WorkflowRuntimeEventKind.ACTIVATION_QUEUED,
        occurred_at=11,
    )
    observer.record(
        workflow_id="workflow-2",
        step_id="deploy",
        kind=WorkflowRuntimeEventKind.DISPATCH_FAILED,
        occurred_at=12,
    )

    events = observer.events(
        workflow_id="workflow-1"
    )
    metrics = observer.metrics(
        workflow_id="workflow-1"
    )

    assert tuple(event.sequence for event in events) == (1, 2)
    assert metrics.event_count == 2
    assert metrics.workflow_count == 1
    assert metrics.trigger_count == 1
    assert metrics.activation_count == 1
    assert metrics.dispatch_failed_count == 0


def test_02_observer_clear_preserves_other_workflows() -> None:
    observer = WorkflowRuntimeObserver()

    observer.record(
        workflow_id="workflow-1",
        kind=WorkflowRuntimeEventKind.TRIGGER_PROCESSED,
        occurred_at=10,
    )
    observer.record(
        workflow_id="workflow-2",
        kind=WorkflowRuntimeEventKind.TRIGGER_PROCESSED,
        occurred_at=11,
    )

    removed = observer.clear_workflow(
        "workflow-1",
        occurred_at=12,
    )

    assert len(removed) == 1
    assert len(observer.events(workflow_id="workflow-2")) == 1

    remaining = observer.events(
        workflow_id="workflow-1"
    )

    assert len(remaining) == 1
    assert (
        remaining[0].kind
        is WorkflowRuntimeEventKind.WORKFLOW_CLEARED
    )


def test_03_success_flow_activates_dependencies() -> None:
    runtime = make_runtime()
    start(runtime, "workflow-1", linear_graph())

    first = runtime.dispatch_ready(
        AcceptedLifecycle(),
        now=101,
        limit=1,
    )
    assert first.accepted_count == 1

    runtime.record_execution_success(
        "workflow-1",
        "build",
        now=102,
    )

    second = runtime.dispatch_ready(
        AcceptedLifecycle(),
        now=103,
        limit=1,
    )
    assert second.accepted_count == 1

    runtime.record_execution_success(
        "workflow-1",
        "test",
        now=104,
    )

    snapshot = runtime.snapshot("workflow-1")

    assert snapshot.states["build"] == "succeeded"
    assert snapshot.states["test"] == "succeeded"
    assert snapshot.states["deploy"] == "pending"
    assert snapshot.pending_count == 1
    assert snapshot.metrics.execution_succeeded_count == 2


def test_04_execution_failure_releases_retry() -> None:
    runtime = make_runtime(delay=2)
    start(runtime, "workflow-1", single_step_graph())

    runtime.dispatch_ready(
        AcceptedLifecycle(),
        now=101,
        limit=1,
    )

    decision = runtime.record_execution_failure(
        "workflow-1",
        "build",
        now=102,
        reason="temporary error",
    )

    assert decision.action.value == "retry"
    assert runtime.release_ready_retries(now=103) == ()

    released = runtime.release_ready_retries(now=104)

    assert len(released) == 1

    snapshot = runtime.snapshot("workflow-1")

    assert snapshot.states["build"] == "pending"
    assert snapshot.pending_count == 1
    assert snapshot.retry_waiting_count == 0
    assert snapshot.metrics.retry_scheduled_count == 1
    assert snapshot.metrics.retry_released_count == 1


def test_05_timeout_schedules_retry() -> None:
    runtime = make_runtime(
        delay=2,
        timeout=5,
    )
    start(runtime, "workflow-1", single_step_graph())

    runtime.dispatch_ready(
        AcceptedLifecycle(),
        now=101,
        limit=1,
    )

    assert runtime.check_timeouts(now=105) == ()

    decisions = runtime.check_timeouts(now=106)

    assert len(decisions) == 1
    assert decisions[0].action.value == "retry"

    snapshot = runtime.snapshot("workflow-1")

    assert snapshot.states["build"] == "retry_waiting"
    assert snapshot.retry_waiting_count == 1
    assert snapshot.metrics.timeout_count == 1
    assert snapshot.metrics.retry_scheduled_count == 1


def test_06_rejected_dispatch_obeys_backoff() -> None:
    runtime = make_runtime(delay=2)
    start(runtime, "workflow-1", single_step_graph())

    rejected = runtime.dispatch_ready(
        RejectedLifecycle(),
        now=101,
        limit=1,
    )

    assert rejected.rejected_count == 1

    blocked = runtime.dispatch_ready(
        AcceptedLifecycle(),
        now=102,
        limit=1,
    )

    assert blocked.outcomes == ()

    accepted = runtime.dispatch_ready(
        AcceptedLifecycle(),
        now=103,
        limit=1,
    )

    assert accepted.accepted_count == 1

    snapshot = runtime.snapshot("workflow-1")

    assert snapshot.states["build"] == "running"
    assert snapshot.metrics.dispatch_rejected_count == 1
    assert snapshot.metrics.dispatch_accepted_count == 1


def test_07_workflow_metrics_are_isolated() -> None:
    runtime = make_runtime()

    runtime.register_workflow(
        "workflow-1",
        single_step_graph(),
    )
    runtime.register_workflow(
        "workflow-2",
        single_step_graph(),
    )

    runtime.process_event(
        WorkflowTriggerEvent(
            workflow_id="workflow-1",
            event_id="start-1",
            kind=WorkflowTriggerKind.WORKFLOW_STARTED,
        ),
        now=10,
    )

    first = runtime.snapshot("workflow-1")
    second = runtime.snapshot("workflow-2")

    assert first.metrics.event_count == 2
    assert first.pending_count == 1
    assert second.metrics.event_count == 0
    assert second.pending_count == 0


def test_08_registry_rejects_duplicate_workflow() -> None:
    runtime = make_runtime()

    runtime.register_workflow(
        "workflow-1",
        single_step_graph(),
    )

    try:
        runtime.register_workflow(
            "workflow-1",
            single_step_graph(),
        )
    except WorkflowRuntimeError:
        pass
    else:
        raise AssertionError(
            "duplicate workflow registration was accepted"
        )
