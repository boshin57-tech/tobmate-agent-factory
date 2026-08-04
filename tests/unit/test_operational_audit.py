import sqlite3
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from pathlib import Path

import pytest

from af_core.production.backup_models import (
    BackupPlan,
)
from af_core.production.backup_service import (
    BackupService,
)
from af_core.production.health import (
    HealthRegistry,
    ServiceRuntimeHealthAdapter,
)
from af_core.production.operational_audit import (
    OperationalAuditPlan,
    OperationalAuditService,
    OperationalAuditStatus,
)
from af_core.production.service_runtime import (
    ServiceRuntime,
)


BACKUP_ID = (
    "backup-"
    "0123456789abcdef0123456789abcdef"
)

AUDIT_ID = (
    "audit-"
    "abcdef0123456789abcdef0123456789"
)


def create_database(
    path: Path,
) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE records "
            "(id INTEGER PRIMARY KEY, value TEXT)"
        )
        connection.execute(
            "INSERT INTO records(value) "
            "VALUES ('ready')"
        )
        connection.commit()


def create_backup(
    tmp_path: Path,
    *,
    created_at: datetime,
):
    database = tmp_path / "source.sqlite3"
    create_database(database)

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    (
        artifacts / "object.bin"
    ).write_bytes(
        b"artifact"
    )

    service = BackupService(
        clock=lambda: created_at,
        id_factory=lambda: BACKUP_ID,
    )

    result = service.create(
        BackupPlan(
            destination_root=(
                tmp_path / "backup-root"
            ),
            database_path=database,
            artifact_root=artifacts,
        )
    )

    return database, artifacts, result


def audit_service(
    now: datetime,
) -> OperationalAuditService:
    return OperationalAuditService(
        clock=lambda: now,
        id_factory=lambda: AUDIT_ID,
    )


@pytest.mark.asyncio
async def test_complete_operational_audit_passes(
    tmp_path: Path,
) -> None:
    now = datetime(
        2026,
        8,
        4,
        4,
        0,
        tzinfo=timezone.utc,
    )

    database, artifacts, backup = (
        create_backup(
            tmp_path,
            created_at=(
                now - timedelta(hours=1)
            ),
        )
    )

    runtime = ServiceRuntime()

    health = HealthRegistry(
        ServiceRuntimeHealthAdapter(
            runtime
        ).checks()
    )

    await runtime.start()

    report_path = (
        tmp_path
        / "reports"
        / "audit.json"
    )

    report = await audit_service(now).run(
        OperationalAuditPlan(
            database_path=database,
            artifact_root=artifacts,
            backup_dir=backup.backup_dir,
            report_path=report_path,
            require_artifacts=True,
        ),
        health_registry=health,
    )

    await runtime.stop(reason="test")

    assert report.status is (
        OperationalAuditStatus.PASSED
    )
    assert report.backup_id == BACKUP_ID
    assert report_path.is_file()

    assert tuple(
        check.name
        for check in report.checks
    ) == (
        "database",
        "artifacts",
        "backup",
        "runtime",
    )


@pytest.mark.asyncio
async def test_corrupt_database_fails_audit(
    tmp_path: Path,
) -> None:
    database = (
        tmp_path / "invalid.sqlite3"
    )

    database.write_text(
        "not sqlite",
        encoding="utf-8",
    )

    report = await audit_service(
        datetime.now(timezone.utc)
    ).run(
        OperationalAuditPlan(
            database_path=database,
            report_path=(
                tmp_path / "audit.json"
            ),
            require_backup=False,
            require_runtime_health=False,
        )
    )

    assert report.status is (
        OperationalAuditStatus.FAILED
    )

    database_check = report.checks[0]

    assert database_check.name == (
        "database"
    )
    assert database_check.status is (
        OperationalAuditStatus.FAILED
    )


