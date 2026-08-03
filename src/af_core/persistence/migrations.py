"""Versioned database migrations and startup compatibility gates."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .database import (
    Base,
    load_database_models,
)
from .project_run_tables import (
    project_run_metadata,
)


SCHEMA_MIGRATION_TABLE = "af_schema_migrations"
APPLICATION_SCHEMA_VERSION = 2
MINIMUM_SUPPORTED_SCHEMA_VERSION = 0


class MigrationError(RuntimeError):
    """Base error for schema migration failures."""


class MigrationIntegrityError(MigrationError):
    """Raised when migration history is missing or altered."""


class MigrationExecutionError(MigrationError):
    """Raised when a migration cannot be applied atomically."""


class SchemaCompatibilityError(MigrationError):
    """Raised when application and database schemas are incompatible."""


MigrationCallable = Callable[[Connection], None]


@dataclass(frozen=True, slots=True)
class MigrationDefinition:
    """One immutable migration definition."""

    version: int
    name: str
    signature: str
    apply: MigrationCallable

    def __post_init__(self) -> None:
        if self.version <= 0:
            raise ValueError(
                "migration version must be positive"
            )

        if not self.name.strip():
            raise ValueError(
                "migration name must not be empty"
            )

        if not self.signature.strip():
            raise ValueError(
                "migration signature must not be empty"
            )

    @property
    def checksum(self) -> str:
        payload = (
            f"{self.version}\0"
            f"{self.name.strip()}\0"
            f"{self.signature.strip()}"
        ).encode("utf-8")

        return sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class AppliedMigration:
    """One migration recorded in the database."""

    version: int
    name: str
    checksum: str
    applied_at: str


@dataclass(frozen=True, slots=True)
class SchemaCompatibilityReport:
    """Credential-free application/database compatibility report."""

    current_version: int
    target_version: int
    minimum_supported_version: int
    pending_versions: tuple[int, ...]
    compatible: bool
    requires_migration: bool
    reason: str


class MigrationRegistry:
    """Immutable ordered registry of application migrations."""

    def __init__(
        self,
        migrations: Iterable[MigrationDefinition],
    ) -> None:
        ordered = tuple(
            sorted(
                migrations,
                key=lambda migration: migration.version,
            )
        )

        versions = tuple(
            migration.version
            for migration in ordered
        )

        expected = tuple(
            range(1, len(ordered) + 1)
        )

        if versions != expected:
            raise ValueError(
                "migration versions must be contiguous "
                f"from 1: {versions}"
            )

        names = [
            migration.name
            for migration in ordered
        ]

        if len(names) != len(set(names)):
            raise ValueError(
                "migration names must be unique"
            )

        self._migrations = ordered
        self._by_version = {
            migration.version: migration
            for migration in ordered
        }

    @property
    def migrations(
        self,
    ) -> tuple[MigrationDefinition, ...]:
        return self._migrations

    @property
    def target_version(self) -> int:
        if not self._migrations:
            return 0

        return self._migrations[-1].version

    def get(
        self,
        version: int,
    ) -> MigrationDefinition:
        try:
            return self._by_version[version]
        except KeyError as exc:
            raise MigrationIntegrityError(
                f"unknown migration version: {version}"
            ) from exc

    def pending_after(
        self,
        current_version: int,
    ) -> tuple[MigrationDefinition, ...]:
        return tuple(
            migration
            for migration in self._migrations
            if migration.version > current_version
        )


def _apply_baseline_schema(
    connection: Connection,
) -> None:
    """Create the AF-Core v1 baseline tables idempotently."""

    load_database_models()
    Base.metadata.create_all(
        bind=connection
    )


def _apply_project_run_schema(
    connection: Connection,
) -> None:
    """Create durable project-run snapshot and event tables."""

    project_run_metadata.create_all(
        bind=connection,
        checkfirst=True,
    )


def default_migration_registry() -> MigrationRegistry:
    """Return the official AF-Core schema migration chain."""

    return MigrationRegistry(
        (
            MigrationDefinition(
                version=1,
                name="af_core_baseline",
                signature=(
                    "baseline-v1:"
                    "events,projects,runs,tasks"
                ),
                apply=_apply_baseline_schema,
            ),
            MigrationDefinition(
                version=2,
                name="durable_project_runs",
                signature=(
                    "project-runs-v2:"
                    "project_run_snapshots,"
                    "project_run_events;"
                    "optimistic-version;"
                    "ordered-events"
                ),
                apply=_apply_project_run_schema,
            ),
        )
    )


class SchemaMigrationManager:
    """Read, verify and apply the migration chain."""

    def __init__(
        self,
        engine: Engine,
        registry: MigrationRegistry,
        *,
        minimum_supported_version: int = (
            MINIMUM_SUPPORTED_SCHEMA_VERSION
        ),
    ) -> None:
        if minimum_supported_version < 0:
            raise ValueError(
                "minimum supported version "
                "must not be negative"
            )

        self.engine = engine
        self.registry = registry
        self.minimum_supported_version = (
            minimum_supported_version
        )

    def ensure_registry_table(self) -> None:
        """Create the migration history table idempotently."""

        statement = text(
            f"""
            CREATE TABLE IF NOT EXISTS
            {SCHEMA_MIGRATION_TABLE} (
                version INTEGER PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                checksum VARCHAR(64) NOT NULL,
                applied_at VARCHAR(64) NOT NULL
            )
            """
        )

        with self.engine.begin() as connection:
            connection.execute(statement)

    def applied_migrations(
        self,
    ) -> tuple[AppliedMigration, ...]:
        self.ensure_registry_table()

        statement = text(
            f"""
            SELECT version, name, checksum, applied_at
            FROM {SCHEMA_MIGRATION_TABLE}
            ORDER BY version
            """
        )

        with self.engine.connect() as connection:
            rows = connection.execute(
                statement
            ).all()

        return tuple(
            AppliedMigration(
                version=int(row.version),
                name=str(row.name),
                checksum=str(row.checksum),
                applied_at=str(row.applied_at),
            )
            for row in rows
        )

    def assess(
        self,
    ) -> SchemaCompatibilityReport:
        """Verify history and report compatibility."""

        applied = self.applied_migrations()

        versions = tuple(
            record.version
            for record in applied
        )

        expected_versions = tuple(
            range(1, len(applied) + 1)
        )

        if versions != expected_versions:
            raise MigrationIntegrityError(
                "migration history is not contiguous: "
                f"{versions}"
            )

        current_version = (
            versions[-1]
            if versions
            else 0
        )

        target_version = (
            self.registry.target_version
        )

        if current_version > target_version:
            return SchemaCompatibilityReport(
                current_version=current_version,
                target_version=target_version,
                minimum_supported_version=(
                    self.minimum_supported_version
                ),
                pending_versions=(),
                compatible=False,
                requires_migration=False,
                reason=(
                    "database schema is newer than "
                    "the application"
                ),
            )

        for record in applied:
            expected = self.registry.get(
                record.version
            )

            if record.name != expected.name:
                raise MigrationIntegrityError(
                    "migration name mismatch at "
                    f"version {record.version}"
                )

            if record.checksum != expected.checksum:
                raise MigrationIntegrityError(
                    "migration checksum mismatch at "
                    f"version {record.version}"
                )

        if (
            current_version
            < self.minimum_supported_version
        ):
            return SchemaCompatibilityReport(
                current_version=current_version,
                target_version=target_version,
                minimum_supported_version=(
                    self.minimum_supported_version
                ),
                pending_versions=tuple(
                    migration.version
                    for migration
                    in self.registry.pending_after(
                        current_version
                    )
                ),
                compatible=False,
                requires_migration=True,
                reason=(
                    "database schema is older than the "
                    "minimum supported version"
                ),
            )

        pending = self.registry.pending_after(
            current_version
        )

        return SchemaCompatibilityReport(
            current_version=current_version,
            target_version=target_version,
            minimum_supported_version=(
                self.minimum_supported_version
            ),
            pending_versions=tuple(
                migration.version
                for migration in pending
            ),
            compatible=True,
            requires_migration=bool(pending),
            reason=(
                "migration required"
                if pending
                else "schema current"
            ),
        )

    def migrate(
        self,
    ) -> SchemaCompatibilityReport:
        """Apply all pending migrations in order."""

        initial = self.assess()

        if not initial.compatible:
            raise SchemaCompatibilityError(
                initial.reason
            )

        for migration in self.registry.pending_after(
            initial.current_version
        ):
            applied_at = datetime.now(
                timezone.utc
            ).isoformat()

            try:
                with self.engine.begin() as connection:
                    migration.apply(connection)

                    connection.execute(
                        text(
                            f"""
                            INSERT INTO
                            {SCHEMA_MIGRATION_TABLE}
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
                            "version": migration.version,
                            "name": migration.name,
                            "checksum": migration.checksum,
                            "applied_at": applied_at,
                        },
                    )

            except IntegrityError as exc:
                raise MigrationIntegrityError(
                    "migration version was recorded "
                    f"concurrently: {migration.version}"
                ) from exc

            except SQLAlchemyError as exc:
                raise MigrationExecutionError(
                    "database error applying migration "
                    f"{migration.version}: "
                    f"{migration.name}"
                ) from exc

            except Exception as exc:
                raise MigrationExecutionError(
                    "migration failed at version "
                    f"{migration.version}: "
                    f"{migration.name}"
                ) from exc

        final = self.assess()

        if (
            not final.compatible
            or final.requires_migration
        ):
            raise SchemaCompatibilityError(
                "schema did not reach the application "
                "target version"
            )

        return final


class SchemaMigrationGate:
    """Startup gate preventing incompatible database use."""

    def __init__(
        self,
        manager: SchemaMigrationManager,
        *,
        auto_migrate: bool = False,
    ) -> None:
        self.manager = manager
        self.auto_migrate = auto_migrate

    def prepare(
        self,
    ) -> SchemaCompatibilityReport:
        report = self.manager.assess()

        if not report.compatible:
            raise SchemaCompatibilityError(
                report.reason
            )

        if report.requires_migration:
            if not self.auto_migrate:
                versions = ", ".join(
                    str(version)
                    for version
                    in report.pending_versions
                )

                raise SchemaCompatibilityError(
                    "pending schema migrations must be "
                    f"applied before startup: {versions}"
                )

            report = self.manager.migrate()

        if report.current_version != (
            report.target_version
        ):
            raise SchemaCompatibilityError(
                "database schema is not current"
            )

        return report
