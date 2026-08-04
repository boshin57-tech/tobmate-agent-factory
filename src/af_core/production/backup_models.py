"""Immutable backup plans, manifests and result models."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_BACKUP_ID = re.compile(
    r"^backup-[0-9a-f]{32}$"
)


class BackupError(RuntimeError):
    """Base error for backup operations."""


class BackupPolicyError(BackupError):
    """Raised when a backup violates a safety policy."""


class BackupIntegrityError(BackupError):
    """Raised when backup integrity cannot be established."""


class BackupFileKind(StrEnum):
    """Supported backup payload file categories."""

    DATABASE = "database"
    ARTIFACT = "artifact"


class BackupFileRecord(BaseModel):
    """Immutable hash inventory record."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    relative_path: str
    kind: BackupFileKind
    sha256: str
    size_bytes: int = Field(
        ge=0
    )

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if (
            not normalized
            or normalized.startswith("/")
            or "\\" in normalized
            or "\x00" in normalized
        ):
            raise ValueError(
                "backup path must be a safe "
                "POSIX relative path"
            )

        segments = normalized.split("/")

        if any(
            segment in {
                "",
                ".",
                "..",
            }
            for segment in segments
        ):
            raise ValueError(
                "backup path must not contain "
                "empty or traversal segments"
            )

        return normalized

    @field_validator("sha256")
    @classmethod
    def validate_sha256(
        cls,
        value: str,
    ) -> str:
        normalized = value.lower()

        if not _SHA256.fullmatch(normalized):
            raise ValueError(
                "sha256 must contain 64 "
                "lower-case hexadecimal characters"
            )

        return normalized


class BackupManifest(BaseModel):
    """Immutable manifest for one published backup."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    schema_version: int = Field(
        default=1,
        ge=1,
    )
    backup_id: str
    created_at: datetime
    database_source_name: str
    artifact_source_name: str | None = None
    file_count: int = Field(
        ge=0
    )
    total_size_bytes: int = Field(
        ge=0
    )
    files: tuple[BackupFileRecord, ...]

    @field_validator("backup_id")
    @classmethod
    def validate_backup_id(
        cls,
        value: str,
    ) -> str:
        normalized = value.lower()

        if not _BACKUP_ID.fullmatch(normalized):
            raise ValueError(
                "backup_id must use "
                "backup- plus 32 hexadecimal characters"
            )

        return normalized

    @field_validator(
        "database_source_name",
        "artifact_source_name",
    )
    @classmethod
    def validate_source_name(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()

        if (
            not normalized
            or "/" in normalized
            or "\\" in normalized
            or "\x00" in normalized
            or normalized in {
                ".",
                "..",
            }
        ):
            raise ValueError(
                "backup source name must be a plain name"
            )

        return normalized

    @model_validator(mode="after")
    def validate_inventory(
        self,
    ) -> Self:
        if (
            self.created_at.tzinfo is None
            or self.created_at.utcoffset() is None
        ):
            raise ValueError(
                "created_at must be timezone-aware"
            )

        paths = [
            record.relative_path
            for record in self.files
        ]

        if len(paths) != len(set(paths)):
            raise ValueError(
                "backup file paths must be unique"
            )

        if self.file_count != len(self.files):
            raise ValueError(
                "file_count must match the inventory"
            )

        expected_total = sum(
            record.size_bytes
            for record in self.files
        )

        if self.total_size_bytes != expected_total:
            raise ValueError(
                "total_size_bytes must match "
                "the inventory"
            )

        return self


@dataclass(frozen=True, slots=True)
class BackupPlan:
    """Explicit source and destination backup plan."""

    destination_root: Path
    database_path: Path
    artifact_root: Path | None = None
    backup_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "destination_root",
            Path(self.destination_root),
        )
        object.__setattr__(
            self,
            "database_path",
            Path(self.database_path),
        )

        if self.artifact_root is not None:
            object.__setattr__(
                self,
                "artifact_root",
                Path(self.artifact_root),
            )

        if self.backup_id is not None:
            object.__setattr__(
                self,
                "backup_id",
                self.backup_id.strip().lower(),
            )


@dataclass(frozen=True, slots=True)
class BackupResult:
    """Published backup location and immutable manifest."""

    backup_dir: Path
    manifest_path: Path
    checksum_path: Path
    manifest: BackupManifest
