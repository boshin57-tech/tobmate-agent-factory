"""Credential-free operational readiness auditing."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from .backup_service import BackupService
from .health import HealthRegistry, HealthStatus
from .recovery_models import RecoveryIntegrityError
from .recovery_service import RecoveryService


_AUDIT_ID = re.compile(
    r"^audit-[0-9a-f]{32}$"
)


class OperationalAuditError(RuntimeError):
    """Base operational audit failure."""


class OperationalAuditPolicyError(
    OperationalAuditError
):
    """Raised when an audit plan is unsafe."""


class OperationalAuditStatus(StrEnum):
    """Operational check and report status."""

    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


class OperationalAuditMetric(BaseModel):
    """Non-sensitive integer evidence metric."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    name: str
    value: int = Field(ge=0)

    @field_validator("name")
    @classmethod
    def validate_name(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if (
            not normalized
            or not normalized.replace(
                "_",
                "",
            ).isalnum()
        ):
            raise ValueError(
                "invalid audit metric name"
            )

        return normalized


class OperationalAuditCheck(BaseModel):
    """One credential-free operational check."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    name: str
    status: OperationalAuditStatus
    required: bool
    summary: str
    metrics: tuple[
        OperationalAuditMetric,
        ...,
    ] = ()

    @field_validator(
        "name",
        "summary",
    )
    @classmethod
    def validate_public_text(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if (
            not normalized
            or len(normalized) > 200
            or "\x00" in normalized
            or "\n" in normalized
            or "\r" in normalized
            or "://" in normalized
        ):
            raise ValueError(
                "invalid public audit text"
            )

        return normalized


class OperationalAuditReport(BaseModel):
    """Immutable public operational audit report."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    schema_version: int = Field(
        default=1,
        ge=1,
    )
    audit_id: str
    generated_at: datetime
    status: OperationalAuditStatus
    backup_id: str | None = None
    checks: tuple[
        OperationalAuditCheck,
        ...,
    ] = Field(min_length=1)

    @field_validator("audit_id")
    @classmethod
    def validate_audit_id(
        cls,
        value: str,
    ) -> str:
        normalized = value.lower()

        if not _AUDIT_ID.fullmatch(
            normalized
        ):
            raise ValueError(
                "invalid operational audit ID"
            )

        return normalized

    @field_validator("generated_at")
    @classmethod
    def validate_generated_at(
        cls,
        value: datetime,
    ) -> datetime:
        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                "generated_at must be "
                "timezone-aware"
            )

        return value


@dataclass(frozen=True, slots=True)
class OperationalAuditPlan:
    """Filesystem and recency audit plan."""

    database_path: Path
    report_path: Path
    artifact_root: Path | None = None
    backup_dir: Path | None = None
    maximum_backup_age: timedelta = (
        timedelta(days=1)
    )
    require_artifacts: bool = False
    require_backup: bool = True
    require_runtime_health: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "database_path",
            Path(self.database_path),
        )
        object.__setattr__(
            self,
            "report_path",
            Path(self.report_path),
        )

        if self.artifact_root is not None:
            object.__setattr__(
                self,
                "artifact_root",
                Path(self.artifact_root),
            )

        if self.backup_dir is not None:
            object.__setattr__(
                self,
                "backup_dir",
                Path(self.backup_dir),
            )


