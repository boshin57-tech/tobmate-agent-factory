from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from af_core.persistence.database import (
    DatabaseRuntime,
    create_database_engine,
    initialize_database,
    sqlite_url,
)
from af_core.persistence.migrations import (
    APPLICATION_SCHEMA_VERSION,
    MigrationDefinition,
    MigrationExecutionError,
    MigrationIntegrityError,
    MigrationRegistry,
    SchemaCompatibilityError,
    SchemaMigrationGate,
    SchemaMigrationManager,
    default_migration_registry,
)


def engine_for(
    tmp_path: Path,
    name: str,
):
    return create_database_engine(
        sqlite_url(tmp_path / name)
    )


def insert_history(
    manager: SchemaMigrationManager,
    *,
    version: int,
    name: str,
    checksum: str,
) -> None:
    manager.ensure_registry_table()

    with manager.engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO af_schema_migrations
                (
                    version,
                    name,
                    checksum,
                    applied_at
                )
                VALUES
                (
                    :version,
                    :name,
                    :checksum,
                    :applied_at
                )
                """
            ),
            {
                "version": version,
                "name": name,
                "checksum": checksum,
                "applied_at": (
                    "2026-08-04T00:00:00+00:00"
                ),
            },
        )


def test_registry_requires_contiguous_versions():
    migration = MigrationDefinition(
        version=2,
        name="invalid-gap",
        signature="invalid-gap-v2",
        apply=lambda connection: None,
    )

    with pytest.raises(
        ValueError,
        match="contiguous",
    ):
        MigrationRegistry((migration,))


def test_checksum_is_stable_and_signature_sensitive():
    first = MigrationDefinition(
        version=1,
        name="baseline",
        signature="signature-a",
        apply=lambda connection: None,
    )

    same = MigrationDefinition(
        version=1,
        name="baseline",
        signature="signature-a",
        apply=lambda connection: None,
    )

    changed = MigrationDefinition(
        version=1,
        name="baseline",
        signature="signature-b",
        apply=lambda connection: None,
    )

    assert first.checksum == same.checksum
    assert first.checksum != changed.checksum
    assert len(first.checksum) == 64


def test_empty_database_reports_pending_baseline(
    tmp_path: Path,
):
    engine = engine_for(
        tmp_path,
        "pending.db",
    )

    try:
        manager = SchemaMigrationManager(
            engine,
            default_migration_registry(),
        )

        report = manager.assess()

        assert report.current_version == 0
        assert report.target_version == 2
        assert report.pending_versions == (1, 2)
        assert report.compatible is True
        assert report.requires_migration is True
    finally:
        engine.dispose()


def test_gate_rejects_pending_schema_without_auto_migrate(
    tmp_path: Path,
):
    engine = engine_for(
        tmp_path,
        "manual-gate.db",
    )

    try:
        manager = SchemaMigrationManager(
            engine,
            default_migration_registry(),
        )

        gate = SchemaMigrationGate(
            manager,
            auto_migrate=False,
        )

        with pytest.raises(
            SchemaCompatibilityError,
            match="pending schema migrations",
        ):
            gate.prepare()
    finally:
        engine.dispose()


def test_auto_migrate_creates_baseline_and_history(
    tmp_path: Path,
):
    engine = engine_for(
        tmp_path,
        "auto-migrate.db",
    )

    try:
        manager = SchemaMigrationManager(
            engine,
            default_migration_registry(),
        )

        report = SchemaMigrationGate(
            manager,
            auto_migrate=True,
        ).prepare()

        assert report.current_version == (
            APPLICATION_SCHEMA_VERSION
        )
        assert report.requires_migration is False

        tables = set(
            inspect(engine).get_table_names()
        )

        assert {
            "projects",
            "tasks",
            "runs",
            "events",
            "af_schema_migrations",
            "project_run_snapshots",
            "project_run_events",
        }.issubset(tables)

        history = manager.applied_migrations()

        assert len(history) == 2
        assert history[0].version == 1
        assert (
            history[0].checksum
            == default_migration_registry()
            .get(1)
            .checksum
        )
    finally:
        engine.dispose()


def test_migration_is_idempotent(
    tmp_path: Path,
):
    engine = engine_for(
        tmp_path,
        "idempotent.db",
    )

    try:
        manager = SchemaMigrationManager(
            engine,
            default_migration_registry(),
        )

        first = manager.migrate()
        second = manager.migrate()

        assert first.current_version == APPLICATION_SCHEMA_VERSION
        assert second.current_version == APPLICATION_SCHEMA_VERSION
        assert len(
            manager.applied_migrations()
        ) == 2
    finally:
        engine.dispose()


def test_existing_baseline_schema_can_be_adopted(
    tmp_path: Path,
):
    engine = engine_for(
        tmp_path,
        "existing-schema.db",
    )

    try:
        initialize_database(engine)

        manager = SchemaMigrationManager(
            engine,
            default_migration_registry(),
        )

        report = manager.migrate()

        assert report.current_version == APPLICATION_SCHEMA_VERSION
        assert len(
            manager.applied_migrations()
        ) == 2
    finally:
        engine.dispose()


def test_tampered_checksum_is_rejected(
    tmp_path: Path,
):
    engine = engine_for(
        tmp_path,
        "tampered.db",
    )

    try:
        manager = SchemaMigrationManager(
            engine,
            default_migration_registry(),
        )

        definition = (
            default_migration_registry().get(1)
        )

        insert_history(
            manager,
            version=1,
            name=definition.name,
            checksum="0" * 64,
        )

        with pytest.raises(
            MigrationIntegrityError,
            match="checksum mismatch",
        ):
            manager.assess()
    finally:
        engine.dispose()


def test_future_database_version_is_rejected(
    tmp_path: Path,
):
    engine = engine_for(
        tmp_path,
        "future.db",
    )

    try:
        manager = SchemaMigrationManager(
            engine,
            default_migration_registry(),
        )

        manager.migrate()

        insert_history(
            manager,
            version=3,
            name="future-migration",
            checksum="f" * 64,
        )

        report = manager.assess()

        assert report.compatible is False
        assert report.current_version == 3

        gate = SchemaMigrationGate(manager)

        with pytest.raises(
            SchemaCompatibilityError,
            match="newer",
        ):
            gate.prepare()
    finally:
        engine.dispose()


def test_non_contiguous_history_is_rejected(
    tmp_path: Path,
):
    engine = engine_for(
        tmp_path,
        "history-gap.db",
    )

    try:
        manager = SchemaMigrationManager(
            engine,
            default_migration_registry(),
        )

        insert_history(
            manager,
            version=2,
            name="gap",
            checksum="a" * 64,
        )

        with pytest.raises(
            MigrationIntegrityError,
            match="not contiguous",
        ):
            manager.assess()
    finally:
        engine.dispose()


def test_failed_migration_is_not_recorded(
    tmp_path: Path,
):
    engine = engine_for(
        tmp_path,
        "failed.db",
    )

    def fail(_connection):
        raise RuntimeError(
            "simulated migration failure"
        )

    registry = MigrationRegistry(
        (
            MigrationDefinition(
                version=1,
                name="failing",
                signature="failing-v1",
                apply=fail,
            ),
        )
    )

    try:
        manager = SchemaMigrationManager(
            engine,
            registry,
        )

        with pytest.raises(
            MigrationExecutionError,
            match="migration failed",
        ):
            manager.migrate()

        assert (
            manager.applied_migrations()
            == ()
        )
    finally:
        engine.dispose()


def test_database_runtime_prepares_schema(
    tmp_path: Path,
):
    with DatabaseRuntime.from_url(
        sqlite_url(tmp_path / "runtime-gate.db")
    ) as runtime:
        pending = runtime.schema_status()

        assert pending.current_version == 0
        assert pending.requires_migration is True

        ready = runtime.prepare_schema(
            auto_migrate=True
        )

        assert ready.current_version == APPLICATION_SCHEMA_VERSION
        assert ready.requires_migration is False
        assert runtime.health().healthy is True
