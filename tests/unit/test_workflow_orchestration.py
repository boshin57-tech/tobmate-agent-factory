from __future__ import annotations

import pytest

from af_core.orchestrator.workflow_models import (
    WorkflowDefinition,
    WorkflowStatus,
    WorkflowStep,
    WorkflowStepStatus,
)
from af_core.orchestrator.workflow_registry import (
    WorkflowRegistry,
    WorkflowRegistryError,
)
from af_core.orchestrator.workflow_engine import (
    WorkflowEngine,
    WorkflowEngineError,
)


def build_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="deploy-flow",
        name="Deployment Workflow",
        version=1,
        steps=(
            WorkflowStep(
                step_id="build",
                name="Build",
            ),
            WorkflowStep(
                step_id="test",
                name="Test",
                dependency_ids=frozenset(
                    {"build"}
                ),
                maximum_attempts=2,
            ),
            WorkflowStep(
                step_id="deploy",
                name="Deploy",
                dependency_ids=frozenset(
                    {"test"}
                ),
                compensation_step_id="rollback",
            ),
            WorkflowStep(
                step_id="rollback",
                name="Rollback",
            ),
        ),
    )


def test_workflow_registry_registers_valid_dag() -> None:
    registry = WorkflowRegistry()

    workflow = build_workflow()

    registered = registry.register(workflow)

    assert registered.workflow_id == (
        "deploy-flow"
    )
    assert registry.topological_order(
        "deploy-flow"
    ) == (
        "build",
        "rollback",
        "test",
        "deploy",
    )


def test_registry_rejects_unknown_dependency() -> None:
    registry = WorkflowRegistry()

    workflow = WorkflowDefinition(
        workflow_id="invalid",
        name="Invalid",
        steps=(
            WorkflowStep(
                step_id="step-a",
                name="A",
                dependency_ids=frozenset(
                    {"missing"}
                ),
            ),
        ),
    )

    with pytest.raises(
        WorkflowRegistryError,
        match="Unknown workflow dependencies",
    ):
        registry.register(workflow)


def test_registry_rejects_cycle() -> None:
    registry = WorkflowRegistry()

    workflow = WorkflowDefinition(
        workflow_id="cycle",
        name="Cycle",
        steps=(
            WorkflowStep(
                step_id="a",
                name="A",
                dependency_ids=frozenset({"b"}),
            ),
            WorkflowStep(
                step_id="b",
                name="B",
                dependency_ids=frozenset({"a"}),
            ),
        ),
    )

    with pytest.raises(
        WorkflowRegistryError,
        match="cycle",
    ):
        registry.register(workflow)


def test_create_and_start_workflow_run() -> None:
    engine = WorkflowEngine()

    run = engine.create_run(
        build_workflow()
    )

    assert run.status is (
        WorkflowStatus.PENDING
    )

    started = engine.start_run(
        run.run_id
    )

    assert started.status is (
        WorkflowStatus.RUNNING
    )


def test_ready_steps_follow_dependencies() -> None:
    engine = WorkflowEngine()

    run = engine.create_run(
        build_workflow()
    )

    engine.start_run(run.run_id)

    ready = engine.ready_steps(
        run.run_id
    )

    assert tuple(
        step.step_id
        for step in ready
    ) == ("build",)


def test_schedule_ready_creates_decisions() -> None:
    engine = WorkflowEngine()

    run = engine.create_run(
        build_workflow()
    )

    engine.start_run(run.run_id)

    decisions = engine.schedule_ready(
        run.run_id
    )

    assert len(decisions) == 1
    assert decisions[0].step_id == "build"


def test_schedule_requires_running_state() -> None:
    engine = WorkflowEngine()

    run = engine.create_run(
        build_workflow()
    )

    with pytest.raises(
        WorkflowEngineError,
        match="must be running",
    ):
        engine.schedule_ready(run.run_id)


def test_successful_step_completion() -> None:
    engine = WorkflowEngine()

    run = engine.create_run(
        build_workflow()
    )

    engine.start_run(run.run_id)

    result = engine.execute_step(
        run_id=run.run_id,
        step_id="build",
        success=True,
    )

    step = next(
        item
        for item in result.steps
        if item.step_id == "build"
    )

    assert step.status is (
        WorkflowStepStatus.COMPLETED
    )


def test_failed_step_enters_retry_state() -> None:
    engine = WorkflowEngine()

    run = engine.create_run(
        build_workflow()
    )

    engine.start_run(run.run_id)

    engine.execute_step(
        run_id=run.run_id,
        step_id="build",
        success=False,
        error="compile error",
    )

    result = engine.execute_step(
        run_id=run.run_id,
        step_id="test",
        success=False,
        error="test failure",
    )

    step = next(
        item
        for item in result.steps
        if item.step_id == "test"
    )

    assert step.status is (
        WorkflowStepStatus.RETRYING
    )
    assert step.attempt_count == 1


def test_failed_step_exceeds_retry_limit() -> None:
    engine = WorkflowEngine()

    run = engine.create_run(
        build_workflow()
    )

    engine.start_run(run.run_id)

    result = engine.execute_step(
        run_id=run.run_id,
        step_id="test",
        success=False,
        error="persistent failure",
    )

    result = engine.execute_step(
        run_id=run.run_id,
        step_id="test",
        success=False,
        error="persistent failure",
    )

    step = next(
        item
        for item in result.steps
        if item.step_id == "test"
    )

    assert step.status is (
        WorkflowStepStatus.FAILED
    )
    assert result.status is (
        WorkflowStatus.FAILED
    )


def test_failed_workflow_enters_compensation() -> None:
    engine = WorkflowEngine()

    run = engine.create_run(
        build_workflow()
    )

    engine.start_run(run.run_id)

    failed = engine.execute_step(
        run_id=run.run_id,
        step_id="deploy",
        success=False,
        error="deployment failure",
    )

    compensated = engine.compensate(
        failed.run_id
    )

    assert compensated.status is (
        WorkflowStatus.COMPENSATING
    )


def test_checkpoint_is_created_after_state_change() -> None:
    engine = WorkflowEngine()

    run = engine.create_run(
        build_workflow()
    )

    engine.start_run(run.run_id)

    checkpoints = (
        engine._checkpoints
        .list_for_run(run.run_id)
    )

    assert len(checkpoints) >= 2


def test_recovery_restores_checkpoint() -> None:
    engine = WorkflowEngine()

    run = engine.create_run(
        build_workflow()
    )

    engine.start_run(run.run_id)

    recovered = engine.recover(
        run.run_id
    )

    assert recovered.run_id == run.run_id
    assert recovered.workflow_id == (
        "deploy-flow"
    )
