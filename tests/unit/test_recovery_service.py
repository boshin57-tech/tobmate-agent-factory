import json
import sqlite3
import stat
from datetime import datetime, timezone
from pathlib import Path

import pytest

from af_core.production.backup_models import (
    BackupPlan,
)
from af_core.production.backup_service import (
    BackupService,
)
from af_core.production.recovery_models import (
    RecoveryIntegrityError,
    RecoveryPlan,
    RecoveryPolicyError,
)
from af_core.production.recovery_service import (
    RecoveryService,
)


BACKUP_ID = (
    "backup-"
    "0123456789abcdef0123456789abcdef"
)
RECOVERY_ID = (
    "recovery-"
    "fedcba9876543210fedcba9876543210"
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
            "VALUES ('recoverable')"
        )
        connection.commit()


def create_backup(
    tmp_path: Path,
    *,
    with_artifacts: bool = True,
):
    database = tmp_path / "source.sqlite3"
    create_database(database)

    artifacts = tmp_path / "artifacts"

    if with_artifacts:
        (artifacts / "objects").mkdir(
            parents=True
        )
        (artifacts / "metadata").mkdir()

        (
            artifacts
            / "objects"
            / "object.bin"
        ).write_bytes(b"object-data")

        (
            artifacts
            / "metadata"
            / "record.json"
        ).write_text(
            '{"status":"ready"}',
            encoding="utf-8",
        )

    service = BackupService(
        clock=lambda: datetime(
            2026,
            8,
            4,
            1,
            0,
            tzinfo=timezone.utc,
        ),
        id_factory=lambda: BACKUP_ID,
    )

    return service.create(
        BackupPlan(
            destination_root=(
                tmp_path / "backup-root"
            ),
            database_path=database,
            artifact_root=(
                artifacts
                if with_artifacts
                else None
            ),
        )
    )


def recovery_service() -> RecoveryService:
    return RecoveryService(
        clock=lambda: datetime(
            2026,
            8,
            4,
            2,
            0,
            tzinfo=timezone.utc,
        ),
        id_factory=lambda: RECOVERY_ID,
    )


def test_verify_valid_backup(
    tmp_path: Path,
) -> None:
    backup = create_backup(tmp_path)

    verification = (
        recovery_service().verify(
            backup.backup_dir
        )
    )

    assert verification.backup_id == (
        BACKUP_ID
    )
    assert verification.file_count == 3
    assert verification.artifact_file_count == 2
    assert verification.database_relative_path == (
        "payload/database.sqlite3"
    )


def test_verify_rejects_manifest_tampering(
    tmp_path: Path,
) -> None:
    backup = create_backup(tmp_path)

    with backup.manifest_path.open(
        "ab"
    ) as stream:
        stream.write(b" ")

    with pytest.raises(
        RecoveryIntegrityError,
        match="manifest",
    ):
        recovery_service().verify(
            backup.backup_dir
        )


def test_verify_rejects_payload_tampering(
    tmp_path: Path,
) -> None:
    backup = create_backup(tmp_path)

    artifact = (
        backup.backup_dir
        / "payload"
        / "artifacts"
        / "objects"
        / "object.bin"
    )

    artifact.write_bytes(
        b"tampered-object"
    )

    with pytest.raises(
        RecoveryIntegrityError,
        match="size|checksum",
    ):
        recovery_service().verify(
            backup.backup_dir
        )


def test_verify_rejects_missing_payload(
    tmp_path: Path,
) -> None:
    backup = create_backup(tmp_path)

    artifact = (
        backup.backup_dir
        / "payload"
        / "artifacts"
        / "objects"
        / "object.bin"
    )

    artifact.unlink()

    with pytest.raises(
        RecoveryIntegrityError,
        match="inventory",
    ):
        recovery_service().verify(
            backup.backup_dir
        )


def test_verify_rejects_unexpected_payload(
    tmp_path: Path,
) -> None:
    backup = create_backup(tmp_path)

    (
        backup.backup_dir
        / "payload"
        / "unexpected.txt"
    ).write_text(
        "unexpected",
        encoding="utf-8",
    )

    with pytest.raises(
        RecoveryIntegrityError,
        match="inventory",
    ):
        recovery_service().verify(
            backup.backup_dir
        )


def test_verify_rejects_payload_symlink(
    tmp_path: Path,
) -> None:
    backup = create_backup(tmp_path)

    artifact = (
        backup.backup_dir
        / "payload"
        / "artifacts"
        / "objects"
        / "object.bin"
    )
    external = tmp_path / "external.bin"

    artifact.unlink()
    external.write_bytes(b"external")
    artifact.symlink_to(external)

    with pytest.raises(
        RecoveryIntegrityError,
        match="symlink",
    ):
        recovery_service().verify(
            backup.backup_dir
        )


