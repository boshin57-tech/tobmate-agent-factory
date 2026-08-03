from af_core.orchestrator.workflow_dispatch_coordinator import (
    WorkflowDispatchCoordinator,
    WorkflowDispatchOutcome,
    WorkflowDispatchRequest,
    WorkflowDispatchStatus,
)
from af_core.orchestrator.workflow_trigger_engine import (
    WorkflowTriggerActivation,
    WorkflowTriggerKind,
)


def activation(
    step_id: str,
    *,
    workflow_id: str = "workflow-1",
    priority: int = 100,
) -> WorkflowTriggerActivation:
    return WorkflowTriggerActivation(
        workflow_id=workflow_id,
        trigger_id=f"trigger:{step_id}",
        target_step_id=step_id,
        kind=WorkflowTriggerKind.DEPENDENCY_READY,
        event_identity=f"event:{step_id}",
        priority=priority,
    )


class RecordingLifecycle:
    def __init__(self, accepted: bool = True) -> None:
        self.accepted = accepted
        self.requests: list[WorkflowDispatchRequest] = []

    def dispatch(
        self,
        request: WorkflowDispatchRequest,
    ) -> bool:
        self.requests.append(request)
        return self.accepted


def test_01_activation_is_converted_to_candidate() -> None:
    coordinator = WorkflowDispatchCoordinator()

    queued = coordinator.enqueue_activations(
        (activation("build", priority=20),),
        capability_resolver=lambda _: ("python",),
        metadata_resolver=lambda _: {"owner": "builder"},
    )

    assert len(queued) == 1

    candidate = queued[0]

    assert candidate.step_id == "build"
    assert candidate.priority == 20
    assert candidate.required_capabilities == ("python",)
    assert candidate.metadata["owner"] == "builder"
    assert candidate.metadata["trigger_kind"] == "dependency_ready"


def test_02_duplicate_pending_activation_is_ignored() -> None:
    coordinator = WorkflowDispatchCoordinator()
    item = activation("build")

    first = coordinator.enqueue_activations((item,))
    second = coordinator.enqueue_activations((item,))

    assert len(first) == 1
    assert second == ()
    assert len(coordinator.scheduler) == 1


def test_03_priority_controls_dispatch_order() -> None:
    coordinator = WorkflowDispatchCoordinator()
    lifecycle = RecordingLifecycle()

    coordinator.enqueue_activations(
        (
            activation("normal", priority=100),
            activation("urgent", priority=10),
            activation("high", priority=50),
        )
    )

    cycle = coordinator.dispatch_ready(
        lifecycle,
        limit=3,
    )

    assert tuple(
        request.step_id
        for request in lifecycle.requests
    ) == ("urgent", "high", "normal")

    assert cycle.accepted_count == 3
    assert len(coordinator.scheduler) == 0


def test_04_lifecycle_and_capability_gates_dispatch() -> None:
    coordinator = WorkflowDispatchCoordinator()
    lifecycle = RecordingLifecycle()

    coordinator.enqueue_activations(
        (
            activation("running-step", priority=10),
            activation("move-step", priority=20),
            activation("python-step", priority=30),
        ),
        capability_resolver=lambda item: (
            ("move", "sui")
            if item.target_step_id == "move-step"
            else (
                ("python",)
                if item.target_step_id == "python-step"
                else ()
            )
        ),
    )

    cycle = coordinator.dispatch_ready(
        lifecycle,
        limit=3,
        states_by_workflow={
            "workflow-1": {
                "running-step": "running",
                "move-step": "pending",
                "python-step": "pending",
            }
        },
        available_capabilities=("python",),
    )

    assert tuple(
        request.step_id
        for request in lifecycle.requests
    ) == ("python-step",)

    assert tuple(
        item.step_id
        for item in cycle.deferred
    ) == ("running-step", "move-step")

    assert len(coordinator.scheduler) == 2


def test_05_accepted_dispatch_removes_candidate() -> None:
    coordinator = WorkflowDispatchCoordinator()
    lifecycle = RecordingLifecycle(accepted=True)

    coordinator.enqueue_activations(
        (activation("build"),)
    )

    cycle = coordinator.dispatch_ready(
        lifecycle,
        limit=1,
    )

    assert cycle.accepted_count == 1
    assert cycle.rejected_count == 0
    assert cycle.failed_count == 0
    assert len(coordinator.scheduler) == 0


def test_06_rejected_dispatch_remains_pending() -> None:
    coordinator = WorkflowDispatchCoordinator()
    lifecycle = RecordingLifecycle(accepted=False)

    coordinator.enqueue_activations(
        (activation("deploy"),)
    )

    cycle = coordinator.dispatch_ready(
        lifecycle,
        limit=1,
    )

    assert cycle.accepted_count == 0
    assert cycle.rejected_count == 1
    assert cycle.failed_count == 0
    assert len(coordinator.scheduler) == 1


def test_07_dispatch_exception_becomes_failed_outcome() -> None:
    coordinator = WorkflowDispatchCoordinator()

    class FailingLifecycle:
        def dispatch(
            self,
            request: WorkflowDispatchRequest,
        ) -> bool:
            raise RuntimeError("lifecycle unavailable")

    coordinator.enqueue_activations(
        (activation("test"),)
    )

    cycle = coordinator.dispatch_ready(
        FailingLifecycle(),
        limit=1,
    )

    assert cycle.failed_count == 1
    assert cycle.outcomes[0].status is WorkflowDispatchStatus.FAILED
    assert "lifecycle unavailable" in cycle.outcomes[0].reason
    assert len(coordinator.scheduler) == 1


def test_08_structured_accepted_outcome_is_supported() -> None:
    coordinator = WorkflowDispatchCoordinator()

    class StructuredLifecycle:
        def dispatch(
            self,
            request: WorkflowDispatchRequest,
        ) -> WorkflowDispatchOutcome:
            return WorkflowDispatchOutcome(
                request=request,
                status=WorkflowDispatchStatus.ACCEPTED,
                reason="lifecycle transition recorded",
            )

    coordinator.enqueue_activations(
        (activation("deploy"),)
    )

    cycle = coordinator.dispatch_ready(
        StructuredLifecycle(),
        limit=1,
    )

    assert cycle.accepted_count == 1
    assert cycle.outcomes[0].reason == (
        "lifecycle transition recorded"
    )
    assert len(coordinator.scheduler) == 0
