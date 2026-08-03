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
    TaskCoordinationCoordinator,
    TaskCoordinationEventPublisher,
    TaskCoordinationWorkflow,
    TaskFailurePolicy,
)


def make_system(
    bus: AgentCommunicationBus,
) -> tuple[
    MultiAgentTaskCoordinationEngine,
    TaskCoordinationCoordinator,
]:
    engine = (
        MultiAgentTaskCoordinationEngine()
    )

    coordinator = (
        TaskCoordinationCoordinator(
            engine=engine,
            publisher=(
                TaskCoordinationEventPublisher(
                    bus
                )
            ),
        )
    )

    return engine, coordinator


def make_workflow(
    *,
    workspace_id: str = (
        "blockchain-workspace"
    ),
) -> TaskCoordinationWorkflow:
    return TaskCoordinationWorkflow(
        workflow_id="workflow-001",
        workspace_id=workspace_id,
        team_id="team-001",
        name="Move Module Delivery",
        objective=(
            "Design, implement, and verify "
            "a governed Move module"
        ),
        created_by="planner-agent",
    )


def make_task(
    *,
    task_id: str,
    dependencies: set[str] | None = None,
    failure_policy: TaskFailurePolicy = (
        TaskFailurePolicy.STOP_WORKFLOW
    ),
    maximum_attempts: int = 1,
) -> CoordinatedTask:
    return CoordinatedTask(
        task_id=task_id,
        workflow_id="workflow-001",
        title=f"Task {task_id}",
        description=f"Execute {task_id}",
        required_capabilities={
            "sui_move",
        },
        required_tasks={
            "contract_implementation",
        },
        dependencies=(
            dependencies or set()
        ),
        failure_policy=failure_policy,
        maximum_attempts=maximum_attempts,
    )


def get_task(
    workflow: TaskCoordinationWorkflow,
    task_id: str,
) -> CoordinatedTask:
    return next(
        task
        for task in workflow.tasks
        if task.task_id == task_id
    )


def test_workflow_and_task_events_are_published():
    received: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="task.**",
        agent_id=(
            "task-intelligence-monitor"
        ),
        handler=received.append,
    )

    _, coordinator = make_system(
        bus
    )

    workflow = coordinator.create_workflow(
        make_workflow()
    )

    workflow = coordinator.add_task(
        workflow_id=workflow.workflow_id,
        task=make_task(
            task_id="design",
        ),
    )

    workflow = coordinator.add_task(
        workflow_id=workflow.workflow_id,
        task=make_task(
            task_id="implementation",
            dependencies={"design"},
        ),
    )

    workflow = (
        coordinator.prepare_workflow(
            workflow.workflow_id
        )
    )

    topics = [
        message.topic
        for message in received
    ]

    assert topics == [
        "task.workflow.created",
        "task.added",
        "task.added",
        "task.workflow.prepared",
        "task.blocked",
    ]

    assert (
        get_task(
            workflow,
            "implementation",
        ).status
        is CoordinatedTaskStatus.BLOCKED
    )

    assert bus.verify_audit_integrity()


def test_assignment_start_completion_events_are_published():
    received: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="task.**",
        agent_id="execution-monitor",
        handler=received.append,
    )

    _, coordinator = make_system(
        bus
    )

    workflow = coordinator.create_workflow(
        make_workflow()
    )

    workflow = coordinator.add_task(
        workflow_id=workflow.workflow_id,
        task=make_task(
            task_id="implementation",
        ),
    )

    workflow = (
        coordinator.prepare_workflow(
            workflow.workflow_id
        )
    )

    workflow = coordinator.assign_task(
        workflow_id=workflow.workflow_id,
        task_id="implementation",
        agent_id="move-agent",
        assigned_by="coordinator-agent",
    )

    workflow = coordinator.start_workflow(
        workflow.workflow_id
    )

    workflow = coordinator.start_task(
        workflow_id=workflow.workflow_id,
        task_id="implementation",
    )

    workflow = coordinator.complete_task(
        workflow_id=workflow.workflow_id,
        task_id="implementation",
        result={
            "tests_passed": True,
        },
    )

    assert (
        workflow.status
        is CoordinationStatus.COMPLETED
    )

    assert [
        message.topic
        for message in received[-5:]
    ] == [
        "task.assigned",
        "task.workflow.started",
        "task.started",
        "task.completed",
        "task.workflow.completed",
    ]

    completed_event = received[-2]

    assert (
        completed_event.payload[
            "successful"
        ]
        is True
    )

    assert bus.verify_audit_integrity()


