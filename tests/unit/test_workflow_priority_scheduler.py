import pytest

from af_core.orchestrator.workflow_priority_scheduler import (
    WorkflowPriorityScheduler,
    WorkflowScheduleCandidate,
    WorkflowSchedulerError,
)
from af_core.orchestrator.workflow_trigger_engine import (
    WorkflowTriggerActivation,
    WorkflowTriggerKind,
)


def make_candidate(
    step_id: str,
    *,
    workflow_id: str = "workflow-1",
    priority: int = 100,
    capabilities: tuple[str, ...] = (),
) -> WorkflowScheduleCandidate:
    return WorkflowScheduleCandidate(
        workflow_id=workflow_id,
        step_id=step_id,
        priority=priority,
        required_capabilities=capabilities,
    )


def test_01_priority_order() -> None:
    scheduler = WorkflowPriorityScheduler()

    scheduler.enqueue(make_candidate("normal", priority=100))
    scheduler.enqueue(make_candidate("urgent", priority=10))
    scheduler.enqueue(make_candidate("high", priority=50))

    batch = scheduler.select(limit=3)

    assert tuple(
        item.step_id for item in batch.selected
    ) == ("urgent", "high", "normal")


def test_02_equal_priority_preserves_insertion_order() -> None:
    scheduler = WorkflowPriorityScheduler()

    scheduler.enqueue(make_candidate("first"))
    scheduler.enqueue(make_candidate("second"))
    scheduler.enqueue(make_candidate("third"))

    assert tuple(
        item.step_id for item in scheduler.pending()
    ) == ("first", "second", "third")


def test_03_duplicate_candidate_is_rejected() -> None:
    scheduler = WorkflowPriorityScheduler()
    scheduler.enqueue(make_candidate("build"))

    with pytest.raises(
        WorkflowSchedulerError,
        match="duplicate workflow schedule candidate",
    ):
        scheduler.enqueue(make_candidate("build"))


def test_04_trigger_activation_is_enqueued() -> None:
    scheduler = WorkflowPriorityScheduler()

    activation = WorkflowTriggerActivation(
        workflow_id="workflow-1",
        trigger_id="dependency-ready:build",
        target_step_id="build",
        kind=WorkflowTriggerKind.DEPENDENCY_READY,
        event_identity="dependency-ready:build",
        priority=25,
    )

    candidate = scheduler.enqueue_activation(
        activation,
        required_capabilities=("python",),
        metadata={"origin": "dependency"},
    )

    assert candidate.step_id == "build"
    assert candidate.priority == 25
    assert candidate.required_capabilities == ("python",)
    assert candidate.metadata["origin"] == "dependency"


def test_05_capacity_limit_defers_remaining_items() -> None:
    scheduler = WorkflowPriorityScheduler()

    scheduler.enqueue(make_candidate("one"))
    scheduler.enqueue(make_candidate("two"))
    scheduler.enqueue(make_candidate("three"))

    batch = scheduler.select(limit=2)

    assert batch.selected_count == 2
    assert batch.deferred_count == 1
    assert len(scheduler) == 3


def test_06_lifecycle_and_capability_gates() -> None:
    scheduler = WorkflowPriorityScheduler()

    scheduler.enqueue(make_candidate("running-step"))
    scheduler.enqueue(
        make_candidate(
            "move-step",
            capabilities=("move", "sui"),
        )
    )
    scheduler.enqueue(
        make_candidate(
            "python-step",
            capabilities=("python",),
        )
    )

    batch = scheduler.select(
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
        item.step_id for item in batch.selected
    ) == ("python-step",)

    assert tuple(
        item.step_id for item in batch.deferred
    ) == ("running-step", "move-step")


def test_07_acknowledge_removes_candidate() -> None:
    scheduler = WorkflowPriorityScheduler()

    stored = scheduler.enqueue(make_candidate("build"))
    selected = scheduler.select(limit=1).selected[0]

    assert selected == stored
    assert scheduler.acknowledge(selected) == stored
    assert len(scheduler) == 0


def test_08_clear_workflow_preserves_other_workflows() -> None:
    scheduler = WorkflowPriorityScheduler()

    scheduler.enqueue(make_candidate("build"))
    scheduler.enqueue(make_candidate("test"))
    scheduler.enqueue(
        make_candidate(
            "deploy",
            workflow_id="workflow-2",
        )
    )

    removed = scheduler.clear_workflow("workflow-1")

    assert tuple(
        item.step_id for item in removed
    ) == ("build", "test")

    assert tuple(
        item.workflow_id for item in scheduler.pending()
    ) == ("workflow-2",)
