"""Secure local content-addressed artifact storage."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

from .artifact_models import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ArtifactPolicyError,
    ArtifactReference,
    ArtifactStorageError,
)


_CHUNK_SIZE = 1024 * 1024


class LocalContentAddressedArtifactStore:
    """Store immutable artifacts under their SHA-256 digest."""

    def __init__(
        self,
        root: str | Path,
        *,
        maximum_size_bytes: int = (
            1024 * 1024 * 1024
        ),
    ) -> None:
        if maximum_size_bytes <= 0:
            raise ValueError(
                "maximum_size_bytes must be positive"
            )

        requested_root = Path(
            root
        ).expanduser()

        if requested_root.exists() \
            and requested_root.is_symlink():
            raise ArtifactPolicyError(
                "artifact store root must not be a symlink"
            )

        requested_root.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o750,
        )

        self.root = requested_root.resolve()
        self.maximum_size_bytes = (
            maximum_size_bytes
        )

        self._objects = (
            self.root / "objects" / "sha256"
        )
        self._metadata = (
            self.root / "metadata" / "sha256"
        )
        self._temporary = self.root / "temporary"

        for directory in (
            self._objects,
            self._metadata,
            self._temporary,
        ):
            directory.mkdir(
                parents=True,
                exist_ok=True,
                mode=0o750,
            )

            if directory.is_symlink():
                raise ArtifactPolicyError(
                    "artifact store directories "
                    "must not be symlinks"
                )

    def put_bytes(
        self,
        content: bytes,
        *,
        media_type: str = "application/octet-stream",
        original_name: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> ArtifactReference:
        if not isinstance(
            content,
            (bytes, bytearray, memoryview),
        ):
            raise TypeError(
                "artifact content must be bytes"
            )

        payload = bytes(content)

        if len(payload) > self.maximum_size_bytes:
            raise ArtifactPolicyError(
                "artifact exceeds maximum size"
            )

        digest = hashlib.sha256(
            payload
        ).hexdigest()

        destination = self._object_path(
            digest
        )

        if destination.exists():
            self._verify_object(
                digest,
                expected_size=len(payload),
            )
        else:
            self._atomic_write(
                destination,
                payload,
                mode=0o640,
            )

        return self._load_or_create_metadata(
            digest=digest,
            size_bytes=len(payload),
            media_type=media_type,
            original_name=original_name,
            metadata=metadata,
        )

    def put_file(
        self,
        source: str | Path,
        *,
        media_type: str = "application/octet-stream",
        original_name: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> ArtifactReference:
        path = Path(source).expanduser()

        if path.is_symlink():
            raise ArtifactPolicyError(
                "artifact source must not be a symlink"
            )

        if not path.is_file():
            raise ArtifactPolicyError(
                f"artifact source is not a file: {path}"
            )

        size = path.stat().st_size

        if size > self.maximum_size_bytes:
            raise ArtifactPolicyError(
                "artifact exceeds maximum size"
            )

        descriptor, temporary_name = (
            tempfile.mkstemp(
                prefix=".artifact.",
                suffix=".tmp",
                dir=self._temporary,
            )
        )

        temporary = Path(temporary_name)
        digest = hashlib.sha256()
        written = 0

        try:
            with path.open("rb") as source_handle:
                with os.fdopen(
                    descriptor,
                    "wb",
                ) as target_handle:
                    while True:
                        chunk = source_handle.read(
                            _CHUNK_SIZE
                        )

                        if not chunk:
                            break

                        written += len(chunk)

                        if (
                            written
                            > self.maximum_size_bytes
                        ):
                            raise ArtifactPolicyError(
                                "artifact exceeds "
                                "maximum size"
                            )

                        digest.update(chunk)
                        target_handle.write(chunk)

                    target_handle.flush()
                    os.fsync(
                        target_handle.fileno()
                    )

            hexadecimal = digest.hexdigest()
            destination = self._object_path(
                hexadecimal
            )

            if destination.exists():
                self._verify_object(
                    hexadecimal,
                    expected_size=written,
                )
            else:
                destination.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                    mode=0o750,
                )

                self._assert_internal(
                    destination
                )

                os.replace(
                    temporary,
                    destination,
                )
                os.chmod(
                    destination,
                    0o640,
                )
                self._fsync_directory(
                    destination.parent
                )

            return self._load_or_create_metadata(
                digest=hexadecimal,
                size_bytes=written,
                media_type=media_type,
                original_name=(
                    original_name or path.name
                ),
                metadata=metadata,
            )

        finally:
            temporary.unlink(
                missing_ok=True
            )

    def get(
        self,
        artifact_id: str,
    ) -> ArtifactReference:
        digest = self._digest_from_id(
            artifact_id
        )
        metadata_path = self._metadata_path(
            digest
        )

        if not metadata_path.is_file():
            raise ArtifactNotFoundError(
                f"artifact not found: {artifact_id}"
            )

        if metadata_path.is_symlink():
            raise ArtifactIntegrityError(
                "artifact metadata must not "
                "be a symlink"
            )

        try:
            reference = (
                ArtifactReference.model_validate_json(
                    metadata_path.read_text(
                        encoding="utf-8"
                    )
                )
            )
        except Exception as exc:
            raise ArtifactIntegrityError(
                "artifact metadata is invalid: "
                f"{artifact_id}"
            ) from exc

        if reference.sha256 != digest:
            raise ArtifactIntegrityError(
                "artifact metadata digest mismatch"
            )

        return reference

    def read_bytes(
        self,
        artifact_id: str,
    ) -> bytes:
        reference = self.verify(
            artifact_id
        )
        path = self._object_path(
            reference.sha256
        )

        try:
            return path.read_bytes()
        except OSError as exc:
            raise ArtifactStorageError(
                f"unable to read artifact: {artifact_id}"
            ) from exc

    def exists(
        self,
        artifact_id: str,
    ) -> bool:
        try:
            digest = self._digest_from_id(
                artifact_id
            )
        except ArtifactPolicyError:
            return False

        return (
            self._object_path(digest).is_file()
            and self._metadata_path(digest).is_file()
        )

    def verify(
        self,
        artifact_id: str,
    ) -> ArtifactReference:
        reference = self.get(
            artifact_id
        )

        self._verify_object(
            reference.sha256,
            expected_size=reference.size_bytes,
        )

        return reference

    def _load_or_create_metadata(
        self,
        *,
        digest: str,
        size_bytes: int,
        media_type: str,
        original_name: str | None,
        metadata: Mapping[str, str] | None,
    ) -> ArtifactReference:
        artifact_id = f"sha256:{digest}"
        metadata_path = self._metadata_path(
            digest
        )

        if metadata_path.exists():
            existing = self.get(
                artifact_id
            )

            if existing.size_bytes != size_bytes:
                raise ArtifactIntegrityError(
                    "existing artifact size mismatch"
                )

            return existing

        reference = ArtifactReference(
            artifact_id=artifact_id,
            sha256=digest,
            size_bytes=size_bytes,
            media_type=media_type,
            original_name=original_name,
            created_at=datetime.now(
                timezone.utc
            ).isoformat(),
            metadata={
                str(key): str(value)
                for key, value
                in dict(metadata or {}).items()
            },
        )

        payload = (
            json.dumps(
                reference.model_dump(
                    mode="json"
                ),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")

        self._atomic_write(
            metadata_path,
            payload,
            mode=0o640,
        )

        return reference

    def _verify_object(
        self,
        digest: str,
        *,
        expected_size: int,
    ) -> None:
        path = self._object_path(
            digest
        )

        if not path.is_file():
            raise ArtifactNotFoundError(
                f"artifact object not found: sha256:{digest}"
            )

        if path.is_symlink():
            raise ArtifactIntegrityError(
                "artifact object must not be a symlink"
            )

        calculated = hashlib.sha256()
        measured_size = 0

        try:
            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(
                        _CHUNK_SIZE
                    )

                    if not chunk:
                        break

                    calculated.update(chunk)
                    measured_size += len(chunk)
        except OSError as exc:
            raise ArtifactStorageError(
                "unable to verify artifact object"
            ) from exc

        if measured_size != expected_size:
            raise ArtifactIntegrityError(
                "artifact size mismatch"
            )

        if calculated.hexdigest() != digest:
            raise ArtifactIntegrityError(
                "artifact checksum mismatch"
            )

    def _object_path(
        self,
        digest: str,
    ) -> Path:
        normalized = self._validate_digest(
            digest
        )

        path = (
            self._objects
            / normalized[:2]
            / normalized
        )

        self._assert_internal(path)
        return path

    def _metadata_path(
        self,
        digest: str,
    ) -> Path:
        normalized = self._validate_digest(
            digest
        )

        path = (
            self._metadata
            / normalized[:2]
            / f"{normalized}.json"
        )

        self._assert_internal(path)
        return path

    def _digest_from_id(
        self,
        artifact_id: str,
    ) -> str:
        if not isinstance(
            artifact_id,
            str,
        ):
            raise ArtifactPolicyError(
                "artifact_id must be a string"
            )

        prefix = "sha256:"

        if not artifact_id.startswith(prefix):
            raise ArtifactPolicyError(
                "artifact_id must use sha256:<digest>"
            )

        return self._validate_digest(
            artifact_id[len(prefix):]
        )

    @staticmethod
    def _validate_digest(
        digest: str,
    ) -> str:
        normalized = digest.strip().lower()

        if (
            len(normalized) != 64
            or any(
                character not in "0123456789abcdef"
                for character in normalized
            )
        ):
            raise ArtifactPolicyError(
                "invalid SHA-256 artifact digest"
            )

        return normalized

    def _assert_internal(
        self,
        path: Path,
    ) -> None:
        parent = path.parent.resolve()

        try:
            parent.relative_to(
                self.root
            )
        except ValueError as exc:
            raise ArtifactPolicyError(
                "artifact path escaped storage root"
            ) from exc

        cursor = parent

        while cursor != self.root:
            if cursor.exists() \
                and cursor.is_symlink():
                raise ArtifactPolicyError(
                    "artifact storage path "
                    "must not contain symlinks"
                )

            cursor = cursor.parent

    def _atomic_write(
        self,
        destination: Path,
        content: bytes,
        *,
        mode: int,
    ) -> None:
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o750,
        )

        self._assert_internal(
            destination
        )

        if destination.exists() \
            and destination.is_symlink():
            raise ArtifactIntegrityError(
                "artifact destination must not "
                "be a symlink"
            )

        descriptor, temporary_name = (
            tempfile.mkstemp(
                prefix=f".{destination.name}.",
                suffix=".tmp",
                dir=destination.parent,
            )
        )

        temporary = Path(temporary_name)

        try:
            with os.fdopen(
                descriptor,
                "wb",
            ) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(
                    handle.fileno()
                )

            os.chmod(
                temporary,
                mode,
            )
            os.replace(
                temporary,
                destination,
            )
            self._fsync_directory(
                destination.parent
            )

        finally:
            temporary.unlink(
                missing_ok=True
            )

    @staticmethod
    def _fsync_directory(
        directory: Path,
    ) -> None:
        flags = os.O_RDONLY

        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY

        descriptor = os.open(
            directory,
            flags,
        )

        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
