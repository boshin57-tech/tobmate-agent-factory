from pathlib import Path

import pytest

from af_core.orchestrator.project_execution_models import (
    ProjectRunEventKind,
    ProjectRunState,
    ProjectRunStatus,
)
from af_core.orchestrator.project_execution_repository import (
    ProjectRunRepositoryError,
    ProjectRunResumeService,
    ProjectRunVersionConflict,
)
from af_core.orchestrator.project_execution_runtime import (
    AutonomousProjectExecutionRuntime,
)
from af_core.persistence.database import (
    DatabaseRuntime,
    DatabaseRuntimeError,
    sqlite_url,
)


def state(
    run_id: str,
    *,
    status: ProjectRunStatus = ProjectRunStatus.READY,
    version: int = 3,
) -> ProjectRunState:
    return ProjectRunState(
        run_id=run_id,
        project_id=f"project-{run_id}",
        repository_path=f"/workspace/{run_id}",
        status=status,
        created_at=1.0,
        updated_at=float(version),
        version=version,
        metadata={
            "source": "sql-test",
        },
    )


def ready_runtime(
    path: Path,
) -> DatabaseRuntime:
    runtime = DatabaseRuntime.from_url(
        sqlite_url(path)
    )
    runtime.prepare_schema(
        auto_migrate=True
    )
    return runtime


def test_factory_requires_current_schema(
    tmp_path: Path,
) -> None:
    with DatabaseRuntime.from_url(
        sqlite_url(tmp_path / "pending.db")
    ) as runtime:
        with pytest.raises(
            DatabaseRuntimeError,
            match="schema must be current",
        ):
            runtime.create_project_run_repository()


def test_create_and_get_round_trip(
    tmp_path: Path,
) -> None:
    with ready_runtime(
        tmp_path / "round-trip.db"
    ) as runtime:
        repository = (
            runtime.create_project_run_repository()
        )
        original = state("run-a")

        created = repository.create(
            original,
            occurred_at=10.0,
        )
        restored = repository.get(
            original.run_id
        )

        assert created.state == original
        assert restored.state == original
        assert len(restored.events) == 1
        assert (
            restored.events[0].kind
            is ProjectRunEventKind.RUN_CREATED
        )


def test_duplicate_create_is_rejected(
    tmp_path: Path,
) -> None:
    with ready_runtime(
        tmp_path / "duplicate.db"
    ) as runtime:
        repository = (
            runtime.create_project_run_repository()
        )
        original = state("run-a")

        repository.create(
            original,
            occurred_at=10.0,
        )

        with pytest.raises(
            ProjectRunRepositoryError,
            match="already exists",
        ):
            repository.create(
                original,
                occurred_at=11.0,
            )


def test_save_updates_snapshot_and_event_atomically(
    tmp_path: Path,
) -> None:
    with ready_runtime(
        tmp_path / "save.db"
    ) as runtime:
        repository = (
            runtime.create_project_run_repository()
        )
        original = state("run-a")

        repository.create(
            original,
            occurred_at=10.0,
        )

        updated = original.transition(
            ProjectRunStatus.RUNNING,
            now=20.0,
        )

        saved = repository.save(
            updated,
            expected_version=original.version,
            occurred_at=20.0,
            event_kind=(
                ProjectRunEventKind.RUN_TRANSITIONED
            ),
            detail={
                "previous_status": (
                    original.status.value
                ),
            },
        )

        assert saved.state == updated
        assert len(saved.events) == 2
        assert saved.events[-1].sequence == 2
        assert (
            saved.events[-1].kind
            is ProjectRunEventKind.RUN_TRANSITIONED
        )


def test_stale_save_does_not_modify_snapshot(
    tmp_path: Path,
) -> None:
    with ready_runtime(
        tmp_path / "stale.db"
    ) as runtime:
        repository = (
            runtime.create_project_run_repository()
        )
        original = state("run-a")

        repository.create(
            original,
            occurred_at=10.0,
        )

        updated = original.transition(
            ProjectRunStatus.RUNNING,
            now=20.0,
        )

        repository.save(
            updated,
            expected_version=original.version,
            occurred_at=20.0,
        )

        stale = original.transition(
            ProjectRunStatus.RUNNING,
            now=30.0,
        )

        with pytest.raises(
            ProjectRunVersionConflict,
            match="version conflict",
        ):
            repository.save(
                stale,
                expected_version=original.version,
                occurred_at=30.0,
            )

        persisted = repository.get(
            original.run_id
        )

        assert persisted.state == updated
        assert len(persisted.events) == 2


