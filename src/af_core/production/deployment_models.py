"""Immutable deployment package and release manifest models."""

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
_RELEASE_ID = re.compile(
    r"^release-[0-9a-f]{32}$"
)
_APPLICATION_NAME = re.compile(
    r"^[a-z0-9][a-z0-9-]{0,62}$"
)
_VERSION = re.compile(
    r"^[0-9]+\.[0-9]+\.[0-9]+"
    r"(?:[-+][0-9A-Za-z.-]+)?$"
)
_GIT_COMMIT = re.compile(
    r"^[0-9a-f]{7,64}$"
)


class DeploymentError(RuntimeError):
    """Base deployment packaging failure."""


class DeploymentPolicyError(DeploymentError):
    """Raised when a deployment policy is violated."""


class DeploymentIntegrityError(DeploymentError):
    """Raised when package integrity cannot be verified."""


class DeploymentFileKind(StrEnum):
    """Supported release payload categories."""

    WHEEL = "wheel"
    SOURCE_ARCHIVE = "source_archive"
    CONFIGURATION = "configuration"
    RUNBOOK = "runbook"
    SERVICE_UNIT = "service_unit"
    OTHER = "other"


class ReleaseIdentity(BaseModel):
    """Immutable release identity."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    release_id: str
    application_name: str
    version: str
    git_commit: str

    @field_validator("release_id")
    @classmethod
    def validate_release_id(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().lower()

        if not _RELEASE_ID.fullmatch(
            normalized
        ):
            raise ValueError(
                "release_id must use release- "
                "plus 32 hexadecimal characters"
            )

        return normalized

    @field_validator("application_name")
    @classmethod
    def validate_application_name(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().lower()

        if not _APPLICATION_NAME.fullmatch(
            normalized
        ):
            raise ValueError(
                "invalid application name"
            )

        return normalized

    @field_validator("version")
    @classmethod
    def validate_version(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not _VERSION.fullmatch(
            normalized
        ):
            raise ValueError(
                "invalid release version"
            )

        return normalized

    @field_validator("git_commit")
    @classmethod
    def validate_git_commit(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().lower()

        if not _GIT_COMMIT.fullmatch(
            normalized
        ):
            raise ValueError(
                "invalid Git commit identity"
            )

        return normalized


class DeploymentFileRecord(BaseModel):
    """Immutable release payload inventory record."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    relative_path: str
    kind: DeploymentFileKind
    sha256: str
    size_bytes: int = Field(ge=0)
    executable: bool = False

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
                "deployment path must be a safe "
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
                "deployment path must not contain "
                "empty or traversal segments"
            )

        return normalized

    @field_validator("sha256")
    @classmethod
    def validate_sha256(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().lower()

        if not _SHA256.fullmatch(
            normalized
        ):
            raise ValueError(
                "sha256 must contain 64 "
                "lower-case hexadecimal characters"
            )

        return normalized


class DeploymentManifest(BaseModel):
    """Immutable deployment package manifest."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    schema_version: int = Field(
        default=1,
        ge=1,
    )
    identity: ReleaseIdentity
    created_at: datetime
    python_requires: str
    file_count: int = Field(ge=1)
    total_size_bytes: int = Field(ge=0)
    files: tuple[
        DeploymentFileRecord,
        ...,
    ] = Field(min_length=1)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(
        cls,
        value: datetime,
    ) -> datetime:
        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                "created_at must be timezone-aware"
            )

        return value

    @field_validator("python_requires")
    @classmethod
    def validate_python_requires(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if (
            not normalized
            or len(normalized) > 80
            or "\x00" in normalized
            or "\n" in normalized
            or "\r" in normalized
        ):
            raise ValueError(
                "invalid Python requirement"
            )

        return normalized

    @model_validator(mode="after")
    def validate_inventory(
        self,
    ) -> Self:
        paths = tuple(
            record.relative_path
            for record in self.files
        )

        if len(paths) != len(set(paths)):
            raise ValueError(
                "deployment file paths must be unique"
            )

        if self.file_count != len(self.files):
            raise ValueError(
                "file_count must match the inventory"
            )

        expected_size = sum(
            record.size_bytes
            for record in self.files
        )

        if (
            self.total_size_bytes
            != expected_size
        ):
            raise ValueError(
                "total_size_bytes must match "
                "the inventory"
            )

        return self


@dataclass(frozen=True, slots=True)
class ReleasePackageInput:
    """One explicit source file in a release package."""

    source_path: Path
    relative_path: str
    kind: DeploymentFileKind
    executable: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_path",
            Path(self.source_path),
        )
        object.__setattr__(
            self,
            "relative_path",
            self.relative_path.strip(),
        )


@dataclass(frozen=True, slots=True)
class DeploymentPackagePlan:
    """Atomic release package publication plan."""

    destination_root: Path
    identity: ReleaseIdentity
    files: tuple[ReleasePackageInput, ...]
    python_requires: str = ">=3.11"
    activate: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "destination_root",
            Path(self.destination_root),
        )
        object.__setattr__(
            self,
            "files",
            tuple(self.files),
        )


@dataclass(frozen=True, slots=True)
class DeploymentPackageResult:
    """Published release package and manifest paths."""

    release_dir: Path
    manifest_path: Path
    checksum_path: Path
    current_pointer_path: Path | None
    manifest: DeploymentManifest
