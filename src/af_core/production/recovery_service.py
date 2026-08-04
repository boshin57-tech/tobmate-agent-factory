"""Verified and atomically staged backup recovery."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import sqlite3
import tempfile
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .backup_models import (
    BackupFileKind,
    BackupIntegrityError,
    BackupManifest,
)
from .backup_service import BackupService
from .recovery_models import (
    RecoveryDrillReport,
    RecoveryDrillResult,
    RecoveryIntegrityError,
    RecoveryPlan,
    RecoveryPolicyError,
    RecoveryResult,
    RecoveryVerification,
)


_CHUNK_SIZE = 1024 * 1024
_RECOVERY_ID = re.compile(
    r"^recovery-[0-9a-f]{32}$"
)


class RecoveryService:
    """Verify backups and publish isolated staged restores."""

    def __init__(
        self,
        *,
        backup_service: BackupService | None = None,
        clock: Callable[[], datetime] = (
            lambda: datetime.now(timezone.utc)
        ),
        id_factory: Callable[[], str] = (
            lambda: f"recovery-{uuid.uuid4().hex}"
        ),
    ) -> None:
        self._backup_service = (
            backup_service or BackupService()
        )
        self._clock = clock
        self._id_factory = id_factory

    def verify(
        self,
        backup_dir: str | Path,
    ) -> RecoveryVerification:
        directory = (
            Path(backup_dir)
            .expanduser()
            .absolute()
        )

        self._require_directory(
            directory,
            role="backup directory",
            integrity=True,
        )

        try:
            manifest = (
                self._backup_service
                .load_manifest(directory)
            )
        except BackupIntegrityError as exc:
            raise RecoveryIntegrityError(
                "backup manifest verification failed"
            ) from exc

        expected_top_level = {
            "manifest.json",
            "manifest.sha256",
            "payload",
        }

        actual_top_level = {
            path.name
            for path in directory.iterdir()
        }

        if actual_top_level != expected_top_level:
            raise RecoveryIntegrityError(
                "backup top-level inventory mismatch"
            )

        payload_dir = directory / "payload"

        self._require_directory(
            payload_dir,
            role="backup payload",
            integrity=True,
        )

        expected_paths = {
            record.relative_path
            for record in manifest.files
        }

        actual_paths: set[str] = set()

        for path in sorted(
            payload_dir.rglob("*")
        ):
            if path.is_symlink():
                raise RecoveryIntegrityError(
                    "backup payload contains a symlink"
                )

            if path.is_dir():
                continue

            if not path.is_file():
                raise RecoveryIntegrityError(
                    "backup payload contains "
                    "a non-regular file"
                )

            actual_paths.add(
                path.relative_to(
                    directory
                ).as_posix()
            )

        if actual_paths != expected_paths:
            raise RecoveryIntegrityError(
                "backup payload inventory mismatch"
            )

        database_records = [
            record
            for record in manifest.files
            if record.kind
            is BackupFileKind.DATABASE
        ]

        if len(database_records) != 1:
            raise RecoveryIntegrityError(
                "backup must contain exactly "
                "one database file"
            )

        for record in manifest.files:
            path = directory.joinpath(
                *PurePosixPath(
                    record.relative_path
                ).parts
            )

            self._require_regular_file(
                path,
                role="backup payload file",
                integrity=True,
            )

            digest, size = self._hash_file(
                path
            )

            if size != record.size_bytes:
                raise RecoveryIntegrityError(
                    "backup payload size mismatch"
                )

            if not hmac.compare_digest(
                digest,
                record.sha256,
            ):
                raise RecoveryIntegrityError(
                    "backup payload checksum mismatch"
                )

        database_record = database_records[0]
        database_path = directory.joinpath(
            *PurePosixPath(
                database_record.relative_path
            ).parts
        )

        self._quick_check_sqlite(
            database_path
        )

        verified_at = self._clock()

        if (
            verified_at.tzinfo is None
            or verified_at.utcoffset() is None
        ):
            raise RecoveryPolicyError(
                "recovery clock must return "
                "a timezone-aware datetime"
            )

        artifact_count = sum(
            1
            for record in manifest.files
            if record.kind
            is BackupFileKind.ARTIFACT
        )

        return RecoveryVerification(
            backup_id=manifest.backup_id,
            verified_at=verified_at,
            file_count=manifest.file_count,
            total_size_bytes=(
                manifest.total_size_bytes
            ),
            artifact_file_count=(
                artifact_count
            ),
            database_relative_path=(
                database_record.relative_path
            ),
        )

    def restore(
        self,
        plan: RecoveryPlan,
    ) -> RecoveryResult:
        backup_dir = (
            plan.backup_dir
            .expanduser()
            .absolute()
        )
        destination_root = (
            plan.destination_root
            .expanduser()
            .absolute()
        )

        verification = self.verify(
            backup_dir
        )

        self._reject_symlink_components(
            destination_root,
            integrity=False,
        )
        self._reject_overlap(
            backup_dir,
            destination_root,
        )

        recovery_id = (
            plan.recovery_id
            or self._id_factory()
        )

        self._validate_recovery_id(
            recovery_id
        )

        recoveries_root = (
            destination_root / "recoveries"
        )
        temporary_root = (
            destination_root / "temporary"
        )

        self._make_directory(
            destination_root
        )
        self._make_directory(
            recoveries_root
        )
        self._make_directory(
            temporary_root
        )

        final_dir = (
            recoveries_root / recovery_id
        )

        if (
            final_dir.exists()
            or final_dir.is_symlink()
        ):
            raise RecoveryPolicyError(
                "recovery already exists: "
                f"{recovery_id}"
            )

        temporary_dir = Path(
            tempfile.mkdtemp(
                prefix=f"{recovery_id}-",
                dir=temporary_root,
            )
        )
        temporary_dir.chmod(0o750)

        try:
            manifest = (
                self._backup_service
                .load_manifest(backup_dir)
            )

            database_record = next(
                record
                for record in manifest.files
                if record.kind
                is BackupFileKind.DATABASE
            )

            database_source = (
                backup_dir.joinpath(
                    *PurePosixPath(
                        database_record.relative_path
                    ).parts
                )
            )
            database_destination = (
                temporary_dir
                / "database.sqlite3"
            )

            self._copy_regular_file(
                database_source,
                database_destination,
            )

            artifact_records = [
                record
                for record in manifest.files
                if record.kind
                is BackupFileKind.ARTIFACT
            ]

            artifact_destination = (
                temporary_dir / "artifacts"
            )

            if (
                artifact_records
                or manifest.artifact_source_name
                is not None
            ):
                self._make_directory(
                    artifact_destination
                )

            artifact_prefix = (
                "payload/artifacts/"
            )

            for record in artifact_records:
                if not record.relative_path.startswith(
                    artifact_prefix
                ):
                    raise RecoveryIntegrityError(
                        "artifact inventory path "
                        "is invalid"
                    )

                relative = record.relative_path[
                    len(artifact_prefix):
                ]

                source = backup_dir.joinpath(
                    *PurePosixPath(
                        record.relative_path
                    ).parts
                )
                destination = (
                    artifact_destination.joinpath(
                        *PurePosixPath(
                            relative
                        ).parts
                    )
                )

                self._copy_regular_file(
                    source,
                    destination,
                )

            self._verify_restored_payload(
                temporary_dir,
                manifest,
            )

            metadata_path = (
                temporary_dir
                / "recovery.json"
            )

            metadata = {
                "schema_version": 1,
                "backup_id": (
                    manifest.backup_id
                ),
                "recovery_id": recovery_id,
                "restored_at": (
                    self._clock().isoformat()
                ),
                "file_count": (
                    manifest.file_count
                ),
                "total_size_bytes": (
                    manifest.total_size_bytes
                ),
                "artifact_file_count": (
                    verification
                    .artifact_file_count
                ),
            }

            self._write_json_file(
                metadata_path,
                metadata,
            )

            self._fsync_tree(
                temporary_dir
            )

            os.replace(
                temporary_dir,
                final_dir,
            )

            self._fsync_directory(
                recoveries_root
            )

        except BaseException:
            if temporary_dir.exists():
                shutil.rmtree(
                    temporary_dir,
                    ignore_errors=True,
                )
            raise

        final_artifact_root = (
            final_dir / "artifacts"
        )

        return RecoveryResult(
            recovery_dir=final_dir,
            database_path=(
                final_dir
                / "database.sqlite3"
            ),
            artifact_root=(
                final_artifact_root
                if final_artifact_root.exists()
                else None
            ),
            metadata_path=(
                final_dir
                / "recovery.json"
            ),
            verification=verification,
        )

    def drill(
        self,
        plan: RecoveryPlan,
    ) -> RecoveryDrillResult:
        recovery = self.restore(plan)

        report = RecoveryDrillReport(
            backup_id=(
                recovery.verification.backup_id
            ),
            recovery_id=(
                recovery.recovery_dir.name
            ),
            completed_at=self._clock(),
            checks=(
                "manifest_checksum",
                "payload_inventory",
                "file_sha256",
                "file_size",
                "sqlite_quick_check",
                "staged_restore",
                "restored_payload_sha256",
                "atomic_publication",
            ),
            file_count=(
                recovery.verification.file_count
            ),
            total_size_bytes=(
                recovery.verification
                .total_size_bytes
            ),
            artifact_file_count=(
                recovery.verification
                .artifact_file_count
            ),
        )

        report_path = (
            recovery.recovery_dir
            / "recovery-drill.json"
        )

        self._atomic_write_json_file(
            report_path,
            report.model_dump(
                mode="json"
            ),
        )

        return RecoveryDrillResult(
            recovery=recovery,
            report_path=report_path,
            report=report,
        )

    def _verify_restored_payload(
        self,
        recovery_root: Path,
        manifest: BackupManifest,
    ) -> None:
        artifact_prefix = (
            "payload/artifacts/"
        )

        for record in manifest.files:
            if (
                record.kind
                is BackupFileKind.DATABASE
            ):
                path = (
                    recovery_root
                    / "database.sqlite3"
                )
            else:
                if not record.relative_path.startswith(
                    artifact_prefix
                ):
                    raise RecoveryIntegrityError(
                        "artifact recovery path "
                        "is invalid"
                    )

                relative = record.relative_path[
                    len(artifact_prefix):
                ]

                path = (
                    recovery_root
                    / "artifacts"
                ).joinpath(
                    *PurePosixPath(
                        relative
                    ).parts
                )

            self._require_regular_file(
                path,
                role="restored payload file",
                integrity=True,
            )

            digest, size = self._hash_file(
                path
            )

            if size != record.size_bytes:
                raise RecoveryIntegrityError(
                    "restored payload size mismatch"
                )

            if not hmac.compare_digest(
                digest,
                record.sha256,
            ):
                raise RecoveryIntegrityError(
                    "restored payload checksum mismatch"
                )

        self._quick_check_sqlite(
            recovery_root
            / "database.sqlite3"
        )

    @staticmethod
    def _quick_check_sqlite(
        path: Path,
    ) -> None:
        uri = path.resolve().as_uri() + (
            "?mode=ro"
        )

        try:
            with sqlite3.connect(
                uri,
                uri=True,
            ) as connection:
                rows = connection.execute(
                    "PRAGMA quick_check"
                ).fetchall()

        except sqlite3.Error as exc:
            raise RecoveryIntegrityError(
                "SQLite recovery integrity "
                "check failed"
            ) from exc

        if rows != [("ok",)]:
            raise RecoveryIntegrityError(
                "SQLite recovery integrity "
                "check failed"
            )

    @staticmethod
    def _hash_file(
        path: Path,
    ) -> tuple[str, int]:
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

        return digest.hexdigest(), size

    @classmethod
    def _copy_regular_file(
        cls,
        source: Path,
        destination: Path,
    ) -> None:
        cls._require_regular_file(
            source,
            role="recovery source",
            integrity=True,
        )

        cls._make_directory(
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

    @classmethod
    def _require_regular_file(
        cls,
        path: Path,
        *,
        role: str,
        integrity: bool,
    ) -> None:
        cls._reject_symlink_components(
            path,
            integrity=integrity,
        )

        if (
            path.is_symlink()
            or not path.is_file()
        ):
            error = (
                RecoveryIntegrityError
                if integrity
                else RecoveryPolicyError
            )

            raise error(
                f"{role} is missing or "
                "not a regular file"
            )

    @classmethod
    def _require_directory(
        cls,
        path: Path,
        *,
        role: str,
        integrity: bool,
    ) -> None:
        cls._reject_symlink_components(
            path,
            integrity=integrity,
        )

        if (
            path.is_symlink()
            or not path.is_dir()
        ):
            error = (
                RecoveryIntegrityError
                if integrity
                else RecoveryPolicyError
            )

            raise error(
                f"{role} is missing or "
                "not a directory"
            )

    @staticmethod
    def _validate_recovery_id(
        value: str,
    ) -> None:
        if not _RECOVERY_ID.fullmatch(
            value.lower()
        ):
            raise RecoveryPolicyError(
                "invalid recovery ID"
            )

    @classmethod
    def _reject_symlink_components(
        cls,
        path: Path,
        *,
        integrity: bool,
    ) -> None:
        absolute = path.absolute()
        current = Path(absolute.anchor)

        for part in absolute.parts[1:]:
            current = current / part

            if current.is_symlink():
                error = (
                    RecoveryIntegrityError
                    if integrity
                    else RecoveryPolicyError
                )

                raise error(
                    "recovery paths must not "
                    "contain symlinks"
                )

    @classmethod
    def _reject_overlap(
        cls,
        backup_dir: Path,
        destination_root: Path,
    ) -> None:
        backup = backup_dir.resolve()
        destination = (
            destination_root.resolve()
        )

        if (
            cls._is_relative_to(
                destination,
                backup,
            )
            or cls._is_relative_to(
                backup,
                destination,
            )
        ):
            raise RecoveryPolicyError(
                "backup source and recovery "
                "destination must not overlap"
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
    def _make_directory(
        path: Path,
    ) -> None:
        path.mkdir(
            parents=True,
            exist_ok=True,
        )
        path.chmod(0o750)

    @staticmethod
    def _write_json_file(
        path: Path,
        payload: dict[str, object],
    ) -> None:
        encoded = (
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")

        with path.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())

        path.chmod(0o640)

    @classmethod
    def _atomic_write_json_file(
        cls,
        path: Path,
        payload: dict[str, object],
    ) -> None:
        temporary = path.with_name(
            f".{path.name}.{uuid.uuid4().hex}.tmp"
        )

        try:
            cls._write_json_file(
                temporary,
                payload,
            )
            os.replace(
                temporary,
                path,
            )
            cls._fsync_directory(
                path.parent
            )
        finally:
            if temporary.exists():
                temporary.unlink()

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