def test_append_event_preserves_snapshot(
    tmp_path: Path,
) -> None:
    with ready_runtime(
        tmp_path / "append.db"
    ) as runtime:
        repository = (
            runtime.create_project_run_repository()
        )
        original = state("run-a")

        repository.create(
            original,
            occurred_at=10.0,
        )

        event = repository.append_event(
            original.run_id,
            kind=ProjectRunEventKind.DELIVERY_CREATED,
            occurred_at=20.0,
            detail={
                "artifact": "delivery-1",
            },
        )

        restored = repository.get(
            original.run_id
        )

        assert event.sequence == 2
        assert restored.state == original
        assert len(restored.events) == 2


def test_exists_and_list_run_ids(
    tmp_path: Path,
) -> None:
    with ready_runtime(
        tmp_path / "list.db"
    ) as runtime:
        repository = (
            runtime.create_project_run_repository()
        )

        repository.create(
            state("run-b"),
            occurred_at=10.0,
        )
        repository.create(
            state("run-a"),
            occurred_at=11.0,
        )

        assert repository.exists("run-a")
        assert not repository.exists("missing")
        assert repository.list_run_ids() == (
            "run-a",
            "run-b",
        )


def test_resumable_filters_terminal_runs(
    tmp_path: Path,
) -> None:
    with ready_runtime(
        tmp_path / "resumable.db"
    ) as runtime:
        repository = (
            runtime.create_project_run_repository()
        )

        repository.create(
            state(
                "ready",
                status=ProjectRunStatus.READY,
            ),
            occurred_at=10.0,
        )

        repository.create(
            state(
                "completed",
                status=ProjectRunStatus.COMPLETED,
            ),
            occurred_at=11.0,
        )

        resumable = repository.resumable()

        assert tuple(
            snapshot.state.run_id
            for snapshot in resumable
        ) == ("ready",)


def test_repository_survives_process_restart(
    tmp_path: Path,
) -> None:
    database = tmp_path / "restart.db"
    original = state("run-a")

    with ready_runtime(database) as first:
        repository = (
            first.create_project_run_repository()
        )
        repository.create(
            original,
            occurred_at=10.0,
        )

    with ready_runtime(database) as second:
        repository = (
            second.create_project_run_repository()
        )
        restored = repository.get(
            original.run_id
        )

        assert restored.state == original
        assert len(restored.events) == 1


def test_resume_service_accepts_sql_repository(
    tmp_path: Path,
) -> None:
    with ready_runtime(
        tmp_path / "resume.db"
    ) as runtime:
        repository = (
            runtime.create_project_run_repository()
        )
        original = state(
            "run-a",
            status=ProjectRunStatus.READY,
        )

        repository.create(
            original,
            occurred_at=10.0,
        )

        resumed = ProjectRunResumeService(
            repository
        ).resume(
            original.run_id,
            now=20.0,
        )

        assert (
            resumed.state.status
            is ProjectRunStatus.RUNNING
        )
        assert (
            resumed.state.version
            == original.version + 1
        )
        assert (
            resumed.events[-1].kind
            is ProjectRunEventKind.RUN_RESUMED
        )


def test_execution_runtime_accepts_sql_repository(
    tmp_path: Path,
) -> None:
    with ready_runtime(
        tmp_path / "execution.db"
    ) as database:
        repository = (
            database.create_project_run_repository()
        )

        runtime = AutonomousProjectExecutionRuntime(
            repository
        )

        created = runtime.create_run(
            project_id="project-a",
            repository_path="/workspace/project-a",
            now=10.0,
        )

        planning = runtime.begin_planning(
            created.state.run_id,
            now=20.0,
        )

        assert (
            planning.state.status
            is ProjectRunStatus.PLANNING
        )
        assert len(planning.events) == 2
