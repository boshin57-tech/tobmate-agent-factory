"""Atomic SQLite and artifact backup publication."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from .backup_models import (
    BackupFileKind,
    BackupFileRecord,
    BackupIntegrityError,
    BackupManifest,
    BackupPlan,
    BackupPolicyError,
    BackupResult,
)


_CHUNK_SIZE = 1024 * 1024


class BackupService:
    """Create immutable, checksummed filesystem backups."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = (
            lambda: datetime.now(timezone.utc)
        ),
        id_factory: Callable[[], str] = (
            lambda: f"backup-{uuid.uuid4().hex}"
        ),
    ) -> None:
        self._clock = clock
        self._id_factory = id_factory

    def create(
        self,
        plan: BackupPlan,
    ) -> BackupResult:
        destination_root = (
            plan.destination_root
            .expanduser()
            .absolute()
        )
        database_path = (
            plan.database_path
            .expanduser()
            .absolute()
        )

        artifact_root = (
            None
            if plan.artifact_root is None
            else (
                plan.artifact_root
                .expanduser()
                .absolute()
            )
        )

        self._reject_symlink_components(
            destination_root
        )
        self._require_regular_file(
            database_path,
            role="database",
        )

        if artifact_root is not None:
            self._require_directory(
                artifact_root,
                role="artifact root",
            )
            self._reject_overlap(
                destination_root,
                artifact_root,
            )

        backup_id = (
            plan.backup_id
            or self._id_factory()
        )

        self._validate_backup_id(
            backup_id
        )

        created_at = self._clock()

        if (
            created_at.tzinfo is None
            or created_at.utcoffset() is None
        ):
            raise BackupPolicyError(
                "backup clock must return "
                "a timezone-aware datetime"
            )

        backups_root = (
            destination_root / "backups"
        )
        temporary_root = (
            destination_root / "temporary"
        )

        self._make_directory(
            destination_root
        )
        self._make_directory(
            backups_root
        )
        self._make_directory(
            temporary_root
        )

        final_dir = backups_root / backup_id

        if (
            final_dir.exists()
            or final_dir.is_symlink()
        ):
            raise BackupPolicyError(
                f"backup already exists: {backup_id}"
            )

        temporary_dir = Path(
            tempfile.mkdtemp(
                prefix=f"{backup_id}-",
                dir=temporary_root,
            )
        )
        temporary_dir.chmod(0o750)

        try:
            payload_dir = (
                temporary_dir / "payload"
            )
            self._make_directory(
                payload_dir
            )

            records: list[
                BackupFileRecord
            ] = []

            database_destination = (
                payload_dir
                / "database.sqlite3"
            )

            self._snapshot_sqlite(
                database_path,
                database_destination,
            )

            records.append(
                self._inventory_file(
                    temporary_dir,
                    database_destination,
                    BackupFileKind.DATABASE,
                )
            )

            if artifact_root is not None:
                artifact_destination = (
                    payload_dir / "artifacts"
                )
                self._make_directory(
                    artifact_destination
                )

                records.extend(
                    self._copy_artifact_tree(
                        artifact_root,
                        artifact_destination,
                        temporary_dir,
                    )
                )

            records.sort(
                key=lambda record: (
                    record.relative_path
                )
            )

            manifest = BackupManifest(
                backup_id=backup_id,
                created_at=created_at,
                database_source_name=(
                    database_path.name
                ),
                artifact_source_name=(
                    None
                    if artifact_root is None
                    else artifact_root.name
                ),
                file_count=len(records),
                total_size_bytes=sum(
                    record.size_bytes
                    for record in records
                ),
                files=tuple(records),
            )

            manifest_path = (
                temporary_dir / "manifest.json"
            )
            checksum_path = (
                temporary_dir
                / "manifest.sha256"
            )

            manifest_bytes = (
                self._manifest_bytes(
                    manifest
                )
            )

            self._write_file(
                manifest_path,
                manifest_bytes,
            )

            manifest_digest = hashlib.sha256(
                manifest_bytes
            ).hexdigest()

            self._write_file(
                checksum_path,
                (
                    f"{manifest_digest}  "
                    "manifest.json\n"
                ).encode("ascii"),
            )

            self._fsync_tree(
                temporary_dir
            )

            os.replace(
                temporary_dir,
                final_dir,
            )

            self._fsync_directory(
                backups_root
            )

        except BaseException:
            if temporary_dir.exists():
                shutil.rmtree(
                    temporary_dir,
                    ignore_errors=True,
                )
            raise

        return BackupResult(
            backup_dir=final_dir,
            manifest_path=(
                final_dir / "manifest.json"
            ),
            checksum_path=(
                final_dir
                / "manifest.sha256"
            ),
            manifest=manifest,
        )

    def load_manifest(
        self,
        backup_dir: str | Path,
    ) -> BackupManifest:
        """Load and checksum-verify a published manifest."""

        directory = (
            Path(backup_dir)
            .expanduser()
            .absolute()
        )

        self._require_directory(
            directory,
            role="backup directory",
        )

        manifest_path = (
            directory / "manifest.json"
        )
        checksum_path = (
            directory / "manifest.sha256"
        )

        self._require_regular_file(
            manifest_path,
            role="backup manifest",
        )
        self._require_regular_file(
            checksum_path,
            role="manifest checksum",
        )

        manifest_bytes = (
            manifest_path.read_bytes()
        )
        checksum_text = (
            checksum_path.read_text(
                encoding="ascii"
            )
        )

        fields = checksum_text.strip().split()

        if (
            len(fields) != 2
            or fields[1] != "manifest.json"
        ):
            raise BackupIntegrityError(
                "manifest checksum file is invalid"
            )

        expected = fields[0].lower()
        actual = hashlib.sha256(
            manifest_bytes
        ).hexdigest()

        if expected != actual:
            raise BackupIntegrityError(
                "manifest checksum mismatch"
            )

        try:
            manifest = (
                BackupManifest
                .model_validate_json(
                    manifest_bytes
                )
            )
        except Exception as exc:
            raise BackupIntegrityError(
                "backup manifest is invalid"
            ) from exc

        if manifest.backup_id != directory.name:
            raise BackupIntegrityError(
                "backup directory and manifest "
                "identity do not match"
            )

        return manifest

    def _snapshot_sqlite(
        self,
        source: Path,
        destination: Path,
    ) -> None:
        self._make_directory(
            destination.parent
        )

        source_uri = (
            source.resolve().as_uri()
            + "?mode=ro"
        )

        try:
            with sqlite3.connect(
                source_uri,
                uri=True,
            ) as source_connection:
                with sqlite3.connect(
                    destination
                ) as destination_connection:
                    source_connection.backup(
                        destination_connection
                    )

                    rows = (
                        destination_connection
                        .execute(
                            "PRAGMA quick_check"
                        )
                        .fetchall()
                    )

                    if rows != [("ok",)]:
                        raise BackupIntegrityError(
                            "SQLite snapshot "
                            "integrity check failed"
                        )

                    destination_connection.commit()

        except BackupIntegrityError:
            raise

        except sqlite3.Error as exc:
            raise BackupIntegrityError(
                "SQLite backup failed"
            ) from exc

        destination.chmod(0o640)

        with destination.open("rb") as stream:
            os.fsync(stream.fileno())

    def _copy_artifact_tree(
        self,
        source_root: Path,
        destination_root: Path,
        backup_root: Path,
    ) -> list[BackupFileRecord]:
        records: list[
            BackupFileRecord
        ] = []

        entries = sorted(
            source_root.rglob("*"),
            key=lambda path: (
                path.relative_to(
                    source_root
                ).as_posix()
            ),
        )

        for source in entries:
            relative = source.relative_to(
                source_root
            )
            destination = (
                destination_root / relative
            )

            if source.is_symlink():
                raise BackupPolicyError(
                    "artifact snapshot must not "
                    f"contain symlinks: {relative}"
                )

            if source.is_dir():
                self._make_directory(
                    destination
                )
                continue

            if not source.is_file():
                raise BackupPolicyError(
                    "artifact snapshot contains "
                    f"a non-regular file: {relative}"
                )

            self._copy_regular_file(
                source,
                destination,
            )

            records.append(
                self._inventory_file(
                    backup_root,
                    destination,
                    BackupFileKind.ARTIFACT,
                )
            )

        return records

    def _copy_regular_file(
        self,
        source: Path,
        destination: Path,
    ) -> None:
        if source.is_symlink():
            raise BackupPolicyError(
                f"source file is a symlink: {source}"
            )

        self._make_directory(
            destination.parent
        )

        with source.open("rb") as reader:
            with destination.open("xb") as writer:
                while True:
                    chunk = reader.read(
                        _CHUNK_SIZE
                    )

                    if not chunk:
                        break

                    writer.write(chunk)

                writer.flush()
                os.fsync(writer.fileno())

        destination.chmod(0o640)

    def _inventory_file(
        self,
        backup_root: Path,
        path: Path,
        kind: BackupFileKind,
    ) -> BackupFileRecord:
        digest = hashlib.sha256()
        size = 0

        with path.open("rb") as stream:
            while True:
                chunk = stream.read(
                    _CHUNK_SIZE
                )

                if not chunk:
                    break

                digest.update(chunk)
                size += len(chunk)

        return BackupFileRecord(
            relative_path=(
                path.relative_to(
                    backup_root
                ).as_posix()
            ),
            kind=kind,
            sha256=digest.hexdigest(),
            size_bytes=size,
        )

    @staticmethod
    def _manifest_bytes(
        manifest: BackupManifest,
    ) -> bytes:
        return (
            json.dumps(
                manifest.model_dump(
                    mode="json"
                ),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")

    @staticmethod
    def _write_file(
        path: Path,
        payload: bytes,
    ) -> None:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

        path.chmod(0o640)

    @classmethod
    def _require_regular_file(
        cls,
        path: Path,
        *,
        role: str,
    ) -> None:
        cls._reject_symlink_components(
            path
        )

        if (
            path.is_symlink()
            or not path.is_file()
        ):
            raise BackupPolicyError(
                f"{role} must be a regular file: "
                f"{path}"
            )

    @classmethod
    def _require_directory(
        cls,
        path: Path,
        *,
        role: str,
    ) -> None:
        cls._reject_symlink_components(
            path
        )

        if (
            path.is_symlink()
            or not path.is_dir()
        ):
            raise BackupPolicyError(
                f"{role} must be a directory: "
                f"{path}"
            )

    @staticmethod
    def _validate_backup_id(
        backup_id: str,
    ) -> None:
        try:
            BackupManifest(
                backup_id=backup_id,
                created_at=datetime.now(
                    timezone.utc
                ),
                database_source_name="database",
                file_count=0,
                total_size_bytes=0,
                files=(),
            )
        except Exception as exc:
            raise BackupPolicyError(
                f"invalid backup ID: {backup_id}"
            ) from exc

    @classmethod
    def _reject_overlap(
        cls,
        destination: Path,
        source: Path,
    ) -> None:
        destination_resolved = (
            destination.resolve()
        )
        source_resolved = source.resolve()

        if (
            cls._is_relative_to(
                destination_resolved,
                source_resolved,
            )
            or cls._is_relative_to(
                source_resolved,
                destination_resolved,
            )
        ):
            raise BackupPolicyError(
                "backup destination and artifact "
                "source must not overlap"
            )

    @staticmethod
    def _is_relative_to(
        path: Path,
        parent: Path,
    ) -> bool:
        try:
            path.relative_to(parent)
        except ValueError:
            return False

        return True

    @staticmethod
    def _reject_symlink_components(
        path: Path,
    ) -> None:
        absolute = path.absolute()
        current = Path(
            absolute.anchor
        )

        for part in absolute.parts[1:]:
            current = current / part

            if current.is_symlink():
                raise BackupPolicyError(
                    "backup paths must not contain "
                    f"symlinks: {current}"
                )

    @staticmethod
    def _make_directory(
        path: Path,
    ) -> None:
        path.mkdir(
            parents=True,
            exist_ok=True,
        )
        path.chmod(0o750)

    @staticmethod
    def _fsync_directory(
        path: Path,
    ) -> None:
        descriptor = os.open(
            path,
            os.O_RDONLY,
        )

        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @classmethod
    def _fsync_tree(
        cls,
        root: Path,
    ) -> None:
        directories = [
            path
            for path in root.rglob("*")
            if path.is_dir()
        ]

        directories.sort(
            key=lambda path: len(path.parts),
            reverse=True,
        )

        for directory in directories:
            cls._fsync_directory(
                directory
            )

        cls._fsync_directory(root)
