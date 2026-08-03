from __future__ import annotations

from af_core.communication import (
    AgentCommunicationBus,
    AgentMessage,
)
from af_core.organization import (
    CoordinatedTask,
    CoordinatedTaskStatus,
    CoordinationStatus,
    MultiAgentTaskCoordinationEngine,
    ParallelTaskScheduler,
    TaskAgentAvailability,
    TaskAgentRuntimeProfile,
    TaskCoordinationCoordinator,
    TaskCoordinationEventPublisher,
    TaskCoordinationWorkflow,
    TaskDependencyGraphEngine,
    TaskExecutionMode,
    TaskPriority,
    TaskReassignmentReason,
    TaskReassignmentRequest,
    TaskRuntimeProfileRepository,
)


def make_profile(
    agent_id: str,
    *,
    capabilities: set[str],
    supported_tasks: set[str],
    quality_score: float = 95.0,
    workload_ratio: float = 0.0,
) -> TaskAgentRuntimeProfile:
    return TaskAgentRuntimeProfile(
        agent_id=agent_id,
        capabilities=capabilities,
        supported_tasks=supported_tasks,
        availability=(
            TaskAgentAvailability.AVAILABLE
        ),
        current_task_count=0,
        maximum_task_count=4,
        workload_ratio=workload_ratio,
        success_rate=0.98,
        quality_score=quality_score,
        reliability_score=98.0,
    )


def make_task(
    task_id: str,
    *,
    capabilities: set[str],
    supported_tasks: set[str],
    dependencies: set[str] | None = None,
    duration: int = 30,
    priority: TaskPriority = TaskPriority.NORMAL,
    mode: TaskExecutionMode = (
        TaskExecutionMode.PARALLEL
    ),
) -> CoordinatedTask:
    return CoordinatedTask(
        task_id=task_id,
        workflow_id="workflow-e2e",
        title=f"Task {task_id}",
        description=f"Execute {task_id}",
        required_capabilities=capabilities,
        required_tasks=supported_tasks,
        dependencies=dependencies or set(),
        estimated_duration_minutes=duration,
        priority=priority,
        execution_mode=mode,
    )


def task_by_id(
    workflow: TaskCoordinationWorkflow,
    task_id: str,
) -> CoordinatedTask:
    return next(
        task
        for task in workflow.tasks
        if task.task_id == task_id
    )


def build_tasks() -> list[CoordinatedTask]:
    return [
        make_task(
            "design",
            capabilities={"architecture"},
            supported_tasks={"system_design"},
            duration=30,
            priority=TaskPriority.HIGH,
            mode=TaskExecutionMode.SEQUENTIAL,
        ),
        make_task(
            "implementation",
            capabilities={
                "sui_move",
                "smart_contract",
            },
            supported_tasks={
                "contract_implementation",
            },
            dependencies={"design"},
            duration=90,
            priority=TaskPriority.HIGH,
        ),
        make_task(
            "security-review",
            capabilities={"security_audit"},
            supported_tasks={"security_review"},
            dependencies={"design"},
            duration=120,
            priority=TaskPriority.CRITICAL,
        ),
        make_task(
            "release",
            capabilities={
                "release_management",
            },
            supported_tasks={"release"},
            dependencies={
                "implementation",
                "security-review",
            },
            duration=20,
            priority=TaskPriority.HIGH,
            mode=TaskExecutionMode.SEQUENTIAL,
        ),
    ]


def build_system() -> tuple[
    AgentCommunicationBus,
    TaskRuntimeProfileRepository,
    MultiAgentTaskCoordinationEngine,
    TaskCoordinationCoordinator,
    list[AgentMessage],
]:
    received: list[AgentMessage] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="task.**",
        agent_id="task-intelligence-monitor",
        workspace_id="blockchain-workspace",
        handler=received.append,
    )

    profiles = TaskRuntimeProfileRepository()

    profiles.register(
        make_profile(
            "architecture-agent",
            capabilities={"architecture"},
            supported_tasks={"system_design"},
        )
    )

    profiles.register(
        make_profile(
            "move-agent",
            capabilities={
                "sui_move",
                "smart_contract",
            },
            supported_tasks={
                "contract_implementation",
            },
        )
    )

    profiles.register(
        make_profile(
            "security-primary",
            capabilities={"security_audit"},
            supported_tasks={"security_review"},
            quality_score=99.0,
        )
    )

    profiles.register(
        make_profile(
            "security-backup",
            capabilities={"security_audit"},
            supported_tasks={"security_review"},
            quality_score=90.0,
            workload_ratio=0.10,
        )
    )

    profiles.register(
        make_profile(
            "release-agent",
            capabilities={
                "release_management",
            },
            supported_tasks={"release"},
        )
    )

    engine = MultiAgentTaskCoordinationEngine(
        runtime_profiles=profiles
    )

    coordinator = TaskCoordinationCoordinator(
        engine=engine,
        publisher=(
            TaskCoordinationEventPublisher(
                bus
            )
        ),
    )

    return (
        bus,
        profiles,
        engine,
        coordinator,
        received,
    )


