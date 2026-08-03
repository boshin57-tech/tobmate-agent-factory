from __future__ import annotations

import pytest

from af_core.organization import (
    MultiAgentWorkflowOrchestrationEngine,
    OrchestratedWorkflow,
    OrchestratedWorkflowStatus,
    OrchestrationStatus,
    WorkflowFailurePolicy,
    WorkflowOrchestration,
)


def make_orchestration() -> (
    WorkflowOrchestration
):
    return WorkflowOrchestration(
        orchestration_id=(
            "orchestration-001"
        ),
        workspace_id="workspace-001",
        name="Platform delivery",
        objective=(
            "Coordinate design, implementation, "
            "security, and release workflows"
        ),
        created_by="planner-agent",
    )


def make_workflow(
    workflow_id: str,
    *,
    dependencies: set[str] | None = None,
    failure_policy: WorkflowFailurePolicy = (
        WorkflowFailurePolicy
        .STOP_ORCHESTRATION
    ),
    maximum_attempts: int = 1,
) -> OrchestratedWorkflow:
    return OrchestratedWorkflow(
        orchestration_id=(
            "orchestration-001"
        ),
        workflow_id=workflow_id,
        workspace_id="workspace-001",
        team_id=f"team-{workflow_id}",
        name=f"Workflow {workflow_id}",
        objective=f"Execute {workflow_id}",
        dependencies=(
            dependencies or set()
        ),
        failure_policy=failure_policy,
        maximum_attempts=maximum_attempts,
    )


def get_workflow(
    orchestration: WorkflowOrchestration,
    workflow_id: str,
) -> OrchestratedWorkflow:
    return next(
        workflow
        for workflow
        in orchestration.workflows
        if workflow.workflow_id
        == workflow_id
    )


def create_with_workflows(
    *workflows: OrchestratedWorkflow,
) -> tuple[
    MultiAgentWorkflowOrchestrationEngine,
    WorkflowOrchestration,
]:
    engine = (
        MultiAgentWorkflowOrchestrationEngine()
    )

    orchestration = (
        engine.create_orchestration(
            make_orchestration()
        )
    )

    for workflow in workflows:
        orchestration = (
            engine.register_workflow(
                orchestration_id=(
                    orchestration
                    .orchestration_id
                ),
                workflow=workflow,
            )
        )

    return engine, orchestration


def test_orchestration_can_be_created():
    engine = (
        MultiAgentWorkflowOrchestrationEngine()
    )

    orchestration = (
        engine.create_orchestration(
            make_orchestration()
        )
    )

    assert (
        orchestration.status
        is OrchestrationStatus.CREATED
    )

    assert engine.orchestration_count == 1


def test_workflows_can_be_registered_and_prepared():
    engine, orchestration = (
        create_with_workflows(
            make_workflow("design"),
            make_workflow(
                "implementation",
                dependencies={"design"},
            ),
        )
    )

    orchestration = (
        engine.prepare_orchestration(
            orchestration
            .orchestration_id
        )
    )

    assert (
        orchestration.status
        is OrchestrationStatus.READY
    )

    assert (
        get_workflow(
            orchestration,
            "design",
        ).status
        is OrchestratedWorkflowStatus.READY
    )

    assert (
        get_workflow(
            orchestration,
            "implementation",
        ).status
        is OrchestratedWorkflowStatus.WAITING
    )


def test_unknown_dependency_is_rejected():
    engine, orchestration = (
        create_with_workflows(
            make_workflow(
                "implementation",
                dependencies={"missing"},
            )
        )
    )

    with pytest.raises(
        ValueError,
        match="unknown dependencies",
    ):
        engine.prepare_orchestration(
            orchestration.orchestration_id
        )


def test_workflow_completion_releases_dependency():
    engine, orchestration = (
        create_with_workflows(
            make_workflow("design"),
            make_workflow(
                "implementation",
                dependencies={"design"},
            ),
        )
    )

    orchestration = (
        engine.prepare_orchestration(
            orchestration
            .orchestration_id
        )
    )

    orchestration = (
        engine.start_orchestration(
            orchestration
            .orchestration_id
        )
    )

    orchestration = engine.start_workflow(
        orchestration_id=(
            orchestration.orchestration_id
        ),
        workflow_id="design",
    )

    orchestration = (
        engine.complete_workflow(
            orchestration_id=(
                orchestration
                .orchestration_id
            ),
            workflow_id="design",
            result={
                "approved": True,
            },
        )
    )

    assert (
        get_workflow(
            orchestration,
            "design",
        ).status
        is OrchestratedWorkflowStatus
        .COMPLETED
    )

    assert (
        get_workflow(
            orchestration,
            "implementation",
        ).status
        is OrchestratedWorkflowStatus.READY
    )


def test_completed_workflows_finalize_orchestration():
    engine, orchestration = (
        create_with_workflows(
            make_workflow("design")
        )
    )

    orchestration = (
        engine.prepare_orchestration(
            orchestration.orchestration_id
        )
    )

    orchestration = (
        engine.start_orchestration(
            orchestration.orchestration_id
        )
    )

    orchestration = engine.start_workflow(
        orchestration_id=(
            orchestration.orchestration_id
        ),
        workflow_id="design",
    )

    orchestration = (
        engine.complete_workflow(
            orchestration_id=(
                orchestration
                .orchestration_id
            ),
            workflow_id="design",
        )
    )

    assert (
        orchestration.status
        is OrchestrationStatus.COMPLETED
    )

    assert orchestration.completed_at is not None
    assert orchestration.progress_ratio == 1.0