@pytest.mark.asyncio
async def test_artifact_symlink_fails_required_check(
    tmp_path: Path,
) -> None:
    database = (
        tmp_path / "source.sqlite3"
    )
    artifacts = tmp_path / "artifacts"
    external = tmp_path / "external.bin"

    create_database(database)
    artifacts.mkdir()
    external.write_bytes(b"external")

    (
        artifacts / "link.bin"
    ).symlink_to(external)

    report = await audit_service(
        datetime.now(timezone.utc)
    ).run(
        OperationalAuditPlan(
            database_path=database,
            artifact_root=artifacts,
            report_path=(
                tmp_path / "audit.json"
            ),
            require_artifacts=True,
            require_backup=False,
            require_runtime_health=False,
        )
    )

    assert report.status is (
        OperationalAuditStatus.FAILED
    )
    assert report.checks[1].status is (
        OperationalAuditStatus.FAILED
    )


@pytest.mark.asyncio
async def test_stale_backup_produces_warning(
    tmp_path: Path,
) -> None:
    now = datetime(
        2026,
        8,
        4,
        5,
        0,
        tzinfo=timezone.utc,
    )

    database, artifacts, backup = (
        create_backup(
            tmp_path,
            created_at=(
                now - timedelta(days=3)
            ),
        )
    )

    report = await audit_service(now).run(
        OperationalAuditPlan(
            database_path=database,
            artifact_root=artifacts,
            backup_dir=backup.backup_dir,
            report_path=(
                tmp_path / "audit.json"
            ),
            maximum_backup_age=(
                timedelta(days=1)
            ),
            require_runtime_health=False,
        )
    )

    assert report.status is (
        OperationalAuditStatus.WARNING
    )
    assert report.checks[2].summary == (
        "Backup is valid but stale"
    )


@pytest.mark.asyncio
async def test_missing_required_backup_fails(
    tmp_path: Path,
) -> None:
    database = (
        tmp_path / "source.sqlite3"
    )
    create_database(database)

    report = await audit_service(
        datetime.now(timezone.utc)
    ).run(
        OperationalAuditPlan(
            database_path=database,
            report_path=(
                tmp_path / "audit.json"
            ),
            require_backup=True,
            require_runtime_health=False,
        )
    )

    assert report.status is (
        OperationalAuditStatus.FAILED
    )
    assert report.checks[2].status is (
        OperationalAuditStatus.FAILED
    )


@pytest.mark.asyncio
async def test_tampered_backup_fails(
    tmp_path: Path,
) -> None:
    now = datetime.now(timezone.utc)

    database, artifacts, backup = (
        create_backup(
            tmp_path,
            created_at=now,
        )
    )

    payload = (
        backup.backup_dir
        / "payload"
        / "artifacts"
        / "object.bin"
    )

    payload.write_bytes(b"tampered")

    report = await audit_service(now).run(
        OperationalAuditPlan(
            database_path=database,
            artifact_root=artifacts,
            backup_dir=backup.backup_dir,
            report_path=(
                tmp_path / "audit.json"
            ),
            require_runtime_health=False,
        )
    )

    assert report.status is (
        OperationalAuditStatus.FAILED
    )
    assert report.checks[2].status is (
        OperationalAuditStatus.FAILED
    )


import json
import stat

from af_core.production.health import (
    HealthCheck,
    HealthScope,
)
from af_core.production.operational_audit import (
    OperationalAuditPolicyError,
)


@pytest.mark.asyncio
async def test_unhealthy_runtime_fails_required_check(
    tmp_path: Path,
) -> None:
    database = (
        tmp_path / "source.sqlite3"
    )
    create_database(database)

    runtime = ServiceRuntime()

    health = HealthRegistry(
        ServiceRuntimeHealthAdapter(
            runtime
        ).checks()
    )

    report = await audit_service(
        datetime.now(timezone.utc)
    ).run(
        OperationalAuditPlan(
            database_path=database,
            report_path=(
                tmp_path / "audit.json"
            ),
            require_backup=False,
        ),
        health_registry=health,
    )

    assert report.status is (
        OperationalAuditStatus.FAILED
    )
    assert report.checks[3].status is (
        OperationalAuditStatus.FAILED
    )


