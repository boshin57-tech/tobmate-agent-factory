import pytest
from pydantic import ValidationError

from af_core.orchestrator.planner import (
    DeterministicPlanner,
    PlannedTask,
    PlanningRequest,
    ProjectPlan,
)
from af_core.repository.context_builder import ContextPackage


def context() -> ContextPackage:
    return ContextPackage(
        objective="Add planner",
        repository_summary=(
            "Repository: /tmp/repo\n"
            "Branch: main\n"
            "HEAD: abc initial\n"
            "Languages: Python\n"
            "Dirty: False\n"
            "Build commands: python -m build\n"
            "Test commands: pytest"
        ),
    )


def test_deterministic_planner_creates_structured_plan() -> None:
    planner = DeterministicPlanner()

    plan = planner.create_plan(
        PlanningRequest(
            objective="Add planner and tests",
            context=context(),
        )
    )

    assert plan.goal == "Add planner and tests"
    assert len(plan.tasks) == 5
    assert plan.tasks[0].dependencies == []
    assert plan.tasks[1].dependencies == ["task-1"]
    assert any(
        "pytest" in item
        for item in plan.validation_strategy
    )


def test_project_plan_rejects_unknown_dependency() -> None:
    with pytest.raises(ValidationError):
        ProjectPlan(
            goal="Invalid",
            tasks=[
                PlannedTask(
                    id="task-1",
                    title="Invalid task",
                    description="Invalid dependency",
                    task_type="test",
                    dependencies=["missing"],
                    agent_role="tester",
                )
            ],
        )


def test_project_plan_rejects_duplicate_ids() -> None:
    task = PlannedTask(
        id="task-1",
        title="Task",
        description="Task",
        task_type="test",
        agent_role="tester",
    )

    with pytest.raises(ValidationError):
        ProjectPlan(
            goal="Invalid",
            tasks=[task, task.model_copy()],
        )