def test_complete_autonomous_task_coordination_flow():
    (
        bus,
        profiles,
        engine,
        coordinator,
        received,
    ) = build_system()

    tasks = build_tasks()

    graph = TaskDependencyGraphEngine().build(
        workflow_id="workflow-e2e",
        tasks=tasks,
    )

    schedule = (
        ParallelTaskScheduler()
        .build_schedule(
            graph=graph,
            tasks=tasks,
        )
    )

    assert graph.execution_waves == [
        ["design"],
        [
            "security-review",
            "implementation",
        ],
        ["release"],
    ]

    assert schedule.maximum_parallelism == 2

    assert graph.critical_path == [
        "design",
        "security-review",
        "release",
    ]

    assert (
        graph.critical_path_duration_minutes
        == 170
    )

    workflow = coordinator.create_workflow(
        TaskCoordinationWorkflow(
            workflow_id="workflow-e2e",
            workspace_id=(
                "blockchain-workspace"
            ),
            team_id="team-e2e",
            name=(
                "Autonomous Move Delivery"
            ),
            objective=(
                "Design, implement, secure, "
                "and release a Move module"
            ),
            created_by="planner-agent",
        )
    )

    for task in tasks:
        workflow = coordinator.add_task(
            workflow_id=(
                workflow.workflow_id
            ),
            task=task,
        )

    workflow = coordinator.prepare_workflow(
        workflow.workflow_id
    )

    assert (
        task_by_id(
            workflow,
            "design",
        ).status
        is CoordinatedTaskStatus.READY
    )

    assert (
        task_by_id(
            workflow,
            "implementation",
        ).status
        is CoordinatedTaskStatus.BLOCKED
    )

    workflow, design_selection = (
        coordinator
        .automatically_assign_task(
            workflow_id=(
                workflow.workflow_id
            ),
            task_id="design",
            assigned_by=(
                "autonomous-coordinator"
            ),
        )
    )

    assert (
        design_selection.selected_agent_id
        == "architecture-agent"
    )

    workflow = coordinator.start_workflow(
        workflow.workflow_id
    )

    workflow = coordinator.start_task(
        workflow_id=workflow.workflow_id,
        task_id="design",
    )

    workflow = coordinator.complete_task(
        workflow_id=workflow.workflow_id,
        task_id="design",
        result={
            "architecture":
                "approved",
        },
    )

    assert (
        task_by_id(
            workflow,
            "implementation",
        ).status
        is CoordinatedTaskStatus.READY
    )

    assert (
        task_by_id(
            workflow,
            "security-review",
        ).status
        is CoordinatedTaskStatus.READY
    )

    workflow, implementation_selection = (
        coordinator
        .automatically_assign_task(
            workflow_id=(
                workflow.workflow_id
            ),
            task_id="implementation",
            assigned_by=(
                "autonomous-coordinator"
            ),
        )
    )

    assert (
        implementation_selection
        .selected_agent_id
        == "move-agent"
    )

    workflow, security_selection = (
        coordinator
        .automatically_assign_task(
            workflow_id=(
                workflow.workflow_id
            ),
            task_id="security-review",
            assigned_by=(
                "autonomous-coordinator"
            ),
        )
    )

    assert (
        security_selection
        .selected_agent_id
        == "security-primary"
    )

    workflow = coordinator.start_task(
        workflow_id=workflow.workflow_id,
        task_id="implementation",
    )

    workflow = coordinator.start_task(
        workflow_id=workflow.workflow_id,
        task_id="security-review",
    )

    workflow = coordinator.complete_task(
        workflow_id=workflow.workflow_id,
        task_id="implementation",
        result={
            "tests_passed": True,
        },
    )

    profiles.update_availability(
        agent_id="security-primary",
        availability=(
            TaskAgentAvailability.OFFLINE
        ),
    )

    reassignment = coordinator.reassign_task(
        TaskReassignmentRequest(
            workflow_id=(
                workflow.workflow_id
            ),
            task_id="security-review",
            requested_by=(
                "runtime-health-monitor"
            ),
            reason=(
                TaskReassignmentReason
                .AGENT_OFFLINE
            ),
        )
    )

    assert reassignment.completed

    assert (
        reassignment.previous_agent_id
        == "security-primary"
    )

    assert (
        reassignment.replacement_agent_id
        == "security-backup"
    )

    workflow = coordinator.get_workflow(
        workflow.workflow_id
    )

    assert workflow is not None

    assert (
        task_by_id(
            workflow,
            "security-review",
        ).assigned_agent_id
        == "security-backup"
    )

    workflow = coordinator.start_task(
        workflow_id=workflow.workflow_id,
        task_id="security-review",
    )

    workflow = coordinator.complete_task(
        workflow_id=workflow.workflow_id,
        task_id="security-review",
        result={
            "security_review":
                "approved",
        },
    )

    assert (
        task_by_id(
            workflow,
            "release",
        ).status
        is CoordinatedTaskStatus.READY
    )

    workflow, release_selection = (
        coordinator
        .automatically_assign_task(
            workflow_id=(
                workflow.workflow_id
            ),
            task_id="release",
            assigned_by=(
                "autonomous-coordinator"
            ),
        )
    )

    assert (
        release_selection.selected_agent_id
        == "release-agent"
    )

    workflow = coordinator.start_task(
        workflow_id=workflow.workflow_id,
        task_id="release",
    )

    workflow = coordinator.complete_task(
        workflow_id=workflow.workflow_id,
        task_id="release",
        result={
            "release_status":
                "ready",
        },
    )

    assert (
        workflow.status
        is CoordinationStatus.COMPLETED
    )

    assert workflow.progress_ratio == 1.0
    assert workflow.completed_at is not None

    assert all(
        task.status
        is CoordinatedTaskStatus.COMPLETED
        for task in workflow.tasks
    )

    primary = engine.runtime_profile(
        "security-primary"
    )

    backup = engine.runtime_profile(
        "security-backup"
    )

    assert primary is not None
    assert backup is not None

    assert primary.current_task_count == 0
    assert backup.current_task_count == 0

    topics = [
        message.topic
        for message in received
    ]

    assert (
        "task.reassigned"
        in topics
    )

    assert (
        topics[-1]
        == "task.workflow.completed"
    )

    assert bus.verify_audit_integrity()

    history = engine.reassignment_history(
        workflow_id="workflow-e2e",
        task_id="security-review",
    )

    assert len(history) == 1

    assert (
        history[0].replacement_agent_id
        == "security-backup"
    )


