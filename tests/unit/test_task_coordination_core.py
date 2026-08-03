from __future__ import annotations

import pytest

from af_core.organization import (
    CoordinatedTask,
    CoordinatedTaskStatus,
    CoordinationStatus,
    MultiAgentTaskCoordinationEngine,
    TaskCoordinationWorkflow,
    TaskFailurePolicy,
)


def make_workflow() -> TaskCoordinationWorkflow:
    return TaskCoordinationWorkflow(
        workflow_id="workflow-001",
        workspace_id="blockchain-workspace",
        team_id="team-001",
        name="Sui Move Delivery",
        objective=(
            "Design, implement, test, and review "
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


def test_workflow_can_be_created():

    engine = (
        MultiAgentTaskCoordinationEngine()
    )

    workflow = engine.create_workflow(
        make_workflow()
    )

    assert (
        workflow.status
        is CoordinationStatus.CREATED
    )

    assert engine.workflow_count == 1


def test_tasks_can_be_added_and_prepared():

    engine = (
        MultiAgentTaskCoordinationEngine()
    )

    workflow = engine.create_workflow(
        make_workflow()
    )

    workflow = engine.add_task(
        workflow_id=workflow.workflow_id,
        task=make_task(
            task_id="design",
        ),
    )

    workflow = engine.add_task(
        workflow_id=workflow.workflow_id,
        task=make_task(
            task_id="implementation",
            dependencies={"design"},
        ),
    )

    prepared = engine.prepare_workflow(
        workflow.workflow_id
    )

    assert (
        prepared.status
        is CoordinationStatus.READY
    )

    assert (
        get_task(
            prepared,
            "design",
        ).status
        is CoordinatedTaskStatus.READY
    )

    assert (
        get_task(
            prepared,
            "implementation",
        ).status
        is CoordinatedTaskStatus.BLOCKED
    )


def test_unknown_dependency_is_rejected():

    engine = (
        MultiAgentTaskCoordinationEngine()
    )

    workflow = engine.create_workflow(
        make_workflow()
    )

    engine.add_task(
        workflow_id=workflow.workflow_id,
        task=make_task(
            task_id="implementation",
            dependencies={"missing-task"},
        ),
    )

    with pytest.raises(
        ValueError,
        match="unknown dependencies",
    ):
        engine.prepare_workflow(
            workflow.workflow_id
        )


def test_ready_task_can_be_assigned_and_started():

    engine = (
        MultiAgentTaskCoordinationEngine()
    )

    workflow = engine.create_workflow(
        make_workflow()
    )

    workflow = engine.add_task(
        workflow_id=workflow.workflow_id,
        task=make_task(
            task_id="design",
        ),
    )

    workflow = engine.prepare_workflow(
        workflow.workflow_id
    )

    workflow = engine.assign_task(
        workflow_id=workflow.workflow_id,
        task_id="design",
        agent_id="architecture-agent",
        assigned_by="coordinator-agent",
        assignment_score=95.0,
        matched_capabilities={
            "architecture",
        },
        matched_tasks={
            "system_design",
        },
    )

    assigned = get_task(
        workflow,
        "design",
    )

    assert (
        assigned.status
        is CoordinatedTaskStatus.ASSIGNED
    )

    assert (
        assigned.assigned_agent_id
        == "architecture-agent"
    )

    workflow = engine.start_workflow(
        workflow.workflow_id
    )

    workflow = engine.start_task(
        workflow_id=workflow.workflow_id,
        task_id="design",
    )

    running = get_task(
        workflow,
        "design",
    )

    assert (
        running.status
        is CoordinatedTaskStatus.RUNNING
    )

    assert running.attempt_count == 1
    assert len(workflow.execution_records) == 1


def test_completion_releases_dependent_task():

    engine = (
        MultiAgentTaskCoordinationEngine()
    )

    workflow = engine.create_workflow(
        make_workflow()
    )

    for task in (
        make_task(
            task_id="design",
        ),
        make_task(
            task_id="implementation",
            dependencies={"design"},
        ),
    ):
        workflow = engine.add_task(
            workflow_id=workflow.workflow_id,
            task=task,
        )

    workflow = engine.prepare_workflow(
        workflow.workflow_id
    )

    workflow = engine.assign_task(
        workflow_id=workflow.workflow_id,
        task_id="design",
        agent_id="architecture-agent",
        assigned_by="coordinator-agent",
    )

    workflow = engine.start_workflow(
        workflow.workflow_id
    )

    workflow = engine.start_task(
        workflow_id=workflow.workflow_id,
        task_id="design",
    )

    workflow = engine.complete_task(
        workflow_id=workflow.workflow_id,
        task_id="design",
        result={
            "architecture": "approved",
        },
    )

    design = get_task(
        workflow,
        "design",
    )

    implementation = get_task(
        workflow,
        "implementation",
    )

    assert (
        design.status
        is CoordinatedTaskStatus.COMPLETED
    )

    assert (
        implementation.status
        is CoordinatedTaskStatus.READY
    )

    assert (
        implementation.blocked_reason
        is None
    )


def test_completed_workflow_is_finalized():

    engine = (
        MultiAgentTaskCoordinationEngine()
    )

    workflow = engine.create_workflow(
        make_workflow()
    )

    workflow = engine.add_task(
        workflow_id=workflow.workflow_id,
        task=make_task(
            task_id="design",
        ),
    )

    workflow = engine.prepare_workflow(
        workflow.workflow_id
    )

    workflow = engine.assign_task(
        workflow_id=workflow.workflow_id,
        task_id="design",
        agent_id="architecture-agent",
        assigned_by="coordinator-agent",
    )

    workflow = engine.start_workflow(
        workflow.workflow_id
    )

    workflow = engine.start_task(
        workflow_id=workflow.workflow_id,
        task_id="design",
    )

    workflow = engine.complete_task(
        workflow_id=workflow.workflow_id,
        task_id="design",
        result={
            "completed": True,
        },
    )

    assert (
        workflow.status
        is CoordinationStatus.COMPLETED
    )

    assert workflow.completed_at is not None
    assert workflow.progress_ratio == 1.0


def test_retry_policy_moves_task_to_retry_pending():

    engine = (
        MultiAgentTaskCoordinationEngine()
    )

    workflow = engine.create_workflow(
        make_workflow()
    )

    workflow = engine.add_task(
        workflow_id=workflow.workflow_id,
        task=make_task(
            task_id="implementation",
            failure_policy=(
                TaskFailurePolicy.RETRY
            ),
            maximum_attempts=2,
        ),
    )

    workflow = engine.prepare_workflow(
        workflow.workflow_id
    )

    workflow = engine.assign_task(
        workflow_id=workflow.workflow_id,
        task_id="implementation",
        agent_id="move-agent",
        assigned_by="coordinator-agent",
    )

    workflow = engine.start_workflow(
        workflow.workflow_id
    )

    workflow = engine.start_task(
        workflow_id=workflow.workflow_id,
        task_id="implementation",
    )

    workflow = engine.fail_task(
        workflow_id=workflow.workflow_id,
        task_id="implementation",
        error_message="temporary failure",
    )

    task = get_task(
        workflow,
        "implementation",
    )

    assert (
        task.status
        is CoordinatedTaskStatus.RETRY_PENDING
    )

    assert (
        workflow.status
        is CoordinationStatus.RUNNING
    )

    assert (
        workflow.execution_records[0]
        .successful
        is False
    )


def test_stop_workflow_failure_marks_workflow_failed():

    engine = (
        MultiAgentTaskCoordinationEngine()
    )

    workflow = engine.create_workflow(
        make_workflow()
    )

    workflow = engine.add_task(
        workflow_id=workflow.workflow_id,
        task=make_task(
            task_id="security-review",
            failure_policy=(
                TaskFailurePolicy.STOP_WORKFLOW
            ),
        ),
    )

    workflow = engine.prepare_workflow(
        workflow.workflow_id
    )

    workflow = engine.assign_task(
        workflow_id=workflow.workflow_id,
        task_id="security-review",
        agent_id="security-agent",
        assigned_by="coordinator-agent",
    )

    workflow = engine.start_workflow(
        workflow.workflow_id
    )

    workflow = engine.start_task(
        workflow_id=workflow.workflow_id,
        task_id="security-review",
    )

    workflow = engine.fail_task(
        workflow_id=workflow.workflow_id,
        task_id="security-review",
        error_message="critical security failure",
    )

    assert (
        workflow.status
        is CoordinationStatus.FAILED
    )

    assert workflow.completed_at is not None


def test_coordination_result_groups_task_states():

    engine = (
        MultiAgentTaskCoordinationEngine()
    )

    workflow = engine.create_workflow(
        make_workflow()
    )

    for task in (
        make_task(
            task_id="design",
        ),
        make_task(
            task_id="implementation",
            dependencies={"design"},
        ),
    ):
        workflow = engine.add_task(
            workflow_id=workflow.workflow_id,
            task=task,
        )

    engine.prepare_workflow(
        workflow.workflow_id
    )

    result = engine.coordination_result(
        workflow.workflow_id
    )

    assert result.ready_task_ids == [
        "design"
    ]

    assert result.blocked_task_ids == [
        "implementation"
    ]

    assert result.running_task_ids == []
    assert result.completed_task_ids == []
    assert result.failed_task_ids == []


def test_workflow_can_be_cancelled():

    engine = (
        MultiAgentTaskCoordinationEngine()
    )

    workflow = engine.create_workflow(
        make_workflow()
    )

    workflow = engine.add_task(
        workflow_id=workflow.workflow_id,
        task=make_task(
            task_id="design",
        ),
    )

    workflow = engine.prepare_workflow(
        workflow.workflow_id
    )

    cancelled = engine.cancel_workflow(
        workflow.workflow_id
    )

    assert (
        cancelled.status
        is CoordinationStatus.CANCELLED
    )

    assert (
        cancelled.tasks[0].status
        is CoordinatedTaskStatus.CANCELLED
    )

    assert cancelled.completed_at is not None
