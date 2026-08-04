import hashlib
import json
import sqlite3
import stat
from datetime import datetime, timezone
from pathlib import Path

import pytest

from af_core.production.backup_models import (
    BackupFileKind,
    BackupFileRecord,
    BackupIntegrityError,
    BackupPlan,
    BackupPolicyError,
)
from af_core.production.backup_service import (
    BackupService,
)


BACKUP_ID = (
    "backup-"
    "0123456789abcdef0123456789abcdef"
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
            "VALUES ('original')"
        )
        connection.commit()


def backup_service() -> BackupService:
    return BackupService(
        clock=lambda: datetime(
            2026,
            8,
            4,
            0,
            0,
            tzinfo=timezone.utc,
        ),
        id_factory=lambda: BACKUP_ID,
    )


def test_backup_record_rejects_traversal():
    with pytest.raises(
        ValueError,
        match="traversal",
    ):
        BackupFileRecord(
            relative_path="../secret",
            kind=BackupFileKind.ARTIFACT,
            sha256="a" * 64,
            size_bytes=1,
        )


def test_backup_creates_consistent_sqlite_snapshot(
    tmp_path: Path,
) -> None:
    database = tmp_path / "source.sqlite3"
    create_database(database)

    result = backup_service().create(
        BackupPlan(
            destination_root=(
                tmp_path / "backups"
            ),
            database_path=database,
        )
    )

    snapshot = (
        result.backup_dir
        / "payload"
        / "database.sqlite3"
    )

    assert snapshot.is_file()
    assert result.manifest.backup_id == (
        BACKUP_ID
    )
    assert result.manifest.file_count == 1
    assert (
        result.manifest.files[0].kind
        is BackupFileKind.DATABASE
    )

    with sqlite3.connect(snapshot) as connection:
        value = connection.execute(
            "SELECT value FROM records"
        ).fetchone()[0]

    assert value == "original"


def test_snapshot_is_independent_from_source(
    tmp_path: Path,
) -> None:
    database = tmp_path / "source.sqlite3"
    create_database(database)

    result = backup_service().create(
        BackupPlan(
            destination_root=(
                tmp_path / "backups"
            ),
            database_path=database,
        )
    )

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE records "
            "SET value = 'changed'"
        )
        connection.commit()

    snapshot = (
        result.backup_dir
        / "payload"
        / "database.sqlite3"
    )

    with sqlite3.connect(snapshot) as connection:
        value = connection.execute(
            "SELECT value FROM records"
        ).fetchone()[0]

    assert value == "original"


def test_artifact_tree_is_copied_and_inventoried(
    tmp_path: Path,
) -> None:
    database = tmp_path / "source.sqlite3"
    create_database(database)

    artifacts = tmp_path / "artifacts"
    (artifacts / "objects").mkdir(
        parents=True
    )
    (artifacts / "metadata").mkdir()

    (artifacts / "objects" / "b.bin").write_bytes(
        b"binary"
    )
    (artifacts / "metadata" / "a.json").write_text(
        '{"status":"ready"}',
        encoding="utf-8",
    )

    result = backup_service().create(
        BackupPlan(
            destination_root=(
                tmp_path / "backups"
            ),
            database_path=database,
            artifact_root=artifacts,
        )
    )

    relative_paths = tuple(
        record.relative_path
        for record in result.manifest.files
    )

    assert relative_paths == tuple(
        sorted(relative_paths)
    )

    assert (
        "payload/artifacts/objects/b.bin"
        in relative_paths
    )
    assert (
        "payload/artifacts/metadata/a.json"
        in relative_paths
    )

    assert (
        result.backup_dir
        / "payload"
        / "artifacts"
        / "objects"
        / "b.bin"
    ).read_bytes() == b"binary"


def test_manifest_checksum_is_published(
    tmp_path: Path,
) -> None:
    database = tmp_path / "source.sqlite3"
    create_database(database)

    result = backup_service().create(
        BackupPlan(
            destination_root=(
                tmp_path / "backups"
            ),
            database_path=database,
        )
    )

    manifest_bytes = (
        result.manifest_path.read_bytes()
    )
    expected = hashlib.sha256(
        manifest_bytes
    ).hexdigest()

    actual = (
        result.checksum_path
        .read_text(encoding="ascii")
        .split()[0]
    )

    assert actual == expected


def test_duplicate_backup_id_is_rejected(
    tmp_path: Path,
) -> None:
    database = tmp_path / "source.sqlite3"
    create_database(database)

    service = backup_service()
    plan = BackupPlan(
        destination_root=(
            tmp_path / "backups"
        ),
        database_path=database,
        backup_id=BACKUP_ID,
    )

    service.create(plan)

    with pytest.raises(
        BackupPolicyError,
        match="already exists",
    ):
        service.create(plan)


