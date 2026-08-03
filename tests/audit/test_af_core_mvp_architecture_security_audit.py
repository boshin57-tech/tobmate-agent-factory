"""Final architecture and security audit for AF-Core MVP."""

from __future__ import annotations

from pathlib import Path

import pytest

from af_core.orchestrator.project_execution_models import (
    ProjectExecutionError,
    ProjectRunState,
    ProjectRunStatus,
)
from af_core.orchestrator.project_execution_repository import (
    JsonProjectRunRepository,
    ProjectRunVersionConflict,
)
from af_core.orchestrator.project_execution_runtime import (
    AutonomousProjectExecutionRuntime,
    ProjectExecutionRuntimeError,
)
from af_core.orchestrator.project_team_coordination import (
    ProjectConflictKind,
    ProjectHandoffStatus,
    ProjectTeamCoordinationError,
    ProjectTeamCoordinationRegistry,
)
from af_core.orchestrator.project_team_execution import (
    ProjectTeamExecutionCoordinator,
    ProjectTeamExecutionError,
)


def test_terminal_project_run_cannot_be_reopened() -> None:
    """A completed run must remain immutable and terminal."""

    state = ProjectRunState.create(
        project_id="terminal-audit",
        repository_path="/workspace/terminal-audit",
        now=100,
    )

    for timestamp, status in (
        (101, ProjectRunStatus.PLANNING),
        (102, ProjectRunStatus.READY),
        (103, ProjectRunStatus.RUNNING),
        (104, ProjectRunStatus.VALIDATING),
        (105, ProjectRunStatus.COMPLETED),
    ):
        state = state.transition(
            status,
            now=timestamp,
        )

    assert state.terminal is True

    with pytest.raises(ProjectExecutionError):
        state.transition(
            ProjectRunStatus.RUNNING,
            now=106,
        )


def test_repository_rejects_stale_version_and_leaves_no_temp_files(
    tmp_path: Path,
) -> None:
    """Optimistic locking must prevent stale state overwrite."""

    repository = JsonProjectRunRepository(
        tmp_path
    )

    created = ProjectRunState.create(
        project_id="version-audit",
        repository_path="/workspace/version-audit",
        now=200,
    )

    repository.create(
        created,
        occurred_at=200,
    )

    planning = created.transition(
        ProjectRunStatus.PLANNING,
        now=201,
    )

    repository.save(
        planning,
        expected_version=created.version,
        occurred_at=201,
    )

    stale_planning = created.transition(
        ProjectRunStatus.PLANNING,
        now=202,
    )

    with pytest.raises(ProjectRunVersionConflict):
        repository.save(
            stale_planning,
            expected_version=created.version,
            occurred_at=202,
        )

    persisted = repository.get(
        created.run_id
    )

    assert (
        persisted.state.version
        == planning.version
    )
    assert tuple(
        tmp_path.rglob("*.tmp")
    ) == ()


def test_dependency_cycle_is_rejected_before_execution(
    tmp_path: Path,
) -> None:
    """A cyclic task graph must never become ready."""

    runtime = AutonomousProjectExecutionRuntime(
        JsonProjectRunRepository(tmp_path)
    )

    created = runtime.create_run(
        project_id="cycle-audit",
        repository_path="/workspace/cycle-audit",
        now=300,
    )
    run_id = created.state.run_id

    runtime.begin_planning(
        run_id,
        now=301,
    )

    runtime.register_task(
        run_id,
        task_id="task-a",
        dependencies=("task-b",),
        now=302,
    )

    runtime.register_task(
        run_id,
        task_id="task-b",
        dependencies=("task-a",),
        now=303,
    )

    with pytest.raises(
        ProjectExecutionRuntimeError
    ):
        runtime.finalize_plan(
            run_id,
            now=304,
        )

    snapshot = runtime.repository.get(run_id)

    assert (
        snapshot.state.status
        is ProjectRunStatus.PLANNING
    )
    assert runtime.ready_tasks(run_id) == ()


def test_missing_team_capability_is_denied_and_audited(
    tmp_path: Path,
) -> None:
    """Capability failure must deny ownership and record conflict."""

    runtime = AutonomousProjectExecutionRuntime(
        JsonProjectRunRepository(tmp_path)
    )
    registry = ProjectTeamCoordinationRegistry()

    coordinator = ProjectTeamExecutionCoordinator(
        runtime,
        registry,
    )

    created = runtime.create_run(
        project_id="authority-audit",
        repository_path="/workspace/authority-audit",
        now=400,
    )
    run_id = created.state.run_id

    runtime.begin_planning(
        run_id,
        now=401,
    )

    runtime.register_task(
        run_id,
        task_id="production-deploy",
        metadata={
            "required_capabilities": (
                "production-deploy",
                "release-approval",
            ),
        },
        now=402,
    )

    with pytest.raises(
        ProjectTeamExecutionError
    ):
        coordinator.assign_task(
            run_id=run_id,
            task_id="production-deploy",
            team_id="team-build",
            capabilities=("build",),
            now=403,
        )

    snapshot = registry.snapshot(run_id)

    assert snapshot.assignments == ()
    assert len(snapshot.conflicts) == 1
    assert (
        snapshot.conflicts[0].kind
        is ProjectConflictKind.AUTHORITY
    )
    assert (
        snapshot.conflicts[0].resolved
        is False
    )


def test_only_target_team_can_accept_artifact_handoff() -> None:
    """Cross-team artifact entry must be target controlled."""

    registry = ProjectTeamCoordinationRegistry()

    registry.assign(
        run_id="run-handoff-audit",
        task_id="build",
        team_id="team-build",
    )
    registry.assign(
        run_id="run-handoff-audit",
        task_id="validate",
        team_id="team-quality",
    )

    handoff = registry.create_handoff(
        run_id="run-handoff-audit",
        source_task_id="build",
        target_task_id="validate",
        artifact_reference="artifact://secure-build",
        now=500,
    )

    with pytest.raises(
        ProjectTeamCoordinationError
    ):
        registry.accept_handoff(
            handoff.handoff_id,
            team_id="team-build",
            now=501,
        )

    pending = registry.snapshot(
        "run-handoff-audit"
    ).handoffs[0]

    assert (
        pending.status
        is ProjectHandoffStatus.PENDING
    )

    accepted = registry.accept_handoff(
        handoff.handoff_id,
        team_id="team-quality",
        now=502,
    )

    completed = registry.complete_handoff(
        handoff.handoff_id,
        now=503,
    )

    assert (
        accepted.status
        is ProjectHandoffStatus.ACCEPTED
    )
    assert (
        completed.status
        is ProjectHandoffStatus.COMPLETED
    )
