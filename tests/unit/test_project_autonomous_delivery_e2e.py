"""Checkpoint 17 final autonomous project execution E2E tests."""

from __future__ import annotations

import json
from pathlib import Path

from af_core.orchestrator.project_completion_audit import (
    ProjectCompletionDecision,
    ProjectValidationResult,
    ProjectValidationStatus,
)
from af_core.orchestrator.project_delivery_lifecycle import (
    JsonProjectDeliveryWriter,
    ProjectDeliveryLifecycleService,
)
from af_core.orchestrator.project_execution_models import (
    ProjectRunEventKind,
    ProjectRunStatus,
    ProjectTaskStatus,
)
from af_core.orchestrator.project_execution_repository import (
    JsonProjectRunRepository,
)
from af_core.orchestrator.project_execution_runtime import (
    AutonomousProjectExecutionRuntime,
    ProjectTaskExecutionResult,
)
from af_core.orchestrator.project_team_coordination import (
    ProjectHandoffStatus,
    ProjectTeamCoordinationRegistry,
)
from af_core.orchestrator.project_team_execution import (
    ProjectTeamExecutionCoordinator,
)


class SuccessfulExecutor:
    """Deterministic executor producing one artifact per task."""

    def execute(self, *, run, task):
        return ProjectTaskExecutionResult(
            succeeded=True,
            output_reference=f"artifact://{task.task_id}",
            metadata={
                "executed_run_id": run.run_id,
            },
        )


class FailOnceExecutor:
    """Fail the first invocation and succeed after explicit retry."""

    def __init__(self) -> None:
        self.calls = 0

    def execute(self, *, run, task):
        self.calls += 1

        if self.calls == 1:
            return ProjectTaskExecutionResult(
                succeeded=False,
                error="temporary execution failure",
            )

        return ProjectTaskExecutionResult(
            succeeded=True,
            output_reference=f"artifact://{task.task_id}",
        )


def test_autonomous_multi_team_project_delivery_e2e(
    tmp_path: Path,
) -> None:
    state_directory = tmp_path / "state"
    delivery_directory = tmp_path / "delivery"

    repository = JsonProjectRunRepository(
        state_directory
    )
    runtime = AutonomousProjectExecutionRuntime(
        repository
    )
    registry = ProjectTeamCoordinationRegistry()

    coordinator = ProjectTeamExecutionCoordinator(
        runtime,
        registry,
    )

    created = runtime.create_run(
        project_id="af-core-final-e2e",
        repository_path="/workspace/af-core-final-e2e",
        now=100,
    )
    run_id = created.state.run_id

    runtime.begin_planning(
        run_id,
        now=101,
    )

    runtime.register_task(
        run_id,
        task_id="build",
        metadata={
            "required_capabilities": ("build",),
        },
        now=102,
    )

    runtime.register_task(
        run_id,
        task_id="test",
        dependencies=("build",),
        metadata={
            "required_capabilities": ("test",),
        },
        now=103,
    )

    runtime.register_task(
        run_id,
        task_id="package",
        dependencies=("test",),
        metadata={
            "required_capabilities": ("release",),
        },
        now=104,
    )

    runtime.finalize_plan(
        run_id,
        now=105,
    )
    runtime.refresh_ready_tasks(
        run_id,
        now=106,
    )
    runtime.start_run(
        run_id,
        now=107,
    )

    coordinator.assign_task(
        run_id=run_id,
        task_id="build",
        team_id="team-build",
        capabilities=("build",),
        now=108,
    )

    coordinator.assign_task(
        run_id=run_id,
        task_id="test",
        team_id="team-quality",
        capabilities=("test",),
        now=108,
    )

    coordinator.assign_task(
        run_id=run_id,
        task_id="package",
        team_id="team-release",
        capabilities=("release",),
        now=108,
    )

    executor = SuccessfulExecutor()

    build_cycle = coordinator.execute_next(
        run_id,
        executor,
        now=109,
    )

    assert build_cycle is not None
    assert build_cycle.task_id == "build"
    assert build_cycle.succeeded is True
    assert len(build_cycle.handoff_ids) == 1

    build_handoff_id = (
        build_cycle.handoff_ids[0]
    )

    build_handoff = registry.snapshot(
        run_id
    ).handoffs[0]

    assert (
        build_handoff.status
        is ProjectHandoffStatus.PENDING
    )
    assert coordinator.eligible_tasks(run_id) == ()

    registry.accept_handoff(
        build_handoff_id,
        team_id="team-quality",
        now=110,
    )
    registry.complete_handoff(
        build_handoff_id,
        now=111,
    )

    test_cycle = coordinator.execute_next(
        run_id,
        executor,
        now=112,
    )

    assert test_cycle is not None
    assert test_cycle.task_id == "test"
    assert test_cycle.succeeded is True
    assert len(test_cycle.handoff_ids) == 1

    test_handoff_id = test_cycle.handoff_ids[0]

    registry.accept_handoff(
        test_handoff_id,
        team_id="team-release",
        now=113,
    )
    registry.complete_handoff(
        test_handoff_id,
        now=114,
    )

    package_cycle = coordinator.execute_next(
        run_id,
        executor,
        now=115,
    )

    assert package_cycle is not None
    assert package_cycle.task_id == "package"
    assert package_cycle.succeeded is True
    assert package_cycle.handoff_ids == ()

    executed = repository.get(run_id)

    assert executed.state.status is ProjectRunStatus.RUNNING
    assert all(
        task.status
        is ProjectTaskStatus.SUCCEEDED
        for task in executed.state.tasks.values()
    )

    delivery_service = ProjectDeliveryLifecycleService(
        repository
    )

    delivery_service.begin_validation(
        run_id,
        now=116,
    )

    validations = tuple(
        ProjectValidationResult(
            task_id=task_id,
            status=ProjectValidationStatus.PASSED,
            validator_id="validator-final",
            checked_at=117,
            evidence=(
                f"evidence://{task_id}",
            ),
        )
        for task_id in (
            "build",
            "test",
            "package",
        )
    )

    delivery_package = delivery_service.finalize(
        run_id,
        validations=validations,
        now=118,
        metadata={
            "checkpoint": "17-E",
            "release": "af-core-mvp",
        },
    )

    assert (
        delivery_package.state.status
        is ProjectRunStatus.COMPLETED
    )
    assert (
        delivery_package.audit.decision
        is ProjectCompletionDecision.COMPLETED
    )
    assert (
        delivery_package.audit.validation_passed
        == 3
    )
    assert len(
        delivery_package.manifest.artifacts
    ) == 3

    delivery_files = (
        JsonProjectDeliveryWriter().write(
            delivery_package,
            delivery_directory,
        )
    )

    assert delivery_files.manifest_path.is_file()
    assert delivery_files.audit_path.is_file()
    assert delivery_files.report_path.is_file()

    manifest = json.loads(
        delivery_files.manifest_path.read_text(
            encoding="utf-8"
        )
    )
    audit = json.loads(
        delivery_files.audit_path.read_text(
            encoding="utf-8"
        )
    )
    report = delivery_files.report_path.read_text(
        encoding="utf-8"
    )

    assert manifest["decision"] == "completed"
    assert audit["decision"] == "completed"
    assert len(manifest["artifacts"]) == 3
    assert "Decision: completed" in report
    assert "artifact://package" in report

    reloaded_repository = JsonProjectRunRepository(
        state_directory
    )
    reloaded = reloaded_repository.get(
        run_id
    )

    assert (
        reloaded.state.status
        is ProjectRunStatus.COMPLETED
    )
    assert (
        reloaded.events[-1].kind
        is ProjectRunEventKind.DELIVERY_CREATED
    )
    assert len(reloaded.state.tasks) == 3