def test_database_symlink_is_rejected(
    tmp_path: Path,
) -> None:
    database = tmp_path / "source.sqlite3"
    link = tmp_path / "database-link.sqlite3"

    create_database(database)
    link.symlink_to(database)

    with pytest.raises(
        BackupPolicyError,
        match="symlink",
    ):
        backup_service().create(
            BackupPlan(
                destination_root=(
                    tmp_path / "backups"
                ),
                database_path=link,
            )
        )


def test_artifact_root_symlink_is_rejected(
    tmp_path: Path,
) -> None:
    database = tmp_path / "source.sqlite3"
    artifacts = tmp_path / "artifacts"
    link = tmp_path / "artifact-link"

    create_database(database)
    artifacts.mkdir()
    link.symlink_to(
        artifacts,
        target_is_directory=True,
    )

    with pytest.raises(
        BackupPolicyError,
        match="symlink",
    ):
        backup_service().create(
            BackupPlan(
                destination_root=(
                    tmp_path / "backups"
                ),
                database_path=database,
                artifact_root=link,
            )
        )


def test_artifact_symlink_fails_and_cleans_temp(
    tmp_path: Path,
) -> None:
    database = tmp_path / "source.sqlite3"
    artifacts = tmp_path / "artifacts"
    external = tmp_path / "external.bin"

    create_database(database)
    artifacts.mkdir()
    external.write_bytes(b"external")

    (artifacts / "link.bin").symlink_to(
        external
    )

    destination = tmp_path / "backups"

    with pytest.raises(
        BackupPolicyError,
        match="symlink",
    ):
        backup_service().create(
            BackupPlan(
                destination_root=destination,
                database_path=database,
                artifact_root=artifacts,
            )
        )

    assert list(
        (destination / "temporary").iterdir()
    ) == []


def test_destination_symlink_is_rejected(
    tmp_path: Path,
) -> None:
    database = tmp_path / "source.sqlite3"
    real_destination = tmp_path / "real-backups"
    linked_destination = tmp_path / "linked-backups"

    create_database(database)
    real_destination.mkdir()
    linked_destination.symlink_to(
        real_destination,
        target_is_directory=True,
    )

    with pytest.raises(
        BackupPolicyError,
        match="symlink",
    ):
        backup_service().create(
            BackupPlan(
                destination_root=(
                    linked_destination
                ),
                database_path=database,
            )
        )


def test_overlapping_artifact_and_destination_rejected(
    tmp_path: Path,
) -> None:
    database = tmp_path / "source.sqlite3"
    artifacts = tmp_path / "artifacts"

    create_database(database)
    artifacts.mkdir()

    with pytest.raises(
        BackupPolicyError,
        match="must not overlap",
    ):
        backup_service().create(
            BackupPlan(
                destination_root=(
                    artifacts / "backups"
                ),
                database_path=database,
                artifact_root=artifacts,
            )
        )


def test_invalid_sqlite_source_is_rejected(
    tmp_path: Path,
) -> None:
    database = tmp_path / "invalid.sqlite3"
    database.write_text(
        "not a sqlite database",
        encoding="utf-8",
    )

    with pytest.raises(
        BackupIntegrityError,
        match="SQLite backup failed",
    ):
        backup_service().create(
            BackupPlan(
                destination_root=(
                    tmp_path / "backups"
                ),
                database_path=database,
            )
        )


def test_backup_permissions_are_restrictive(
    tmp_path: Path,
) -> None:
    database = tmp_path / "source.sqlite3"
    create_database(database)

    result = backup_service().create(
        BackupPlan(
            destination_root=(
                tmp_path / "backups"
            ),
            database_path=database,
        )
    )

    snapshot = (
        result.backup_dir
        / "payload"
        / "database.sqlite3"
    )

    assert stat.S_IMODE(
        result.backup_dir.stat().st_mode
    ) == 0o750

    assert stat.S_IMODE(
        snapshot.stat().st_mode
    ) == 0o640

    assert stat.S_IMODE(
        result.manifest_path.stat().st_mode
    ) == 0o640


def test_manifest_can_be_reloaded(
    tmp_path: Path,
) -> None:
    database = tmp_path / "source.sqlite3"
    create_database(database)

    service = backup_service()

    result = service.create(
        BackupPlan(
            destination_root=(
                tmp_path / "backups"
            ),
            database_path=database,
        )
    )

    restored = service.load_manifest(
        result.backup_dir
    )

    assert restored == result.manifest


def test_empty_artifact_root_is_supported(
    tmp_path: Path,
) -> None:
    database = tmp_path / "source.sqlite3"
    artifacts = tmp_path / "artifacts"

    create_database(database)
    artifacts.mkdir()

    result = backup_service().create(
        BackupPlan(
            destination_root=(
                tmp_path / "backups"
            ),
            database_path=database,
            artifact_root=artifacts,
        )
    )

    assert result.manifest.file_count == 1
    assert result.manifest.artifact_source_name == (
        "artifacts"
    )

    payload = json.loads(
        result.manifest_path.read_text(
            encoding="utf-8"
        )
    )

    assert payload["file_count"] == 1
