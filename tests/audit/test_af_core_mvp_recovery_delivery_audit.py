"""Recovery and delivery integrity audit for AF-Core MVP."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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
    ProjectExecutionError,
    ProjectRunEventKind,
    ProjectRunState,
    ProjectRunStatus,
    ProjectTaskRuntimeState,
    ProjectTaskStatus,
)
from af_core.orchestrator.project_execution_repository import (
    JsonProjectRunRepository,
    ProjectRunResumeService,
)
from af_core.orchestrator.project_execution_runtime import (
    AutonomousProjectExecutionRuntime,
)


def _persist_state(
    repository: JsonProjectRunRepository,
    state: ProjectRunState,
    *,
    previous_version: int,
    now: float,
) -> ProjectRunState:
    repository.save(
        state,
        expected_version=previous_version,
        occurred_at=now,
    )
    return state


def _completed_delivery_package(
    repository: JsonProjectRunRepository,
):
    run = ProjectRunState.create(
        project_id="delivery-integrity-audit",
        repository_path="/workspace/delivery-integrity-audit",
        now=300,
    )

    for index, task_id in enumerate(
        ("build", "test"),
        start=1,
    ):
        run = run.with_task(
            ProjectTaskRuntimeState(
                task_id=task_id,
                status=ProjectTaskStatus.SUCCEEDED,
                attempts=1,
                started_at=300 + index,
                finished_at=301 + index,
                output_reference=f"artifact://{task_id}",
            ),
            now=301 + index,
        )

    repository.create(
        run,
        occurred_at=303,
    )

    previous = run
    planning = run.transition(
        ProjectRunStatus.PLANNING,
        now=304,
    )
    _persist_state(
        repository,
        planning,
        previous_version=previous.version,
        now=304,
    )

    previous = planning
    ready = planning.transition(
        ProjectRunStatus.READY,
        now=305,
    )
    _persist_state(
        repository,
        ready,
        previous_version=previous.version,
        now=305,
    )

    previous = ready
    running = ready.transition(
        ProjectRunStatus.RUNNING,
        now=306,
    )
    _persist_state(
        repository,
        running,
        previous_version=previous.version,
        now=306,
    )

    service = ProjectDeliveryLifecycleService(
        repository
    )

    service.begin_validation(
        run.run_id,
        now=307,
    )

    validations = tuple(
        ProjectValidationResult(
            task_id=task_id,
            status=ProjectValidationStatus.PASSED,
            validator_id="validator-audit",
            checked_at=308,
            evidence=(
                f"evidence://{task_id}",
            ),
        )
        for task_id in ("build", "test")
    )

    return service.finalize(
        run.run_id,
        validations=validations,
        now=309,
        metadata={
            "audit": "final-recovery-delivery",
        },
    )


def _partial_delivery_package(
    repository: JsonProjectRunRepository,
):
    run = ProjectRunState.create(
        project_id="partial-integrity-audit",
        repository_path="/workspace/partial-integrity-audit",
        now=400,
    )

    run = run.with_task(
        ProjectTaskRuntimeState(
            task_id="build",
            status=ProjectTaskStatus.SUCCEEDED,
            attempts=1,
            started_at=401,
            finished_at=402,
            output_reference="artifact://build",
        ),
        now=402,
    )

    run = run.with_task(
        ProjectTaskRuntimeState(
            task_id="test",
            status=ProjectTaskStatus.FAILED,
            attempts=1,
            started_at=403,
            finished_at=404,
            last_error="validation tests failed",
        ),
        now=404,
    )

    repository.create(
        run,
        occurred_at=404,
    )

    planning = run.transition(
        ProjectRunStatus.PLANNING,
        now=405,
    )
    repository.save(
        planning,
        expected_version=run.version,
        occurred_at=405,
    )

    ready = planning.transition(
        ProjectRunStatus.READY,
        now=406,
    )
    repository.save(
        ready,
        expected_version=planning.version,
        occurred_at=406,
    )

    running = ready.transition(
        ProjectRunStatus.RUNNING,
        now=407,
    )
    repository.save(
        running,
        expected_version=ready.version,
        occurred_at=407,
    )

    service = ProjectDeliveryLifecycleService(
        repository
    )

    service.begin_validation(
        run.run_id,
        now=408,
    )

    return service.finalize(
        run.run_id,
        validations=(
            ProjectValidationResult(
                task_id="build",
                status=ProjectValidationStatus.PASSED,
                validator_id="validator-audit",
                checked_at=409,
            ),
            ProjectValidationResult(
                task_id="test",
                status=ProjectValidationStatus.FAILED,
                validator_id="validator-audit",
                checked_at=409,
                findings=(
                    "validation tests failed",
                ),
            ),
        ),
        now=410,
    )


def test_running_run_recovers_after_repository_restart(
    tmp_path: Path,
) -> None:
    """A persisted running project must resume through recovery."""

    state_directory = tmp_path / "resume-state"

    repository = JsonProjectRunRepository(
        state_directory
    )
    runtime = AutonomousProjectExecutionRuntime(
        repository
    )

    created = runtime.create_run(
        project_id="restart-recovery-audit",
        repository_path="/workspace/restart-recovery-audit",
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
        now=102,
    )
    runtime.finalize_plan(
        run_id,
        now=103,
    )
    runtime.refresh_ready_tasks(
        run_id,
        now=104,
    )
    runtime.start_run(
        run_id,
        now=105,
    )

    restarted_repository = JsonProjectRunRepository(
        state_directory
    )
    resume_service = ProjectRunResumeService(
        restarted_repository
    )

    resumed = resume_service.resume(
        run_id,
        now=106,
    )

    assert (
        resumed.state.status
        is ProjectRunStatus.RECOVERING
    )
    assert (
        resumed.events[-1].kind
        is ProjectRunEventKind.RUN_RESUMED
    )

    reloaded = JsonProjectRunRepository(
        state_directory
    ).get(run_id)

    assert (
        reloaded.state.status
        is ProjectRunStatus.RECOVERING
    )
    assert (
        reloaded.state.version
        == resumed.state.version
    )


def test_terminal_run_cannot_be_resumed(
    tmp_path: Path,
) -> None:
    """Terminal project state must never re-enter execution."""

    repository = JsonProjectRunRepository(
        tmp_path / "terminal-state"
    )

    state = ProjectRunState.create(
        project_id="terminal-resume-audit",
        repository_path="/workspace/terminal-resume-audit",
        now=200,
    )

    repository.create(
        state,
        occurred_at=200,
    )

    for timestamp, status in (
        (201, ProjectRunStatus.PLANNING),
        (202, ProjectRunStatus.READY),
        (203, ProjectRunStatus.RUNNING),
        (204, ProjectRunStatus.VALIDATING),
        (205, ProjectRunStatus.COMPLETED),
    ):
        previous = state
        state = state.transition(
            status,
            now=timestamp,
        )

        repository.save(
            state,
            expected_version=previous.version,
            occurred_at=timestamp,
        )

    with pytest.raises(ProjectExecutionError):
        ProjectRunResumeService(
            repository
        ).resume(
            state.run_id,
            now=206,
        )

    persisted = repository.get(
        state.run_id
    )

    assert (
        persisted.state.status
        is ProjectRunStatus.COMPLETED
    )


def test_completed_delivery_files_are_consistent_and_atomic(
    tmp_path: Path,
) -> None:
    """Manifest, audit and report must describe one final state."""

    repository = JsonProjectRunRepository(
        tmp_path / "completed-state"
    )

    package = _completed_delivery_package(
        repository
    )

    writer = JsonProjectDeliveryWriter()

    files = writer.write(
        package,
        tmp_path / "completed-delivery",
    )

    writer.write(
        package,
        tmp_path / "completed-delivery",
    )

    manifest = json.loads(
        files.manifest_path.read_text(
            encoding="utf-8"
        )
    )
    audit = json.loads(
        files.audit_path.read_text(
            encoding="utf-8"
        )
    )
    report = files.report_path.read_text(
        encoding="utf-8"
    )

    assert (
        package.audit.decision
        is ProjectCompletionDecision.COMPLETED
    )
    assert manifest["run_id"] == package.state.run_id
    assert audit["run_id"] == package.state.run_id
    assert manifest["decision"] == "completed"
    assert audit["decision"] == "completed"
    assert manifest["task_statuses"] == (
        audit["task_statuses"]
    )
    assert {
        artifact["reference"]
        for artifact in manifest["artifacts"]
    } == {
        "artifact://build",
        "artifact://test",
    }
    assert "Decision: completed" in report
    assert "artifact://build" in report
    assert "artifact://test" in report

    assert tuple(
        (tmp_path / "completed-delivery").rglob(
            "*.tmp"
        )
    ) == ()

    snapshot = repository.get(
        package.state.run_id
    )

    timestamps = tuple(
        event.occurred_at
        for event in snapshot.events
    )

    assert timestamps == tuple(
        sorted(timestamps)
    )
    assert (
        snapshot.events[-1].kind
        is ProjectRunEventKind.DELIVERY_CREATED
    )


def test_partial_delivery_never_claims_completion(
    tmp_path: Path,
) -> None:
    """Partial execution must remain partial in every delivery file."""

    repository = JsonProjectRunRepository(
        tmp_path / "partial-state"
    )

    package = _partial_delivery_package(
        repository
    )

    files = JsonProjectDeliveryWriter().write(
        package,
        tmp_path / "partial-delivery",
    )

    manifest = json.loads(
        files.manifest_path.read_text(
            encoding="utf-8"
        )
    )
    audit = json.loads(
        files.audit_path.read_text(
            encoding="utf-8"
        )
    )
    report = files.report_path.read_text(
        encoding="utf-8"
    )

    assert (
        package.state.status
        is ProjectRunStatus.PARTIAL
    )
    assert (
        package.audit.decision
        is ProjectCompletionDecision.PARTIAL
    )
    assert manifest["decision"] == "partial"
    assert audit["decision"] == "partial"
    assert "Decision: partial" in report
    assert "Decision: completed" not in report
    assert audit["failed_tasks"] == 1
    assert audit["validation_failed"] == 1