def test_retry_and_failure_events_are_distinct():
    received: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="task.**",
        agent_id="failure-monitor",
        handler=received.append,
    )

    _, coordinator = make_system(
        bus
    )

    workflow = coordinator.create_workflow(
        make_workflow()
    )

    workflow = coordinator.add_task(
        workflow_id=workflow.workflow_id,
        task=make_task(
            task_id="implementation",
            failure_policy=(
                TaskFailurePolicy.RETRY
            ),
            maximum_attempts=2,
        ),
    )

    workflow = (
        coordinator.prepare_workflow(
            workflow.workflow_id
        )
    )

    workflow = coordinator.assign_task(
        workflow_id=workflow.workflow_id,
        task_id="implementation",
        agent_id="move-agent",
        assigned_by="coordinator-agent",
    )

    workflow = coordinator.start_workflow(
        workflow.workflow_id
    )

    workflow = coordinator.start_task(
        workflow_id=workflow.workflow_id,
        task_id="implementation",
    )

    workflow = coordinator.fail_task(
        workflow_id=workflow.workflow_id,
        task_id="implementation",
        error_message="temporary compiler failure",
    )

    assert (
        get_task(
            workflow,
            "implementation",
        ).status
        is CoordinatedTaskStatus
        .RETRY_PENDING
    )

    assert (
        received[-1].topic
        == "task.retry.pending"
    )

    assert (
        "task.workflow.failed"
        not in [
            message.topic
            for message in received
        ]
    )

    assert bus.verify_audit_integrity()


def test_terminal_failure_publishes_workflow_failure():
    received: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="task.**",
        agent_id="governance-monitor",
        handler=received.append,
    )

    _, coordinator = make_system(
        bus
    )

    workflow = coordinator.create_workflow(
        make_workflow()
    )

    workflow = coordinator.add_task(
        workflow_id=workflow.workflow_id,
        task=make_task(
            task_id="security-review",
            failure_policy=(
                TaskFailurePolicy
                .STOP_WORKFLOW
            ),
        ),
    )

    workflow = (
        coordinator.prepare_workflow(
            workflow.workflow_id
        )
    )

    workflow = coordinator.assign_task(
        workflow_id=workflow.workflow_id,
        task_id="security-review",
        agent_id="security-agent",
        assigned_by="coordinator-agent",
    )

    workflow = coordinator.start_workflow(
        workflow.workflow_id
    )

    workflow = coordinator.start_task(
        workflow_id=workflow.workflow_id,
        task_id="security-review",
    )

    workflow = coordinator.fail_task(
        workflow_id=workflow.workflow_id,
        task_id="security-review",
        error_message=(
            "critical invariant violation"
        ),
    )

    assert (
        workflow.status
        is CoordinationStatus.FAILED
    )

    assert [
        message.topic
        for message in received[-2:]
    ] == [
        "task.failed",
        "task.workflow.failed",
    ]

    assert bus.verify_audit_integrity()


def test_task_events_are_workspace_isolated():
    blockchain_events: list[
        AgentMessage
    ] = []

    gsos_events: list[
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
        agent_id="gsos-monitor",
        workspace_id="gsos-workspace",
        handler=gsos_events.append,
    )

    _, coordinator = make_system(
        bus
    )

    coordinator.create_workflow(
        make_workflow(
            workspace_id=(
                "blockchain-workspace"
            )
        )
    )

    assert len(blockchain_events) == 1
    assert gsos_events == []

    assert bus.verify_audit_integrity()


def test_workflow_cancellation_event_is_published():
    received: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="task.**",
        agent_id="audit-agent",
        handler=received.append,
    )

    _, coordinator = make_system(
        bus
    )

    workflow = coordinator.create_workflow(
        make_workflow()
    )

    workflow = coordinator.add_task(
        workflow_id=workflow.workflow_id,
        task=make_task(
            task_id="design",
        ),
    )

    workflow = (
        coordinator.prepare_workflow(
            workflow.workflow_id
        )
    )

    cancelled = (
        coordinator.cancel_workflow(
            workflow.workflow_id
        )
    )

    assert (
        cancelled.status
        is CoordinationStatus.CANCELLED
    )

    assert (
        received[-1].topic
        == "task.workflow.cancelled"
    )

    assert bus.verify_audit_integrity()
