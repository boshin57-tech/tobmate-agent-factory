"""Durable SQLAlchemy database and transaction boundaries."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
    sessionmaker,
)
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """Shared declarative metadata for AF-Core tables."""


class DatabaseRuntimeError(RuntimeError):
    """Raised when database initialization or access fails."""


@dataclass(frozen=True, slots=True)
class DatabaseHealth:
    """Credential-free database health result."""

    healthy: bool
    dialect: str
    database: str | None
    detail: str


def sqlite_url(path: str | Path) -> str:
    """Return an absolute SQLite URL and create its directory."""

    if str(path) == ":memory:":
        return "sqlite:///:memory:"

    target = Path(path).expanduser().resolve()
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return f"sqlite:///{target}"


def normalize_database_url(
    url: str | URL,
) -> URL:
    """Normalize supported database URLs to explicit drivers."""

    parsed = make_url(url)

    if parsed.drivername in {
        "postgres",
        "postgresql",
    }:
        parsed = parsed.set(
            drivername="postgresql+psycopg"
        )

    return parsed


def _configure_sqlite_connection(
    dbapi_connection: Any,
) -> None:
    """Apply durability and integrity controls to SQLite."""

    cursor = dbapi_connection.cursor()

    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


def create_database_engine(
    url: str | URL,
    *,
    echo: bool = False,
    pool_pre_ping: bool = True,
    pool_recycle_seconds: int = 300,
) -> Engine:
    """Create a dialect-correct SQLAlchemy engine."""

    parsed = normalize_database_url(url)

    options: dict[str, Any] = {
        "echo": echo,
        "future": True,
        "pool_pre_ping": pool_pre_ping,
    }

    if parsed.get_backend_name() == "sqlite":
        options["connect_args"] = {
            "check_same_thread": False,
            "timeout": 30.0,
        }

        if parsed.database in {
            None,
            "",
            ":memory:",
        }:
            options["poolclass"] = StaticPool
    else:
        options["pool_recycle"] = (
            pool_recycle_seconds
        )

    engine = create_engine(
        parsed,
        **options,
    )

    if parsed.get_backend_name() == "sqlite":
        event.listen(
            engine,
            "connect",
            lambda connection, _record: (
                _configure_sqlite_connection(
                    connection
                )
            ),
        )

    return engine


def create_session_factory(
    engine: Engine,
) -> sessionmaker[Session]:
    """Create deterministic AF-Core sessions."""

    return sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
        autoflush=False,
    )


def load_database_models() -> None:
    """Import all mapped models before metadata inspection."""

    from . import tables as _tables

    del _tables


def registered_table_names() -> tuple[str, ...]:
    """Return registered table names deterministically."""

    load_database_models()
    return tuple(sorted(Base.metadata.tables))


def initialize_database(
    engine: Engine,
) -> None:
    """Create the registered baseline schema."""

    load_database_models()
    Base.metadata.create_all(engine)


@contextmanager
def read_session_scope(
    sessions: sessionmaker[Session],
) -> Iterator[Session]:
    """Provide a read session with deterministic closure."""

    session = sessions()

    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def transaction_scope(
    sessions: sessionmaker[Session],
) -> Iterator[Session]:
    """Commit a complete unit or roll it back atomically."""

    session = sessions()

    try:
        with session.begin():
            yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def database_healthcheck(
    engine: Engine,
) -> DatabaseHealth:
    """Execute a credential-free database health query."""

    try:
        with engine.connect() as connection:
            result = connection.execute(
                text("SELECT 1")
            ).scalar_one()

        if result != 1:
            raise DatabaseRuntimeError(
                "database health query returned "
                "an unexpected value"
            )

    except (
        SQLAlchemyError,
        DatabaseRuntimeError,
    ) as exc:
        return DatabaseHealth(
            healthy=False,
            dialect=engine.dialect.name,
            database=engine.url.database,
            detail=type(exc).__name__,
        )

    return DatabaseHealth(
        healthy=True,
        dialect=engine.dialect.name,
        database=engine.url.database,
        detail="ok",
    )


class DatabaseRuntime:
    """Own the database engine and transaction lifecycle."""

    def __init__(
        self,
        engine: Engine,
    ) -> None:
        self.engine = engine
        self.sessions = create_session_factory(
            engine
        )

    @classmethod
    def from_url(
        cls,
        url: str | URL,
        *,
        echo: bool = False,
        pool_pre_ping: bool = True,
        pool_recycle_seconds: int = 300,
    ) -> "DatabaseRuntime":
        return cls(
            create_database_engine(
                url,
                echo=echo,
                pool_pre_ping=pool_pre_ping,
                pool_recycle_seconds=(
                    pool_recycle_seconds
                ),
            )
        )

    def initialize(self) -> None:
        initialize_database(self.engine)

    def health(self) -> DatabaseHealth:
        return database_healthcheck(
            self.engine
        )

    def schema_status(self):
        """Return current application/database schema status."""

        from .migrations import (
            SchemaMigrationManager,
            default_migration_registry,
        )

        manager = SchemaMigrationManager(
            self.engine,
            default_migration_registry(),
        )

        return manager.assess()

    def prepare_schema(
        self,
        *,
        auto_migrate: bool = False,
        minimum_supported_version: int = 0,
    ):
        """Apply or enforce the startup schema gate."""

        from .migrations import (
            SchemaMigrationGate,
            SchemaMigrationManager,
            default_migration_registry,
        )

        manager = SchemaMigrationManager(
            self.engine,
            default_migration_registry(),
            minimum_supported_version=(
                minimum_supported_version
            ),
        )

        return SchemaMigrationGate(
            manager,
            auto_migrate=auto_migrate,
        ).prepare()

    def create_project_run_repository(self):
        """Create a SQL project-run repository after schema gating."""

        from .migrations import (
            APPLICATION_SCHEMA_VERSION,
        )
        from .project_run_repository import (
            SQLAlchemyProjectRunRepository,
        )

        report = self.schema_status()

        if (
            not report.compatible
            or report.requires_migration
            or report.current_version
            != APPLICATION_SCHEMA_VERSION
        ):
            raise DatabaseRuntimeError(
                "database schema must be current before "
                "creating the project-run repository"
            )

        return SQLAlchemyProjectRunRepository(
            self.engine
        )

    @contextmanager
    def read_session(
        self,
    ) -> Iterator[Session]:
        with read_session_scope(
            self.sessions
        ) as session:
            yield session

    @contextmanager
    def transaction(
        self,
    ) -> Iterator[Session]:
        with transaction_scope(
            self.sessions
        ) as session:
            yield session

    def dispose(self) -> None:
        self.engine.dispose()

    def __enter__(
        self,
    ) -> "DatabaseRuntime":
        return self

    def __exit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        del exc_type, exc, traceback
        self.dispose()
