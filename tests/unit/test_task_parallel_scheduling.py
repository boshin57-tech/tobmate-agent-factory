from __future__ import annotations

from af_core.organization import (
    CoordinatedTask,
    CoordinatedTaskStatus,
    CoordinationStatus,
    ParallelTaskScheduler,
    TaskCoordinationWorkflow,
    TaskDependencyGraphEngine,
    TaskExecutionMode,
    TaskPriority,
    TaskReadyQueueEngine,
)


def task(
    task_id: str,
    *,
    dependencies: set[str] | None = None,
    duration: int = 0,
    mode: TaskExecutionMode = (
        TaskExecutionMode.PARALLEL
    ),
    priority: TaskPriority = TaskPriority.NORMAL,
    status: CoordinatedTaskStatus = (
        CoordinatedTaskStatus.CREATED
    ),
) -> CoordinatedTask:
    return CoordinatedTask(
        task_id=task_id,
        workflow_id="workflow-001",
        title=task_id,
        description=f"Execute {task_id}",
        dependencies=dependencies or set(),
        estimated_duration_minutes=duration,
        execution_mode=mode,
        priority=priority,
        status=status,
    )


def test_parallel_tasks_share_schedule_wave():
    tasks = [
        task(
            "design",
            duration=30,
        ),
        task(
            "implementation",
            dependencies={"design"},
            duration=90,
        ),
        task(
            "security",
            dependencies={"design"},
            duration=60,
        ),
    ]

    graph = TaskDependencyGraphEngine().build(
        workflow_id="workflow-001",
        tasks=tasks,
    )

    schedule = (
        ParallelTaskScheduler()
        .build_schedule(
            graph=graph,
            tasks=tasks,
        )
    )

    assert len(schedule.waves) == 2

    assert schedule.waves[1].task_ids == [
        "implementation",
        "security",
    ]

    assert (
        schedule.waves[1]
        .estimated_duration_minutes
        == 90
    )

    assert schedule.maximum_parallelism == 2


def test_exclusive_task_has_own_wave():
    tasks = [
        task(
            "implementation",
            duration=60,
        ),
        task(
            "database-migration",
            duration=20,
            mode=TaskExecutionMode.EXCLUSIVE,
        ),
    ]

    graph = TaskDependencyGraphEngine().build(
        workflow_id="workflow-001",
        tasks=tasks,
    )

    schedule = (
        ParallelTaskScheduler()
        .build_schedule(
            graph=graph,
            tasks=tasks,
        )
    )

    assert len(schedule.waves) == 2

    exclusive_waves = [
        wave
        for wave in schedule.waves
        if wave.exclusive_task_ids
    ]

    assert len(exclusive_waves) == 1

    assert (
        exclusive_waves[0]
        .exclusive_task_ids
        == ["database-migration"]
    )


def test_ready_queue_prioritizes_critical_task():
    tasks = [
        task(
            "normal",
            duration=20,
            priority=TaskPriority.NORMAL,
            status=CoordinatedTaskStatus.READY,
        ),
        task(
            "critical",
            duration=120,
            priority=TaskPriority.CRITICAL,
            status=CoordinatedTaskStatus.READY,
        ),
    ]

    workflow = TaskCoordinationWorkflow(
        workflow_id="workflow-001",
        workspace_id="workspace-001",
        team_id="team-001",
        name="Test workflow",
        objective="Test scheduling",
        created_by="planner-agent",
        status=CoordinationStatus.READY,
        tasks=tasks,
    )

    graph = TaskDependencyGraphEngine().build(
        workflow_id=workflow.workflow_id,
        tasks=tasks,
    )

    queue = TaskReadyQueueEngine().build_queue(
        workflow=workflow,
        graph=graph,
    )

    assert queue.task_ids == [
        "critical",
        "normal",
    ]


def test_exclusive_task_is_selected_alone():
    tasks = [
        task(
            "exclusive",
            priority=TaskPriority.CRITICAL,
            mode=TaskExecutionMode.EXCLUSIVE,
            status=CoordinatedTaskStatus.READY,
        ),
        task(
            "parallel",
            priority=TaskPriority.NORMAL,
            status=CoordinatedTaskStatus.READY,
        ),
    ]

    workflow = TaskCoordinationWorkflow(
        workflow_id="workflow-001",
        workspace_id="workspace-001",
        team_id="team-001",
        name="Test workflow",
        objective="Test exclusive scheduling",
        created_by="planner-agent",
        status=CoordinationStatus.READY,
        tasks=tasks,
    )

    graph = TaskDependencyGraphEngine().build(
        workflow_id=workflow.workflow_id,
        tasks=tasks,
    )

    selected = (
        TaskReadyQueueEngine()
        .select_batch(
            workflow=workflow,
            graph=graph,
            maximum_tasks=2,
        )
    )

    assert selected == [
        "exclusive"
    ]


def test_ready_queue_ignores_blocked_tasks():
    tasks = [
        task(
            "ready",
            status=CoordinatedTaskStatus.READY,
        ),
        task(
            "blocked",
            dependencies={"ready"},
            status=CoordinatedTaskStatus.BLOCKED,
        ),
    ]

    workflow = TaskCoordinationWorkflow(
        workflow_id="workflow-001",
        workspace_id="workspace-001",
        team_id="team-001",
        name="Test workflow",
        objective="Test blocked filtering",
        created_by="planner-agent",
        status=CoordinationStatus.READY,
        tasks=tasks,
    )

    graph = TaskDependencyGraphEngine().build(
        workflow_id=workflow.workflow_id,
        tasks=tasks,
    )

    queue = TaskReadyQueueEngine().build_queue(
        workflow=workflow,
        graph=graph,
    )

    assert queue.task_ids == [
        "ready"
    ]
