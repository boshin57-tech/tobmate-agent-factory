import pytest

from af_core.orchestrator.planner import (
    PlannedTask,
    ProjectPlan,
)
from af_core.orchestrator.task_graph import (
    GraphTaskStatus,
    TaskGraph,
    TaskGraphError,
)


def make_plan() -> ProjectPlan:
    return ProjectPlan(
        goal="Implement feature",
        tasks=[
            PlannedTask(
                id="task-1",
                title="Analyze",
                description="Analyze",
                task_type="analysis",
                agent_role="planner",
            ),
            PlannedTask(
                id="task-2",
                title="Implement",
                description="Implement",
                task_type="implementation",
                dependencies=["task-1"],
                agent_role="implementer",
            ),
            PlannedTask(
                id="task-3",
                title="Test",
                description="Test",
                task_type="validation",
                dependencies=["task-2"],
                agent_role="tester",
            ),
        ],
    )


def test_task_graph_returns_ready_tasks_in_order() -> None:
    graph = TaskGraph(make_plan())
    state = graph.initial_state()

    assert [task.id for task in graph.ready_tasks(state)] == [
        "task-1"
    ]

    state = graph.mark_running(state, "task-1")
    state = graph.mark_completed(state, "task-1")

    assert [task.id for task in graph.ready_tasks(state)] == [
        "task-2"
    ]


def test_task_failure_blocks_dependents() -> None:
    graph = TaskGraph(make_plan())
    state = graph.initial_state()

    state = graph.mark_running(state, "task-1")
    state = graph.mark_completed(state, "task-1")
    state = graph.mark_running(state, "task-2")
    state = graph.mark_failed(state, "task-2")

    assert state.statuses["task-2"] is GraphTaskStatus.FAILED
    assert state.statuses["task-3"] is GraphTaskStatus.BLOCKED
    assert graph.has_failures(state)


def test_task_graph_detects_cycle() -> None:
    plan = ProjectPlan(
        goal="Cycle",
        tasks=[
            PlannedTask(
                id="task-1",
                title="One",
                description="One",
                task_type="test",
                dependencies=["task-2"],
                agent_role="tester",
            ),
            PlannedTask(
                id="task-2",
                title="Two",
                description="Two",
                task_type="test",
                dependencies=["task-1"],
                agent_role="tester",
            ),
        ],
    )

    with pytest.raises(TaskGraphError):
        TaskGraph(plan)


def test_task_cannot_run_before_dependencies() -> None:
    graph = TaskGraph(make_plan())
    state = graph.initial_state()

    with pytest.raises(TaskGraphError):
        graph.mark_running(state, "task-2")
