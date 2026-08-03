from __future__ import annotations

import pytest

from af_core.organization import (
    CoordinatedTask,
    TaskDependencyGraphEngine,
    TaskPriority,
)


def task(
    task_id: str,
    *,
    dependencies: set[str] | None = None,
    duration: int = 0,
    priority: TaskPriority = TaskPriority.NORMAL,
) -> CoordinatedTask:
    return CoordinatedTask(
        task_id=task_id,
        workflow_id="workflow-001",
        title=task_id,
        description=f"Execute {task_id}",
        dependencies=dependencies or set(),
        estimated_duration_minutes=duration,
        priority=priority,
    )


def test_graph_builds_topological_order():
    engine = TaskDependencyGraphEngine()

    graph = engine.build(
        workflow_id="workflow-001",
        tasks=[
            task("design"),
            task(
                "implementation",
                dependencies={"design"},
            ),
            task(
                "test",
                dependencies={"implementation"},
            ),
        ],
    )

    assert graph.topological_order == [
        "design",
        "implementation",
        "test",
    ]

    assert graph.execution_waves == [
        ["design"],
        ["implementation"],
        ["test"],
    ]


def test_parallel_branches_share_wave():
    engine = TaskDependencyGraphEngine()

    graph = engine.build(
        workflow_id="workflow-001",
        tasks=[
            task("design"),
            task(
                "implementation",
                dependencies={"design"},
            ),
            task(
                "security",
                dependencies={"design"},
            ),
            task(
                "integration",
                dependencies={
                    "implementation",
                    "security",
                },
            ),
        ],
    )

    assert graph.execution_waves == [
        ["design"],
        [
            "implementation",
            "security",
        ],
        ["integration"],
    ]


def test_unknown_dependency_is_invalid():
    engine = TaskDependencyGraphEngine()

    result = engine.validate(
        [
            task(
                "implementation",
                dependencies={"missing"},
            )
        ]
    )

    assert not result.valid

    assert result.unknown_dependencies == {
        "implementation": ["missing"]
    }


def test_cycle_is_detected():
    engine = TaskDependencyGraphEngine()

    tasks = [
        task(
            "a",
            dependencies={"c"},
        ),
        task(
            "b",
            dependencies={"a"},
        ),
        task(
            "c",
            dependencies={"b"},
        ),
    ]

    validation = engine.validate(tasks)

    assert not validation.valid

    assert set(validation.cycle_task_ids) == {
        "a",
        "b",
        "c",
    }

    with pytest.raises(
        ValueError,
        match="contains a cycle",
    ):
        engine.build(
            workflow_id="workflow-001",
            tasks=tasks,
        )


def test_critical_path_uses_longest_duration():
    engine = TaskDependencyGraphEngine()

    graph = engine.build(
        workflow_id="workflow-001",
        tasks=[
            task(
                "design",
                duration=30,
            ),
            task(
                "fast-build",
                dependencies={"design"},
                duration=20,
            ),
            task(
                "security-build",
                dependencies={"design"},
                duration=90,
            ),
            task(
                "release",
                dependencies={
                    "fast-build",
                    "security-build",
                },
                duration=10,
            ),
        ],
    )

    assert graph.critical_path == [
        "design",
        "security-build",
        "release",
    ]

    assert (
        graph.critical_path_duration_minutes
        == 130
    )
