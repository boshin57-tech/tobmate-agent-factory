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
from af_core.orchestrator.workflow_trigger_engine import (
    WorkflowTriggerEvent,
    WorkflowTriggerKind,
)


class AcceptedLifecycle:
    def __init__(self) -> None:
        self.steps: list[str] = []

    def dispatch(self, request) -> bool:
        self.steps.append(request.step_id)
        return True


def test_workflow_runtime_end_to_end_recovery() -> None:
    graph = WorkflowDependencyGraph()
    graph.connect("build", "test")
    graph.connect("test", "deploy")

    recovery = WorkflowFailureRecoveryEngine(
        retry_policy=WorkflowRetryPolicy(
            max_attempts=3,
            initial_delay_seconds=2,
            multiplier=2,
            max_delay_seconds=10,
        ),
        timeout_policy=WorkflowTimeoutPolicy(
            timeout_seconds=5,
        ),
    )

    runtime = WorkflowRuntimeEngine(
        recovery_engine=recovery,
    )

    runtime.register_workflow(
        "release-workflow",
        graph,
    )

    result = runtime.process_event(
        WorkflowTriggerEvent(
            workflow_id="release-workflow",
            event_id="release-start",
            kind=WorkflowTriggerKind.WORKFLOW_STARTED,
        ),
        now=100,
    )

    assert tuple(
        candidate.step_id
        for candidate in result.queued
    ) == ("build",)

    lifecycle = AcceptedLifecycle()

    build_cycle = runtime.dispatch_ready(
        lifecycle,
        now=101,
        limit=1,
    )
    assert build_cycle.accepted_count == 1

    runtime.record_execution_success(
        "release-workflow",
        "build",
        now=102,
    )

    test_cycle = runtime.dispatch_ready(
        lifecycle,
        now=103,
        limit=1,
    )
    assert test_cycle.accepted_count == 1

    failure = runtime.record_execution_failure(
        "release-workflow",
        "test",
        now=104,
        reason="temporary test infrastructure failure",
    )

    assert failure.action.value == "retry"
    assert runtime.release_ready_retries(now=105) == ()

    released = runtime.release_ready_retries(now=106)

    assert tuple(
        candidate.step_id
        for candidate in released
    ) == ("test",)

    retry_cycle = runtime.dispatch_ready(
        lifecycle,
        now=107,
        limit=1,
    )
    assert retry_cycle.accepted_count == 1

    runtime.record_execution_success(
        "release-workflow",
        "test",
        now=108,
    )

    deploy_cycle = runtime.dispatch_ready(
        lifecycle,
        now=109,
        limit=1,
    )
    assert deploy_cycle.accepted_count == 1

    runtime.record_execution_success(
        "release-workflow",
        "deploy",
        now=110,
    )

    snapshot = runtime.snapshot(
        "release-workflow"
    )

    assert snapshot.states == {
        "build": "succeeded",
        "test": "succeeded",
        "deploy": "succeeded",
    }

    assert snapshot.pending_count == 0
    assert snapshot.inflight_count == 0
    assert snapshot.retry_waiting_count == 0

    assert lifecycle.steps == [
        "build",
        "test",
        "test",
        "deploy",
    ]

    metrics = snapshot.metrics

    assert metrics.trigger_count == 1
    assert metrics.activation_count == 3
    assert metrics.dispatch_accepted_count == 4
    assert metrics.execution_succeeded_count == 3
    assert metrics.execution_failed_count == 1
    assert metrics.retry_scheduled_count == 1
    assert metrics.retry_released_count == 1