@pytest.mark.asyncio
async def test_degraded_runtime_produces_warning(
    tmp_path: Path,
) -> None:
    database = (
        tmp_path / "source.sqlite3"
    )
    create_database(database)

    health = HealthRegistry(
        (
            HealthCheck(
                "optional-cache",
                lambda: False,
                scopes=frozenset(
                    {
                        HealthScope.STARTUP,
                        HealthScope.LIVENESS,
                        HealthScope.READINESS,
                    }
                ),
                required=False,
            ),
        )
    )

    report = await audit_service(
        datetime.now(timezone.utc)
    ).run(
        OperationalAuditPlan(
            database_path=database,
            report_path=(
                tmp_path / "audit.json"
            ),
            require_backup=False,
        ),
        health_registry=health,
    )

    assert report.status is (
        OperationalAuditStatus.WARNING
    )
    assert report.checks[3].status is (
        OperationalAuditStatus.WARNING
    )


@pytest.mark.asyncio
async def test_report_omits_absolute_paths_and_secrets(
    tmp_path: Path,
) -> None:
    database = (
        tmp_path
        / "postgresql-secret-database.sqlite3"
    )
    create_database(database)

    def failing_health() -> bool:
        raise RuntimeError(
            "postgresql://user:secret@host/db"
        )

    health = HealthRegistry(
        (
            HealthCheck(
                "database-connection",
                failing_health,
            ),
        )
    )

    report_path = (
        tmp_path
        / "reports"
        / "audit.json"
    )

    await audit_service(
        datetime.now(timezone.utc)
    ).run(
        OperationalAuditPlan(
            database_path=database,
            report_path=report_path,
            require_backup=False,
        ),
        health_registry=health,
    )

    text = report_path.read_text(
        encoding="utf-8"
    )

    assert str(tmp_path) not in text
    assert "postgresql://" not in text
    assert "secret" not in text
    assert "database.sqlite3" not in text


@pytest.mark.asyncio
async def test_report_permissions_are_restrictive(
    tmp_path: Path,
) -> None:
    database = (
        tmp_path / "source.sqlite3"
    )
    create_database(database)

    report_path = (
        tmp_path
        / "reports"
        / "audit.json"
    )

    await audit_service(
        datetime.now(timezone.utc)
    ).run(
        OperationalAuditPlan(
            database_path=database,
            report_path=report_path,
            require_backup=False,
            require_runtime_health=False,
        )
    )

    assert stat.S_IMODE(
        report_path.stat().st_mode
    ) == 0o640

    assert stat.S_IMODE(
        report_path.parent.stat().st_mode
    ) == 0o750


@pytest.mark.asyncio
async def test_report_is_atomically_replaced(
    tmp_path: Path,
) -> None:
    database = (
        tmp_path / "source.sqlite3"
    )
    create_database(database)

    report_path = (
        tmp_path / "audit.json"
    )

    report_path.write_text(
        "old report",
        encoding="utf-8",
    )

    report = await audit_service(
        datetime.now(timezone.utc)
    ).run(
        OperationalAuditPlan(
            database_path=database,
            report_path=report_path,
            require_backup=False,
            require_runtime_health=False,
        )
    )

    payload = json.loads(
        report_path.read_text(
            encoding="utf-8"
        )
    )

    assert payload["audit_id"] == (
        report.audit_id
    )

    assert list(
        tmp_path.glob(
            ".audit.json.*.tmp"
        )
    ) == []


@pytest.mark.asyncio
async def test_naive_audit_clock_is_rejected(
    tmp_path: Path,
) -> None:
    database = (
        tmp_path / "source.sqlite3"
    )
    create_database(database)

    service = OperationalAuditService(
        clock=lambda: datetime(
            2026,
            8,
            4,
            6,
            0,
        ),
        id_factory=lambda: AUDIT_ID,
    )

    with pytest.raises(
        OperationalAuditPolicyError,
        match="timezone-aware",
    ):
        await service.run(
            OperationalAuditPlan(
                database_path=database,
                report_path=(
                    tmp_path / "audit.json"
                ),
                require_backup=False,
                require_runtime_health=False,
            )
        )
