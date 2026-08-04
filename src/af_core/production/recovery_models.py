"""Recovery verification, staged restore and drill models."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


_RECOVERY_ID = re.compile(
    r"^recovery-[0-9a-f]{32}$"
)


class RecoveryError(RuntimeError):
    """Base recovery operation failure."""


class RecoveryPolicyError(RecoveryError):
    """Raised when a recovery safety policy is violated."""


class RecoveryIntegrityError(RecoveryError):
    """Raised when backup or restored data fails verification."""


@dataclass(frozen=True, slots=True)
class RecoveryPlan:
    """Staged recovery destination plan."""

    backup_dir: Path
    destination_root: Path
    recovery_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "backup_dir",
            Path(self.backup_dir),
        )
        object.__setattr__(
            self,
            "destination_root",
            Path(self.destination_root),
        )

        if self.recovery_id is not None:
            object.__setattr__(
                self,
                "recovery_id",
                self.recovery_id.strip().lower(),
            )


@dataclass(frozen=True, slots=True)
class RecoveryVerification:
    """Successful backup verification evidence."""

    backup_id: str
    verified_at: datetime
    file_count: int
    total_size_bytes: int
    artifact_file_count: int
    database_relative_path: str


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    """Atomically published staged recovery."""

    recovery_dir: Path
    database_path: Path
    artifact_root: Path | None
    metadata_path: Path
    verification: RecoveryVerification


class RecoveryDrillReport(BaseModel):
    """Credential-free disaster recovery drill report."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    schema_version: int = Field(
        default=1,
        ge=1,
    )
    backup_id: str
    recovery_id: str
    completed_at: datetime
    status: Literal["passed"] = "passed"
    checks: tuple[str, ...] = Field(
        min_length=1
    )
    file_count: int = Field(
        ge=1
    )
    total_size_bytes: int = Field(
        ge=0
    )
    artifact_file_count: int = Field(
        ge=0
    )

    @field_validator("recovery_id")
    @classmethod
    def validate_recovery_id(
        cls,
        value: str,
    ) -> str:
        normalized = value.lower()

        if not _RECOVERY_ID.fullmatch(
            normalized
        ):
            raise ValueError(
                "invalid recovery ID"
            )

        return normalized

    @model_validator(mode="after")
    def validate_time(
        self,
    ) -> Self:
        if (
            self.completed_at.tzinfo is None
            or self.completed_at.utcoffset()
            is None
        ):
            raise ValueError(
                "completed_at must be "
                "timezone-aware"
            )

        return self


@dataclass(frozen=True, slots=True)
class RecoveryDrillResult:
    """Recovery bundle and its drill report."""

    recovery: RecoveryResult
    report_path: Path
    report: RecoveryDrillReport