def test_parallel_schedule_respects_exclusive_task():
    tasks = [
        make_task(
            "implementation",
            capabilities={"sui_move"},
            supported_tasks={
                "contract_implementation",
            },
            duration=60,
        ),
        make_task(
            "database-migration",
            capabilities={
                "database_migration",
            },
            supported_tasks={"migration"},
            duration=20,
            priority=TaskPriority.CRITICAL,
            mode=TaskExecutionMode.EXCLUSIVE,
        ),
    ]

    graph = TaskDependencyGraphEngine().build(
        workflow_id="workflow-e2e",
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

    exclusive = next(
        wave
        for wave in schedule.waves
        if wave.exclusive_task_ids
    )

    assert exclusive.task_ids == [
        "database-migration"
    ]

    assert (
        exclusive.exclusive_task_ids
        == ["database-migration"]
    )


def test_end_to_end_events_are_workspace_isolated():
    blockchain_events: list[
        AgentMessage
    ] = []

    other_events: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="task.**",
        agent_id="blockchain-monitor",
        workspace_id=(
            "blockchain-workspace"
        ),
        handler=(
            blockchain_events.append
        ),
    )

    bus.subscribe(
        topic="task.**",
        agent_id="other-monitor",
        workspace_id="other-workspace",
        handler=other_events.append,
    )

    coordinator = TaskCoordinationCoordinator(
        engine=(
            MultiAgentTaskCoordinationEngine()
        ),
        publisher=(
            TaskCoordinationEventPublisher(
                bus
            )
        ),
    )

    coordinator.create_workflow(
        TaskCoordinationWorkflow(
            workflow_id="isolated-workflow",
            workspace_id=(
                "blockchain-workspace"
            ),
            team_id="team-001",
            name="Isolated workflow",
            objective=(
                "Verify workspace isolation"
            ),
            created_by="planner-agent",
        )
    )

    assert len(blockchain_events) == 1
    assert other_events == []

    assert bus.verify_audit_integrity()