def test_retry_policy_returns_workflow_to_ready():
    engine, orchestration = (
        create_with_workflows(
            make_workflow(
                "implementation",
                failure_policy=(
                    WorkflowFailurePolicy
                    .RETRY_WORKFLOW
                ),
                maximum_attempts=2,
            )
        )
    )

    orchestration = (
        engine.prepare_orchestration(
            orchestration.orchestration_id
        )
    )

    orchestration = (
        engine.start_orchestration(
            orchestration.orchestration_id
        )
    )

    orchestration = engine.start_workflow(
        orchestration_id=(
            orchestration.orchestration_id
        ),
        workflow_id="implementation",
    )

    orchestration = engine.fail_workflow(
        orchestration_id=(
            orchestration.orchestration_id
        ),
        workflow_id="implementation",
        error_message="temporary failure",
    )

    workflow = get_workflow(
        orchestration,
        "implementation",
    )

    assert (
        workflow.status
        is OrchestratedWorkflowStatus.READY
    )

    assert workflow.attempt_count == 1

    assert (
        orchestration.status
        is OrchestrationStatus.RUNNING
    )


def test_terminal_failure_fails_orchestration():
    engine, orchestration = (
        create_with_workflows(
            make_workflow(
                "security",
                failure_policy=(
                    WorkflowFailurePolicy
                    .STOP_ORCHESTRATION
                ),
            )
        )
    )

    orchestration = (
        engine.prepare_orchestration(
            orchestration.orchestration_id
        )
    )

    orchestration = (
        engine.start_orchestration(
            orchestration.orchestration_id
        )
    )

    orchestration = engine.start_workflow(
        orchestration_id=(
            orchestration.orchestration_id
        ),
        workflow_id="security",
    )

    orchestration = engine.fail_workflow(
        orchestration_id=(
            orchestration.orchestration_id
        ),
        workflow_id="security",
        error_message=(
            "critical security failure"
        ),
    )

    assert (
        orchestration.status
        is OrchestrationStatus.FAILED
    )

    assert orchestration.completed_at is not None


def test_pause_and_resume_lifecycle():
    engine, orchestration = (
        create_with_workflows(
            make_workflow("design")
        )
    )

    orchestration = (
        engine.prepare_orchestration(
            orchestration.orchestration_id
        )
    )

    orchestration = (
        engine.start_orchestration(
            orchestration.orchestration_id
        )
    )

    orchestration = engine.start_workflow(
        orchestration_id=(
            orchestration.orchestration_id
        ),
        workflow_id="design",
    )

    orchestration = (
        engine.pause_orchestration(
            orchestration.orchestration_id,
            reason="maintenance window",
        )
    )

    assert (
        orchestration.status
        is OrchestrationStatus.PAUSED
    )

    assert (
        get_workflow(
            orchestration,
            "design",
        ).status
        is OrchestratedWorkflowStatus.PAUSED
    )

    orchestration = (
        engine.resume_orchestration(
            orchestration.orchestration_id
        )
    )

    assert (
        orchestration.status
        is OrchestrationStatus.RUNNING
    )

    assert (
        get_workflow(
            orchestration,
            "design",
        ).status
        is OrchestratedWorkflowStatus.READY
    )


def test_checkpoint_captures_current_state():
    engine, orchestration = (
        create_with_workflows(
            make_workflow("design"),
            make_workflow(
                "implementation",
                dependencies={"design"},
            ),
        )
    )

    orchestration = (
        engine.prepare_orchestration(
            orchestration.orchestration_id
        )
    )

    checkpoint = engine.create_checkpoint(
        orchestration.orchestration_id,
        metadata={
            "reason": "pre-execution",
        },
    )

    assert (
        checkpoint.orchestration_status
        is OrchestrationStatus.READY
    )

    assert (
        checkpoint.workflow_statuses[
            "design"
        ]
        is OrchestratedWorkflowStatus.READY
    )

    assert (
        checkpoint.workflow_statuses[
            "implementation"
        ]
        is OrchestratedWorkflowStatus.WAITING
    )

    assert (
        engine.latest_checkpoint(
            orchestration.orchestration_id
        )
        == checkpoint
    )


def test_orchestration_result_groups_statuses():
    engine, orchestration = (
        create_with_workflows(
            make_workflow("design"),
            make_workflow(
                "implementation",
                dependencies={"design"},
            ),
        )
    )

    engine.prepare_orchestration(
        orchestration.orchestration_id
    )

    result = engine.orchestration_result(
        orchestration.orchestration_id
    )

    assert result.ready_workflow_ids == [
        "design"
    ]

    assert result.running_workflow_ids == []

    assert result.blocked_workflow_ids == []

    assert result.completed_workflow_ids == []

    assert result.failed_workflow_ids == []


def test_orchestration_can_be_cancelled():
    engine, orchestration = (
        create_with_workflows(
            make_workflow("design")
        )
    )

    orchestration = (
        engine.prepare_orchestration(
            orchestration.orchestration_id
        )
    )

    cancelled = (
        engine.cancel_orchestration(
            orchestration.orchestration_id
        )
    )

    assert (
        cancelled.status
        is OrchestrationStatus.CANCELLED
    )

    assert (
        cancelled.workflows[0].status
        is OrchestratedWorkflowStatus
        .CANCELLED
    )

    assert cancelled.completed_at is not None