def test_restore_creates_staged_bundle(
    tmp_path: Path,
) -> None:
    backup = create_backup(tmp_path)

    result = recovery_service().restore(
        RecoveryPlan(
            backup_dir=backup.backup_dir,
            destination_root=(
                tmp_path / "recovery-root"
            ),
            recovery_id=RECOVERY_ID,
        )
    )

    assert result.recovery_dir.name == (
        RECOVERY_ID
    )
    assert result.database_path.is_file()
    assert result.metadata_path.is_file()

    with sqlite3.connect(
        result.database_path
    ) as connection:
        value = connection.execute(
            "SELECT value FROM records"
        ).fetchone()[0]

    assert value == "recoverable"


def test_restore_preserves_artifacts(
    tmp_path: Path,
) -> None:
    backup = create_backup(tmp_path)

    result = recovery_service().restore(
        RecoveryPlan(
            backup_dir=backup.backup_dir,
            destination_root=(
                tmp_path / "recovery-root"
            ),
        )
    )

    assert result.artifact_root is not None

    restored = (
        result.artifact_root
        / "objects"
        / "object.bin"
    )

    assert restored.read_bytes() == (
        b"object-data"
    )


def test_duplicate_recovery_id_is_rejected(
    tmp_path: Path,
) -> None:
    backup = create_backup(tmp_path)
    service = recovery_service()

    plan = RecoveryPlan(
        backup_dir=backup.backup_dir,
        destination_root=(
            tmp_path / "recovery-root"
        ),
        recovery_id=RECOVERY_ID,
    )

    service.restore(plan)

    with pytest.raises(
        RecoveryPolicyError,
        match="already exists",
    ):
        service.restore(plan)


def test_destination_symlink_is_rejected(
    tmp_path: Path,
) -> None:
    backup = create_backup(tmp_path)
    real_destination = (
        tmp_path / "real-recovery"
    )
    linked_destination = (
        tmp_path / "linked-recovery"
    )

    real_destination.mkdir()
    linked_destination.symlink_to(
        real_destination,
        target_is_directory=True,
    )

    with pytest.raises(
        RecoveryPolicyError,
        match="symlink",
    ):
        recovery_service().restore(
            RecoveryPlan(
                backup_dir=backup.backup_dir,
                destination_root=(
                    linked_destination
                ),
            )
        )


def test_backup_and_destination_overlap_rejected(
    tmp_path: Path,
) -> None:
    backup = create_backup(tmp_path)

    with pytest.raises(
        RecoveryPolicyError,
        match="overlap",
    ):
        recovery_service().restore(
            RecoveryPlan(
                backup_dir=backup.backup_dir,
                destination_root=(
                    backup.backup_dir
                    / "recovery"
                ),
            )
        )


def test_recovery_permissions_are_restrictive(
    tmp_path: Path,
) -> None:
    backup = create_backup(tmp_path)

    result = recovery_service().restore(
        RecoveryPlan(
            backup_dir=backup.backup_dir,
            destination_root=(
                tmp_path / "recovery-root"
            ),
        )
    )

    assert stat.S_IMODE(
        result.recovery_dir.stat().st_mode
    ) == 0o750

    assert stat.S_IMODE(
        result.database_path.stat().st_mode
    ) == 0o640

    assert stat.S_IMODE(
        result.metadata_path.stat().st_mode
    ) == 0o640


def test_recovery_drill_writes_passed_report(
    tmp_path: Path,
) -> None:
    backup = create_backup(tmp_path)

    drill = recovery_service().drill(
        RecoveryPlan(
            backup_dir=backup.backup_dir,
            destination_root=(
                tmp_path / "recovery-root"
            ),
        )
    )

    assert drill.report.status == "passed"
    assert drill.report_path.is_file()
    assert (
        "sqlite_quick_check"
        in drill.report.checks
    )
    assert (
        "atomic_publication"
        in drill.report.checks
    )

    payload = json.loads(
        drill.report_path.read_text(
            encoding="utf-8"
        )
    )

    assert payload["backup_id"] == (
        BACKUP_ID
    )
    assert payload["recovery_id"] == (
        RECOVERY_ID
    )


def test_drill_report_omits_absolute_paths(
    tmp_path: Path,
) -> None:
    backup = create_backup(tmp_path)

    drill = recovery_service().drill(
        RecoveryPlan(
            backup_dir=backup.backup_dir,
            destination_root=(
                tmp_path / "recovery-root"
            ),
        )
    )

    text = drill.report_path.read_text(
        encoding="utf-8"
    )

    assert str(tmp_path) not in text
    assert "source.sqlite3" not in text
    assert "backup-root" not in text


def test_restore_failure_cleans_temporary_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    backup = create_backup(tmp_path)
    destination = (
        tmp_path / "recovery-root"
    )
    service = recovery_service()

    def fail_verification(
        *args,
        **kwargs,
    ) -> None:
        raise RecoveryIntegrityError(
            "injected restore verification failure"
        )

    monkeypatch.setattr(
        service,
        "_verify_restored_payload",
        fail_verification,
    )

    with pytest.raises(
        RecoveryIntegrityError,
        match="injected",
    ):
        service.restore(
            RecoveryPlan(
                backup_dir=backup.backup_dir,
                destination_root=destination,
            )
        )

    assert list(
        (destination / "temporary").iterdir()
    ) == []

    assert list(
        (destination / "recoveries").iterdir()
    ) == []