def test_explicit_retry_recovery_to_completed_delivery(
    tmp_path: Path,
) -> None:
    repository = JsonProjectRunRepository(
        tmp_path / "retry-state"
    )
    runtime = AutonomousProjectExecutionRuntime(
        repository
    )
    registry = ProjectTeamCoordinationRegistry()

    coordinator = ProjectTeamExecutionCoordinator(
        runtime,
        registry,
    )

    created = runtime.create_run(
        project_id="retry-recovery-e2e",
        repository_path="/workspace/retry-recovery",
        now=200,
    )
    run_id = created.state.run_id

    runtime.begin_planning(
        run_id,
        now=201,
    )
    runtime.register_task(
        run_id,
        task_id="build",
        metadata={
            "required_capabilities": ("build",),
        },
        now=202,
    )
    runtime.finalize_plan(
        run_id,
        now=203,
    )
    runtime.refresh_ready_tasks(
        run_id,
        now=204,
    )
    runtime.start_run(
        run_id,
        now=205,
    )

    coordinator.assign_task(
        run_id=run_id,
        task_id="build",
        team_id="team-build",
        capabilities=("build",),
        now=206,
    )

    executor = FailOnceExecutor()

    failed_cycle = coordinator.execute_next(
        run_id,
        executor,
        now=207,
    )

    assert failed_cycle is not None
    assert failed_cycle.succeeded is False
    assert (
        repository.get(run_id)
        .state.tasks["build"]
        .status
        is ProjectTaskStatus.FAILED
    )

    runtime.retry_task(
        run_id,
        "build",
        now=208,
    )

    recovered_cycle = coordinator.execute_next(
        run_id,
        executor,
        now=209,
    )

    assert recovered_cycle is not None
    assert recovered_cycle.succeeded is True
    assert executor.calls == 2

    service = ProjectDeliveryLifecycleService(
        repository
    )
    service.begin_validation(
        run_id,
        now=210,
    )

    package = service.finalize(
        run_id,
        validations=(
            ProjectValidationResult(
                task_id="build",
                status=ProjectValidationStatus.PASSED,
                validator_id="validator-recovery",
                checked_at=211,
            ),
        ),
        now=212,
    )

    assert (
        package.state.status
        is ProjectRunStatus.COMPLETED
    )
    assert (
        package.audit.decision
        is ProjectCompletionDecision.COMPLETED
    )
    assert (
        package.state.tasks["build"].attempts
        == 2
    )