class OperationalAuditService:
    """Run and atomically publish operational audits."""

    def __init__(
        self,
        *,
        backup_service: BackupService | None = None,
        recovery_service: RecoveryService | None = None,
        clock: Callable[[], datetime] = (
            lambda: datetime.now(timezone.utc)
        ),
        id_factory: Callable[[], str] = (
            lambda: f"audit-{uuid.uuid4().hex}"
        ),
    ) -> None:
        self._backup_service = (
            backup_service or BackupService()
        )
        self._recovery_service = (
            recovery_service
            or RecoveryService(
                backup_service=self._backup_service
            )
        )
        self._clock = clock
        self._id_factory = id_factory

    async def run(
        self,
        plan: OperationalAuditPlan,
        *,
        health_registry: HealthRegistry | None = None,
    ) -> OperationalAuditReport:
        generated_at = self._clock()

        if (
            generated_at.tzinfo is None
            or generated_at.utcoffset() is None
        ):
            raise OperationalAuditPolicyError(
                "audit clock must return "
                "a timezone-aware datetime"
            )

        if (
            plan.maximum_backup_age.total_seconds()
            <= 0
        ):
            raise OperationalAuditPolicyError(
                "maximum backup age must be positive"
            )

        audit_id = self._id_factory().lower()

        if not _AUDIT_ID.fullmatch(audit_id):
            raise OperationalAuditPolicyError(
                "invalid operational audit ID"
            )

        checks: list[
            OperationalAuditCheck
        ] = []

        checks.append(
            self._audit_database(
                plan.database_path
            )
        )

        checks.append(
            self._audit_artifacts(
                plan.artifact_root,
                required=plan.require_artifacts,
            )
        )

        backup_check, backup_id = (
            self._audit_backup(
                plan.backup_dir,
                generated_at=generated_at,
                maximum_age=(
                    plan.maximum_backup_age
                ),
                required=plan.require_backup,
            )
        )

        checks.append(backup_check)

        checks.append(
            await self._audit_runtime(
                health_registry,
                required=(
                    plan.require_runtime_health
                ),
            )
        )

        report = OperationalAuditReport(
            audit_id=audit_id,
            generated_at=generated_at,
            status=self._overall_status(checks),
            backup_id=backup_id,
            checks=tuple(checks),
        )

        self._publish_report(
            plan.report_path,
            report,
        )

        return report

    @staticmethod
    def _overall_status(
        checks: list[
            OperationalAuditCheck
        ],
    ) -> OperationalAuditStatus:
        if any(
            check.required
            and check.status
            is OperationalAuditStatus.FAILED
            for check in checks
        ):
            return OperationalAuditStatus.FAILED

        if any(
            check.status
            is not OperationalAuditStatus.PASSED
            for check in checks
        ):
            return OperationalAuditStatus.WARNING

        return OperationalAuditStatus.PASSED

    def _audit_database(
        self,
        database_path: Path,
    ) -> OperationalAuditCheck:
        path = (
            database_path
            .expanduser()
            .absolute()
        )

        try:
            self._require_regular_file(path)

            uri = (
                path.resolve().as_uri()
                + "?mode=ro"
            )

            with sqlite3.connect(
                uri,
                uri=True,
            ) as connection:
                result = connection.execute(
                    "PRAGMA quick_check"
                ).fetchall()

                table_count = connection.execute(
                    "SELECT COUNT(*) "
                    "FROM sqlite_master "
                    "WHERE type = 'table' "
                    "AND name NOT LIKE 'sqlite_%'"
                ).fetchone()[0]

            if result != [("ok",)]:
                raise sqlite3.DatabaseError(
                    "quick check failed"
                )

            return OperationalAuditCheck(
                name="database",
                status=(
                    OperationalAuditStatus.PASSED
                ),
                required=True,
                summary=(
                    "Database integrity check passed"
                ),
                metrics=(
                    OperationalAuditMetric(
                        name="table_count",
                        value=int(table_count),
                    ),
                    OperationalAuditMetric(
                        name="size_bytes",
                        value=path.stat().st_size,
                    ),
                ),
            )

        except Exception:
            return OperationalAuditCheck(
                name="database",
                status=(
                    OperationalAuditStatus.FAILED
                ),
                required=True,
                summary=(
                    "Database integrity check failed"
                ),
            )

    def _audit_artifacts(
        self,
        artifact_root: Path | None,
        *,
        required: bool,
    ) -> OperationalAuditCheck:
        if artifact_root is None:
            return OperationalAuditCheck(
                name="artifacts",
                status=(
                    OperationalAuditStatus.FAILED
                    if required
                    else OperationalAuditStatus.PASSED
                ),
                required=required,
                summary=(
                    "Artifact storage is not configured"
                    if required
                    else "Artifact storage is optional"
                ),
            )

        root = (
            artifact_root
            .expanduser()
            .absolute()
        )

        try:
            self._require_directory(root)

            file_count = 0
            total_size = 0

            for path in root.rglob("*"):
                if path.is_symlink():
                    raise OperationalAuditPolicyError(
                        "artifact symlink rejected"
                    )

                if path.is_dir():
                    continue

                if not path.is_file():
                    raise OperationalAuditPolicyError(
                        "non-regular artifact rejected"
                    )

                file_count += 1
                total_size += path.stat().st_size

            return OperationalAuditCheck(
                name="artifacts",
                status=(
                    OperationalAuditStatus.PASSED
                ),
                required=required,
                summary=(
                    "Artifact storage check passed"
                ),
                metrics=(
                    OperationalAuditMetric(
                        name="file_count",
                        value=file_count,
                    ),
                    OperationalAuditMetric(
                        name="size_bytes",
                        value=total_size,
                    ),
                ),
            )

        except Exception:
            return OperationalAuditCheck(
                name="artifacts",
                status=(
                    OperationalAuditStatus.FAILED
                ),
                required=required,
                summary=(
                    "Artifact storage check failed"
                ),
            )

    def _audit_backup(
        self,
        backup_dir: Path | None,
        *,
        generated_at: datetime,
        maximum_age: timedelta,
        required: bool,
    ) -> tuple[
        OperationalAuditCheck,
        str | None,
    ]:
        if backup_dir is None:
            return (
                OperationalAuditCheck(
                    name="backup",
                    status=(
                        OperationalAuditStatus.FAILED
                        if required
                        else OperationalAuditStatus.PASSED
                    ),
                    required=required,
                    summary=(
                        "Required backup is unavailable"
                        if required
                        else "Backup verification is optional"
                    ),
                ),
                None,
            )

        try:
            verification = (
                self._recovery_service.verify(
                    backup_dir
                )
            )

            manifest = (
                self._backup_service.load_manifest(
                    backup_dir
                )
            )

            age = (
                generated_at
                - manifest.created_at
            )

            if age.total_seconds() < 0:
                return (
                    OperationalAuditCheck(
                        name="backup",
                        status=(
                            OperationalAuditStatus.WARNING
                        ),
                        required=required,
                        summary=(
                            "Backup timestamp is "
                            "later than audit time"
                        ),
                    ),
                    verification.backup_id,
                )

            age_seconds = int(
                age.total_seconds()
            )

            if age > maximum_age:
                status = (
                    OperationalAuditStatus.WARNING
                )
                summary = (
                    "Backup is valid but stale"
                )
            else:
                status = (
                    OperationalAuditStatus.PASSED
                )
                summary = (
                    "Backup verification passed"
                )

            return (
                OperationalAuditCheck(
                    name="backup",
                    status=status,
                    required=required,
                    summary=summary,
                    metrics=(
                        OperationalAuditMetric(
                            name="age_seconds",
                            value=age_seconds,
                        ),
                        OperationalAuditMetric(
                            name="file_count",
                            value=(
                                verification.file_count
                            ),
                        ),
                        OperationalAuditMetric(
                            name="size_bytes",
                            value=(
                                verification
                                .total_size_bytes
                            ),
                        ),
                    ),
                ),
                verification.backup_id,
            )

        except Exception:
            return (
                OperationalAuditCheck(
                    name="backup",
                    status=(
                        OperationalAuditStatus.FAILED
                    ),
                    required=required,
                    summary=(
                        "Backup integrity check failed"
                    ),
                ),
                None,
            )

    async def _audit_runtime(
        self,
        health_registry: HealthRegistry | None,
        *,
        required: bool,
    ) -> OperationalAuditCheck:
        if health_registry is None:
            return OperationalAuditCheck(
                name="runtime",
                status=(
                    OperationalAuditStatus.FAILED
                    if required
                    else OperationalAuditStatus.PASSED
                ),
                required=required,
                summary=(
                    "Runtime health is unavailable"
                    if required
                    else "Runtime health check is optional"
                ),
            )

        try:
            snapshot = (
                await health_registry.snapshot()
            )

            if (
                snapshot.overall
                is HealthStatus.HEALTHY
            ):
                status = (
                    OperationalAuditStatus.PASSED
                )
                summary = (
                    "Runtime health check passed"
                )

            elif (
                snapshot.overall
                is HealthStatus.DEGRADED
            ):
                status = (
                    OperationalAuditStatus.WARNING
                )
                summary = (
                    "Runtime health is degraded"
                )

            else:
                status = (
                    OperationalAuditStatus.FAILED
                )
                summary = (
                    "Runtime health check failed"
                )

            return OperationalAuditCheck(
                name="runtime",
                status=status,
                required=required,
                summary=summary,
                metrics=(
                    OperationalAuditMetric(
                        name="check_count",
                        value=len(
                            snapshot.checks
                        ),
                    ),
                ),
            )

        except Exception:
            return OperationalAuditCheck(
                name="runtime",
                status=(
                    OperationalAuditStatus.FAILED
                ),
                required=required,
                summary=(
                    "Runtime health check failed"
                ),
            )

    @classmethod
    def _publish_report(
        cls,
        report_path: Path,
        report: OperationalAuditReport,
    ) -> None:
        path = (
            report_path
            .expanduser()
            .absolute()
        )

        cls._reject_symlink_components(path)

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        path.parent.chmod(0o750)

        payload = (
            json.dumps(
                report.model_dump(
                    mode="json"
                ),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")

        descriptor, temporary_name = (
            tempfile.mkstemp(
                prefix=f".{path.name}.",
                suffix=".tmp",
                dir=path.parent,
            )
        )

        temporary = Path(temporary_name)

        try:
            with os.fdopen(
                descriptor,
                "wb",
            ) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())

            temporary.chmod(0o640)

            if path.is_symlink():
                raise OperationalAuditPolicyError(
                    "audit report path "
                    "must not be a symlink"
                )

            os.replace(
                temporary,
                path,
            )

            path.chmod(0o640)

            cls._fsync_directory(
                path.parent
            )

        finally:
            if temporary.exists():
                temporary.unlink()

    @classmethod
    def _require_regular_file(
        cls,
        path: Path,
    ) -> None:
        cls._reject_symlink_components(path)

        if (
            path.is_symlink()
            or not path.is_file()
        ):
            raise OperationalAuditPolicyError(
                "required regular file is unavailable"
            )

    @classmethod
    def _require_directory(
        cls,
        path: Path,
    ) -> None:
        cls._reject_symlink_components(path)

        if (
            path.is_symlink()
            or not path.is_dir()
        ):
            raise OperationalAuditPolicyError(
                "required directory is unavailable"
            )

    @staticmethod
    def _reject_symlink_components(
        path: Path,
    ) -> None:
        absolute = path.absolute()
        current = Path(absolute.anchor)

        for part in absolute.parts[1:]:
            current = current / part

            if current.is_symlink():
                raise OperationalAuditPolicyError(
                    "operational audit paths "
                    "must not contain symlinks"
                )

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
