from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from af_core.persistence.database import (
    DatabaseRuntime,
    create_database_engine,
    create_session_factory,
    database_healthcheck,
    initialize_database,
    normalize_database_url,
    registered_table_names,
    sqlite_url,
    transaction_scope,
)
from af_core.persistence.tables import (
    ProjectRow,
    TaskRow,
)


def project(
    project_id: str,
) -> ProjectRow:
    from datetime import datetime

    return ProjectRow(
        id=project_id,
        name="AF-Core",
        repository_path="/srv/af-core",
        objective="production readiness",
        status="READY",
        created_at=datetime.utcnow(),
    )


def test_sqlite_url_is_absolute_and_creates_parent(
    tmp_path: Path,
) -> None:
    target = tmp_path / "state" / "af-core.db"

    url = sqlite_url(target)

    assert url.startswith("sqlite:///")
    assert str(target.resolve()) in url
    assert target.parent.is_dir()


def test_memory_sqlite_url_is_preserved() -> None:
    assert sqlite_url(":memory:") == (
        "sqlite:///:memory:"
    )


def test_postgresql_url_uses_psycopg_driver() -> None:
    parsed = normalize_database_url(
        "postgresql://user:secret@db/afcore"
    )

    assert parsed.drivername == (
        "postgresql+psycopg"
    )
    assert parsed.username == "user"
    assert parsed.database == "afcore"


def test_model_registration_is_explicit() -> None:
    assert registered_table_names() == (
        "events",
        "projects",
        "runs",
        "tasks",
    )


def test_sqlite_safety_pragmas_are_enabled(
    tmp_path: Path,
) -> None:
    engine = create_database_engine(
        sqlite_url(tmp_path / "safe.db")
    )

    try:
        with engine.connect() as connection:
            foreign_keys = connection.exec_driver_sql(
                "PRAGMA foreign_keys"
            ).scalar_one()

            busy_timeout = connection.exec_driver_sql(
                "PRAGMA busy_timeout"
            ).scalar_one()

            journal_mode = connection.exec_driver_sql(
                "PRAGMA journal_mode"
            ).scalar_one()

        assert foreign_keys == 1
        assert busy_timeout == 30000
        assert journal_mode.lower() == "wal"
    finally:
        engine.dispose()


def test_healthcheck_reports_healthy_database(
    tmp_path: Path,
) -> None:
    engine = create_database_engine(
        sqlite_url(tmp_path / "health.db")
    )

    try:
        result = database_healthcheck(engine)

        assert result.healthy is True
        assert result.dialect == "sqlite"
        assert result.detail == "ok"
    finally:
        engine.dispose()


def test_transaction_scope_commits_complete_unit(
    tmp_path: Path,
) -> None:
    engine = create_database_engine(
        sqlite_url(tmp_path / "commit.db")
    )

    try:
        initialize_database(engine)
        sessions = create_session_factory(engine)

        with transaction_scope(sessions) as session:
            session.add(project("project-1"))

        with sessions() as session:
            count = session.scalar(
                select(func.count())
                .select_from(ProjectRow)
            )

        assert count == 1
    finally:
        engine.dispose()


def test_transaction_scope_rolls_back_complete_unit(
    tmp_path: Path,
) -> None:
    engine = create_database_engine(
        sqlite_url(tmp_path / "rollback.db")
    )

    try:
        initialize_database(engine)
        sessions = create_session_factory(engine)

        with pytest.raises(RuntimeError):
            with transaction_scope(
                sessions
            ) as session:
                session.add(project("project-1"))
                raise RuntimeError("abort")

        with sessions() as session:
            count = session.scalar(
                select(func.count())
                .select_from(ProjectRow)
            )

        assert count == 0
    finally:
        engine.dispose()


def test_sqlite_foreign_keys_are_enforced(
    tmp_path: Path,
) -> None:
    engine = create_database_engine(
        sqlite_url(tmp_path / "foreign-key.db")
    )

    try:
        initialize_database(engine)
        sessions = create_session_factory(engine)

        with pytest.raises(IntegrityError):
            with transaction_scope(
                sessions
            ) as session:
                session.add(
                    TaskRow(
                        id="task-1",
                        project_id="missing-project",
                        title="invalid",
                        status="READY",
                    )
                )
    finally:
        engine.dispose()


def test_database_runtime_owns_lifecycle(
    tmp_path: Path,
) -> None:
    with DatabaseRuntime.from_url(
        sqlite_url(tmp_path / "runtime.db")
    ) as runtime:
        runtime.initialize()

        assert runtime.health().healthy is True

        with runtime.transaction() as session:
            session.add(project("project-1"))

        with runtime.read_session() as session:
            restored = session.get(
                ProjectRow,
                "project-1",
            )

        assert restored is not None
        assert restored.name == "AF-Core"
