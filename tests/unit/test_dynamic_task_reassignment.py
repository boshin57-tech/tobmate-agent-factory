from __future__ import annotations

from af_core.organization import (
    CoordinatedTask,
    CoordinatedTaskStatus,
    CoordinationStatus,
    DynamicTaskReassignmentEngine,
    MultiAgentTaskCoordinationEngine,
    TaskAgentAvailability,
    TaskAgentRuntimeProfile,
    TaskAssignment,
    TaskCoordinationWorkflow,
    TaskReassignmentDecision,
    TaskReassignmentReason,
    TaskReassignmentRequest,
    TaskRuntimeProfileRepository,
    TaskWorkloadBalancingEngine,
)


def make_profile(
    agent_id: str,
    *,
    availability: TaskAgentAvailability = (
        TaskAgentAvailability.AVAILABLE
    ),
    current_task_count: int = 0,
    maximum_task_count: int = 4,
    workload_ratio: float = 0.0,
    capabilities: set[str] | None = None,
) -> TaskAgentRuntimeProfile:
    return TaskAgentRuntimeProfile(
        agent_id=agent_id,
        capabilities=(
            capabilities
            if capabilities is not None
            else {
                "sui_move",
                "smart_contract",
            }
        ),
        supported_tasks={
            "contract_implementation",
        },
        availability=availability,
        current_task_count=(
            current_task_count
        ),
        maximum_task_count=(
            maximum_task_count
        ),
        workload_ratio=workload_ratio,
        success_rate=0.95,
        quality_score=95.0,
        reliability_score=95.0,
    )


def make_task(
    *,
    assigned_agent_id: str = (
        "primary-agent"
    ),
    status: CoordinatedTaskStatus = (
        CoordinatedTaskStatus.ASSIGNED
    ),
) -> CoordinatedTask:
    return CoordinatedTask(
        task_id="implementation",
        workflow_id="workflow-001",
        title="Implement protocol",
        description=(
            "Implement governed Move protocol"
        ),
        required_capabilities={
            "sui_move",
            "smart_contract",
        },
        required_tasks={
            "contract_implementation",
        },
        assigned_agent_id=(
            assigned_agent_id
        ),
        status=status,
    )


def make_workflow(
    task: CoordinatedTask,
) -> TaskCoordinationWorkflow:
    assignment = TaskAssignment(
        workflow_id="workflow-001",
        task_id=task.task_id,
        agent_id=(
            task.assigned_agent_id
            or "unassigned"
        ),
        assigned_by="coordinator-agent",
    )

    return TaskCoordinationWorkflow(
        workflow_id="workflow-001",
        workspace_id="workspace-001",
        team_id="team-001",
        name="Protocol workflow",
        objective="Complete protocol",
        created_by="planner-agent",
        status=CoordinationStatus.RUNNING,
        tasks=[task],
        assignments=[assignment],
    )


def make_reassignment_engine(
    profiles: list[
        TaskAgentRuntimeProfile
    ],
) -> DynamicTaskReassignmentEngine:
    balancer = TaskWorkloadBalancingEngine(
        agent_provider=lambda: profiles
    )

    return DynamicTaskReassignmentEngine(
        workload_balancer=balancer,
        agent_provider=lambda: profiles,
    )


def test_offline_agent_is_reassigned():
    profiles = [
        make_profile(
            "primary-agent",
            availability=(
                TaskAgentAvailability.OFFLINE
            ),
            current_task_count=1,
            workload_ratio=0.25,
        ),
        make_profile(
            "replacement-agent",
        ),
    ]

    engine = make_reassignment_engine(
        profiles
    )

    workflow = make_workflow(
        make_task()
    )

    updated, result = engine.execute(
        workflow=workflow,
        request=TaskReassignmentRequest(
            workflow_id=(
                workflow.workflow_id
            ),
            task_id="implementation",
            requested_by="coordinator-agent",
            reason=(
                TaskReassignmentReason
                .AGENT_OFFLINE
            ),
        ),
    )

    assert result.completed

    assert (
        result.replacement_agent_id
        == "replacement-agent"
    )

    assert (
        updated.tasks[0]
        .assigned_agent_id
        == "replacement-agent"
    )

    assert (
        updated.tasks[0].status
        is CoordinatedTaskStatus.ASSIGNED
    )

    assert (
        updated.assignments[0].agent_id
        == "replacement-agent"
    )


