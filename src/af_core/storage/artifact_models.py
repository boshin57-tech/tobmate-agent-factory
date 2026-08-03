"""Artifact storage contracts and immutable references."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ARTIFACT_ID = re.compile(
    r"^sha256:([0-9a-f]{64})$"
)


class ArtifactStorageError(RuntimeError):
    """Base error for artifact storage failures."""


class ArtifactNotFoundError(ArtifactStorageError):
    """Raised when an artifact does not exist."""


class ArtifactIntegrityError(ArtifactStorageError):
    """Raised when stored artifact content is corrupted."""


class ArtifactPolicyError(ArtifactStorageError):
    """Raised when an artifact violates storage policy."""


class ArtifactReference(BaseModel):
    """Immutable content-addressed artifact reference."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    artifact_id: str
    sha256: str
    size_bytes: int = Field(ge=0)
    media_type: str = "application/octet-stream"
    original_name: str | None = None
    created_at: str
    metadata: Mapping[str, str] = Field(
        default_factory=dict
    )

    @field_validator("sha256")
    @classmethod
    def validate_sha256(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().lower()

        if not _SHA256.fullmatch(normalized):
            raise ValueError(
                "sha256 must contain exactly "
                "64 lowercase hexadecimal characters"
            )

        return normalized

    @field_validator("artifact_id")
    @classmethod
    def validate_artifact_id(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().lower()

        if not _ARTIFACT_ID.fullmatch(normalized):
            raise ValueError(
                "artifact_id must use sha256:<digest>"
            )

        return normalized

    @field_validator("media_type")
    @classmethod
    def validate_media_type(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().lower()

        if (
            not normalized
            or "/" not in normalized
            or any(
                character in normalized
                for character in "\r\n\0"
            )
        ):
            raise ValueError(
                "media_type must be a valid MIME type"
            )

        return normalized

    @field_validator("original_name")
    @classmethod
    def validate_original_name(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()

        if not normalized:
            return None

        if (
            "/" in normalized
            or "\\" in normalized
            or normalized in {".", ".."}
            or "\0" in normalized
        ):
            raise ValueError(
                "original_name must be a plain filename"
            )

        return normalized

    @model_validator(mode="after")
    def validate_identifier_digest(
        self,
    ) -> "ArtifactReference":
        match = _ARTIFACT_ID.fullmatch(
            self.artifact_id
        )

        if (
            match is None
            or match.group(1) != self.sha256
        ):
            raise ValueError(
                "artifact_id and sha256 must match"
            )

        return self


@runtime_checkable
class ArtifactStore(Protocol):
    """Persistent content-addressed artifact store."""

    def put_bytes(
        self,
        content: bytes,
        *,
        media_type: str = "application/octet-stream",
        original_name: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> ArtifactReference:
        ...

    def put_file(
        self,
        source: str,
        *,
        media_type: str = "application/octet-stream",
        original_name: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> ArtifactReference:
        ...

    def get(
        self,
        artifact_id: str,
    ) -> ArtifactReference:
        ...

    def read_bytes(
        self,
        artifact_id: str,
    ) -> bytes:
        ...

    def exists(
        self,
        artifact_id: str,
    ) -> bool:
        ...

    def verify(
        self,
        artifact_id: str,
    ) -> ArtifactReference:
        ...