def test_overloaded_agent_is_reassigned():
    profiles = [
        make_profile(
            "primary-agent",
            availability=(
                TaskAgentAvailability
                .OVERLOADED
            ),
            current_task_count=4,
            maximum_task_count=4,
            workload_ratio=1.0,
        ),
        make_profile(
            "replacement-agent",
            current_task_count=0,
            workload_ratio=0.0,
        ),
    ]

    engine = make_reassignment_engine(
        profiles
    )

    workflow = make_workflow(
        make_task()
    )

    updated, result = engine.execute(
        workflow=workflow,
        request=TaskReassignmentRequest(
            workflow_id=(
                workflow.workflow_id
            ),
            task_id="implementation",
            requested_by="coordinator-agent",
            reason=(
                TaskReassignmentReason
                .AGENT_OVERLOADED
            ),
        ),
    )

    assert result.completed

    assert (
        updated.tasks[0]
        .assigned_agent_id
        == "replacement-agent"
    )


def test_current_agent_is_not_selected_again():
    profiles = [
        make_profile(
            "primary-agent",
        ),
        make_profile(
            "replacement-agent",
            workload_ratio=0.2,
        ),
    ]

    engine = make_reassignment_engine(
        profiles
    )

    workflow = make_workflow(
        make_task()
    )

    _, result = engine.execute(
        workflow=workflow,
        request=TaskReassignmentRequest(
            workflow_id=(
                workflow.workflow_id
            ),
            task_id="implementation",
            requested_by="manager-agent",
            reason=(
                TaskReassignmentReason
                .MANUAL_REQUEST
            ),
            force=True,
        ),
    )

    assert result.completed

    assert (
        result.replacement_agent_id
        != "primary-agent"
    )


def test_no_replacement_marks_task_blocked():
    profiles = [
        make_profile(
            "primary-agent",
            availability=(
                TaskAgentAvailability.OFFLINE
            ),
            current_task_count=1,
            workload_ratio=0.25,
        )
    ]

    engine = make_reassignment_engine(
        profiles
    )

    workflow = make_workflow(
        make_task()
    )

    updated, result = engine.execute(
        workflow=workflow,
        request=TaskReassignmentRequest(
            workflow_id=(
                workflow.workflow_id
            ),
            task_id="implementation",
            requested_by="coordinator-agent",
            reason=(
                TaskReassignmentReason
                .AGENT_OFFLINE
            ),
        ),
    )

    assert not result.completed

    assert (
        result.record.decision
        is TaskReassignmentDecision.BLOCKED
    )

    assert (
        updated.tasks[0].status
        is CoordinatedTaskStatus.BLOCKED
    )

    assert (
        "no eligible replacement"
        in updated.tasks[0].blocked_reason
    )


def test_failed_task_without_replacement_escalates():
    profiles = [
        make_profile(
            "primary-agent",
            availability=(
                TaskAgentAvailability.OFFLINE
            ),
        )
    ]

    engine = make_reassignment_engine(
        profiles
    )

    workflow = make_workflow(
        make_task(
            status=(
                CoordinatedTaskStatus
                .RETRY_PENDING
            )
        )
    )

    _, result = engine.execute(
        workflow=workflow,
        request=TaskReassignmentRequest(
            workflow_id=(
                workflow.workflow_id
            ),
            task_id="implementation",
            requested_by="coordinator-agent",
            reason=(
                TaskReassignmentReason
                .TASK_FAILURE
            ),
        ),
    )

    assert not result.completed

    assert (
        result.record.decision
        is TaskReassignmentDecision.ESCALATE
    )


def test_reassignment_history_is_preserved():
    profiles = [
        make_profile(
            "primary-agent",
            availability=(
                TaskAgentAvailability.OFFLINE
            ),
        ),
        make_profile(
            "replacement-agent",
        ),
    ]

    engine = make_reassignment_engine(
        profiles
    )

    workflow = make_workflow(
        make_task()
    )

    _, result = engine.execute(
        workflow=workflow,
        request=TaskReassignmentRequest(
            workflow_id=(
                workflow.workflow_id
            ),
            task_id="implementation",
            requested_by="coordinator-agent",
            reason=(
                TaskReassignmentReason
                .AGENT_OFFLINE
            ),
        ),
    )

    history = engine.history(
        workflow_id=(
            workflow.workflow_id
        ),
        task_id="implementation",
    )

    assert engine.history_count == 1
    assert len(history) == 1

    assert (
        history[0].reassignment_id
        == result.record.reassignment_id
    )


def test_coordination_engine_auto_assignment_updates_count():
    repository = (
        TaskRuntimeProfileRepository()
    )

    repository.register(
        make_profile(
            "move-agent",
            current_task_count=0,
            maximum_task_count=4,
            workload_ratio=0.0,
        )
    )

    engine = (
        MultiAgentTaskCoordinationEngine(
            runtime_profiles=repository
        )
    )

    workflow = engine.create_workflow(
        TaskCoordinationWorkflow(
            workflow_id="workflow-001",
            workspace_id="workspace-001",
            team_id="team-001",
            name="Auto assignment",
            objective="Assign task",
            created_by="planner-agent",
        )
    )

    workflow = engine.add_task(
        workflow_id=workflow.workflow_id,
        task=make_task(
            assigned_agent_id=""
        ).model_copy(
            update={
                "assigned_agent_id":
                    None,
                "status":
                    CoordinatedTaskStatus
                    .CREATED,
            }
        ),
    )

    workflow = engine.prepare_workflow(
        workflow.workflow_id
    )

    workflow, selection = (
        engine.automatically_assign_task(
            workflow_id=(
                workflow.workflow_id
            ),
            task_id="implementation",
            assigned_by="coordinator-agent",
        )
    )

    assert selection.fulfilled

    assert (
        workflow.tasks[0]
        .assigned_agent_id
        == "move-agent"
    )

    runtime = engine.runtime_profile(
        "move-agent"
    )

    assert runtime is not None
    assert runtime.current_task_count == 1
    assert runtime.workload_ratio == 0.25


def test_coordination_engine_reassignment_syncs_counts():
    repository = (
        TaskRuntimeProfileRepository()
    )

    repository.register(
        make_profile(
            "primary-agent",
            availability=(
                TaskAgentAvailability.OFFLINE
            ),
            current_task_count=1,
            maximum_task_count=4,
            workload_ratio=0.25,
        )
    )

    repository.register(
        make_profile(
            "replacement-agent",
            current_task_count=0,
            maximum_task_count=4,
            workload_ratio=0.0,
        )
    )

    engine = (
        MultiAgentTaskCoordinationEngine(
            runtime_profiles=repository
        )
    )

    workflow = engine.create_workflow(
        make_workflow(
            make_task()
        ).model_copy(
            update={
                "status":
                    CoordinationStatus.CREATED,
            }
        )
    )

    result = engine.reassign_task(
        TaskReassignmentRequest(
            workflow_id=(
                workflow.workflow_id
            ),
            task_id="implementation",
            requested_by="coordinator-agent",
            reason=(
                TaskReassignmentReason
                .AGENT_OFFLINE
            ),
        )
    )

    assert result.completed

    primary = engine.runtime_profile(
        "primary-agent"
    )

    replacement = engine.runtime_profile(
        "replacement-agent"
    )

    assert primary is not None
    assert replacement is not None

    assert primary.current_task_count == 0
    assert replacement.current_task_count == 1

    stored = engine.get_workflow(
        workflow.workflow_id
    )

    assert stored is not None

    assert (
        stored.tasks[0]
        .assigned_agent_id
        == "replacement-agent"
    )
