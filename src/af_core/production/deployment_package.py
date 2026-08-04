"""Reproducible and atomically published deployment packages."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from collections.abc import Callable

from .deployment_models import (
    DeploymentFileRecord,
    DeploymentIntegrityError,
    DeploymentManifest,
    DeploymentPackagePlan,
    DeploymentPackageResult,
    DeploymentPolicyError,
    ReleasePackageInput,
)


_CHUNK_SIZE = 1024 * 1024


class DeploymentPackageService:
    """Create immutable checksummed release directories."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = (
            lambda: datetime.now(timezone.utc)
        ),
    ) -> None:
        self._clock = clock

    def create(
        self,
        plan: DeploymentPackagePlan,
    ) -> DeploymentPackageResult:
        destination_root = (
            plan.destination_root
            .expanduser()
            .absolute()
        )

        self._reject_symlink_components(
            destination_root
        )

        if not plan.files:
            raise DeploymentPolicyError(
                "deployment package must contain files"
            )

        created_at = self._clock()

        if (
            created_at.tzinfo is None
            or created_at.utcoffset() is None
        ):
            raise DeploymentPolicyError(
                "deployment clock must return "
                "a timezone-aware datetime"
            )

        normalized_inputs = (
            self._validate_inputs(
                plan.files,
                destination_root=destination_root,
            )
        )

        releases_root = (
            destination_root / "releases"
        )
        temporary_root = (
            destination_root / "temporary"
        )

        self._make_directory(
            destination_root
        )
        self._make_directory(
            releases_root
        )
        self._make_directory(
            temporary_root
        )

        release_id = (
            plan.identity.release_id
        )
        final_dir = (
            releases_root / release_id
        )

        if (
            final_dir.exists()
            or final_dir.is_symlink()
        ):
            raise DeploymentPolicyError(
                f"release already exists: {release_id}"
            )

        temporary_dir = Path(
            tempfile.mkdtemp(
                prefix=f"{release_id}-",
                dir=temporary_root,
            )
        )
        temporary_dir.chmod(0o750)

        current_pointer: Path | None = None

        try:
            payload_root = (
                temporary_dir / "payload"
            )
            self._make_directory(
                payload_root
            )

            records: list[
                DeploymentFileRecord
            ] = []

            for package_input in normalized_inputs:
                destination = (
                    payload_root.joinpath(
                        *PurePosixPath(
                            package_input.relative_path
                        ).parts
                    )
                )

                self._copy_input(
                    package_input,
                    destination,
                )

                records.append(
                    self._inventory_file(
                        temporary_dir,
                        destination,
                        package_input,
                    )
                )

            records.sort(
                key=lambda record: (
                    record.relative_path
                )
            )

            manifest = DeploymentManifest(
                identity=plan.identity,
                created_at=created_at,
                python_requires=(
                    plan.python_requires
                ),
                file_count=len(records),
                total_size_bytes=sum(
                    record.size_bytes
                    for record in records
                ),
                files=tuple(records),
            )

            manifest_path = (
                temporary_dir
                / "release-manifest.json"
            )
            checksum_path = (
                temporary_dir
                / "release-manifest.sha256"
            )

            manifest_bytes = (
                self._manifest_bytes(
                    manifest
                )
            )

            self._write_file(
                manifest_path,
                manifest_bytes,
                executable=False,
            )

            manifest_digest = hashlib.sha256(
                manifest_bytes
            ).hexdigest()

            self._write_file(
                checksum_path,
                (
                    f"{manifest_digest}  "
                    "release-manifest.json\n"
                ).encode("ascii"),
                executable=False,
            )

            self._fsync_tree(
                temporary_dir
            )

            os.replace(
                temporary_dir,
                final_dir,
            )

            self._fsync_directory(
                releases_root
            )

            if plan.activate:
                current_pointer = (
                    self._activate_release(
                        destination_root,
                        release_id,
                    )
                )

        except BaseException:
            if temporary_dir.exists():
                shutil.rmtree(
                    temporary_dir,
                    ignore_errors=True,
                )
            raise

        return DeploymentPackageResult(
            release_dir=final_dir,
            manifest_path=(
                final_dir
                / "release-manifest.json"
            ),
            checksum_path=(
                final_dir
                / "release-manifest.sha256"
            ),
            current_pointer_path=(
                current_pointer
            ),
            manifest=manifest,
        )

    def _validate_inputs(
        self,
        files: tuple[
            ReleasePackageInput,
            ...,
        ],
        *,
        destination_root: Path,
    ) -> tuple[
        ReleasePackageInput,
        ...,
    ]:
        normalized: list[
            ReleasePackageInput
        ] = []
        relative_paths: set[str] = set()

        destination_resolved = (
            destination_root.resolve()
        )

        for package_input in files:
            source = (
                package_input.source_path
                .expanduser()
                .absolute()
            )

            self._reject_symlink_components(
                source
            )

            if (
                source.is_symlink()
                or not source.is_file()
            ):
                raise DeploymentPolicyError(
                    "deployment source must be "
                    f"a regular file: {source.name}"
                )

            try:
                source.resolve().relative_to(
                    destination_resolved
                )
            except ValueError:
                pass
            else:
                raise DeploymentPolicyError(
                    "deployment sources must not "
                    "be inside the destination root"
                )

            relative_path = (
                package_input.relative_path
                .strip()
            )

            try:
                record = DeploymentFileRecord(
                    relative_path=relative_path,
                    kind=package_input.kind,
                    sha256="0" * 64,
                    size_bytes=0,
                    executable=(
                        package_input.executable
                    ),
                )
            except Exception as exc:
                raise DeploymentPolicyError(
                    "invalid deployment "
                    f"relative path: {relative_path}"
                ) from exc

            if (
                record.relative_path
                in relative_paths
            ):
                raise DeploymentPolicyError(
                    "deployment relative paths "
                    "must be unique"
                )

            relative_paths.add(
                record.relative_path
            )

            normalized.append(
                ReleasePackageInput(
                    source_path=source,
                    relative_path=(
                        record.relative_path
                    ),
                    kind=package_input.kind,
                    executable=(
                        package_input.executable
                    ),
                )
            )

        normalized.sort(
            key=lambda item: item.relative_path
        )

        return tuple(normalized)

    def _copy_input(
        self,
        package_input: ReleasePackageInput,
        destination: Path,
    ) -> None:
        source = package_input.source_path

        self._reject_symlink_components(
            source
        )

        if (
            source.is_symlink()
            or not source.is_file()
        ):
            raise DeploymentPolicyError(
                "deployment source changed "
                "during packaging"
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

        destination.chmod(
            0o750
            if package_input.executable
            else 0o640
        )

    def _inventory_file(
        self,
        release_root: Path,
        path: Path,
        package_input: ReleasePackageInput,
    ) -> DeploymentFileRecord:
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

        return DeploymentFileRecord(
            relative_path=(
                path.relative_to(
                    release_root
                ).as_posix()
            ),
            kind=package_input.kind,
            sha256=digest.hexdigest(),
            size_bytes=size,
            executable=(
                package_input.executable
            ),
        )

    @staticmethod
    def _manifest_bytes(
        manifest: DeploymentManifest,
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
        *,
        executable: bool,
    ) -> None:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

        path.chmod(
            0o750
            if executable
            else 0o640
        )

    def load_manifest(
        self,
        release_dir: str | Path,
    ) -> DeploymentManifest:
        """Load and checksum-verify a release manifest."""

        directory = (
            Path(release_dir)
            .expanduser()
            .absolute()
        )

        self._require_directory(
            directory,
            role="release directory",
        )

        manifest_path = (
            directory
            / "release-manifest.json"
        )
        checksum_path = (
            directory
            / "release-manifest.sha256"
        )

        self._require_regular_file(
            manifest_path,
            role="release manifest",
        )
        self._require_regular_file(
            checksum_path,
            role="release manifest checksum",
        )

        manifest_bytes = (
            manifest_path.read_bytes()
        )

        try:
            checksum_text = (
                checksum_path.read_text(
                    encoding="ascii"
                )
            )
        except UnicodeError as exc:
            raise DeploymentIntegrityError(
                "release manifest checksum "
                "encoding is invalid"
            ) from exc

        fields = checksum_text.strip().split()

        if (
            len(fields) != 2
            or fields[1]
            != "release-manifest.json"
        ):
            raise DeploymentIntegrityError(
                "release manifest checksum "
                "file is invalid"
            )

        expected_digest = (
            fields[0].lower()
        )
        actual_digest = hashlib.sha256(
            manifest_bytes
        ).hexdigest()

        if expected_digest != actual_digest:
            raise DeploymentIntegrityError(
                "release manifest checksum mismatch"
            )

        try:
            manifest = (
                DeploymentManifest
                .model_validate_json(
                    manifest_bytes
                )
            )
        except Exception as exc:
            raise DeploymentIntegrityError(
                "release manifest is invalid"
            ) from exc

        if (
            manifest.identity.release_id
            != directory.name
        ):
            raise DeploymentIntegrityError(
                "release directory and manifest "
                "identity do not match"
            )

        return manifest

    def verify(
        self,
        release_dir: str | Path,
    ) -> DeploymentManifest:
        """Verify exact inventory, size, digest and mode."""

        directory = (
            Path(release_dir)
            .expanduser()
            .absolute()
        )

        manifest = self.load_manifest(
            directory
        )

        expected_top_level = {
            "payload",
            "release-manifest.json",
            "release-manifest.sha256",
        }

        actual_top_level = {
            path.name
            for path in directory.iterdir()
        }

        if actual_top_level != expected_top_level:
            raise DeploymentIntegrityError(
                "release top-level inventory mismatch"
            )

        payload_root = directory / "payload"

        self._require_directory(
            payload_root,
            role="release payload",
        )

        expected_paths = {
            record.relative_path
            for record in manifest.files
        }

        actual_paths: set[str] = set()

        for path in sorted(
            payload_root.rglob("*")
        ):
            if path.is_symlink():
                raise DeploymentIntegrityError(
                    "release payload contains a symlink"
                )

            if path.is_dir():
                continue

            if not path.is_file():
                raise DeploymentIntegrityError(
                    "release payload contains "
                    "a non-regular file"
                )

            actual_paths.add(
                path.relative_to(
                    directory
                ).as_posix()
            )

        if actual_paths != expected_paths:
            raise DeploymentIntegrityError(
                "release payload inventory mismatch"
            )

        for record in manifest.files:
            path = directory.joinpath(
                *PurePosixPath(
                    record.relative_path
                ).parts
            )

            self._require_regular_file(
                path,
                role="release payload file",
            )

            digest, size = self._hash_file(
                path
            )

            if size != record.size_bytes:
                raise DeploymentIntegrityError(
                    "release payload size mismatch"
                )

            if digest != record.sha256:
                raise DeploymentIntegrityError(
                    "release payload checksum mismatch"
                )

            executable = bool(
                path.stat().st_mode & 0o111
            )

            if executable != record.executable:
                raise DeploymentIntegrityError(
                    "release payload execution "
                    "mode mismatch"
                )

        return manifest

    def _activate_release(
        self,
        destination_root: Path,
        release_id: str,
    ) -> Path:
        """Atomically update the current release pointer."""

        release_dir = (
            destination_root
            / "releases"
            / release_id
        )

        self._require_directory(
            release_dir,
            role="release activation target",
        )

        current_path = (
            destination_root
            / "current-release"
        )

        self._reject_symlink_components(
            current_path
        )

        if current_path.is_symlink():
            raise DeploymentPolicyError(
                "current release pointer "
                "must not be a symlink"
            )

        temporary_root = (
            destination_root
            / "temporary"
        )

        self._make_directory(
            temporary_root
        )

        descriptor, temporary_name = (
            tempfile.mkstemp(
                prefix="current-release-",
                dir=temporary_root,
            )
        )

        temporary_path = Path(
            temporary_name
        )

        try:
            with os.fdopen(
                descriptor,
                "wb",
            ) as stream:
                stream.write(
                    (
                        release_id
                        + "\n"
                    ).encode("ascii")
                )
                stream.flush()
                os.fsync(
                    stream.fileno()
                )

            temporary_path.chmod(0o640)

            os.replace(
                temporary_path,
                current_path,
            )

            self._fsync_directory(
                destination_root
            )

        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass

            if temporary_path.exists():
                temporary_path.unlink(
                    missing_ok=True
                )

            raise

        return current_path

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

    def _require_directory(
        self,
        path: Path,
        *,
        role: str,
    ) -> None:
        self._reject_symlink_components(
            path
        )

        if (
            path.is_symlink()
            or not path.is_dir()
        ):
            raise DeploymentIntegrityError(
                f"{role} is not a safe directory"
            )

    def _require_regular_file(
        self,
        path: Path,
        *,
        role: str,
    ) -> None:
        self._reject_symlink_components(
            path
        )

        if (
            path.is_symlink()
            or not path.is_file()
        ):
            raise DeploymentIntegrityError(
                f"{role} is not a regular file"
            )

    def _make_directory(
        self,
        path: Path,
    ) -> None:
        self._reject_symlink_components(
            path
        )

        existed = path.exists()

        path.mkdir(
            parents=True,
            exist_ok=True,
        )

        if (
            path.is_symlink()
            or not path.is_dir()
        ):
            raise DeploymentPolicyError(
                "deployment directory is unsafe"
            )

        if not existed:
            path.chmod(0o750)

    def _activate_release(
        self,
        destination_root: Path,
        release_id: str,
    ) -> Path:
        """Atomically update the current release pointer."""

        release_dir = (
            destination_root
            / "releases"
            / release_id
        )

        self._require_directory(
            release_dir,
            role="release activation target",
        )

        current_path = (
            destination_root
            / "current-release"
        )

        self._reject_symlink_components(
            current_path
        )

        if current_path.is_symlink():
            raise DeploymentPolicyError(
                "current release pointer "
                "must not be a symlink"
            )

        temporary_root = (
            destination_root
            / "temporary"
        )

        self._make_directory(
            temporary_root
        )

        descriptor, temporary_name = (
            tempfile.mkstemp(
                prefix="current-release-",
                dir=temporary_root,
            )
        )

        temporary_path = Path(
            temporary_name
        )

        try:
            with os.fdopen(
                descriptor,
                "wb",
            ) as stream:
                stream.write(
                    (
                        release_id
                        + "\n"
                    ).encode("ascii")
                )
                stream.flush()
                os.fsync(
                    stream.fileno()
                )

            temporary_path.chmod(0o640)

            os.replace(
                temporary_path,
                current_path,
            )

            self._fsync_directory(
                destination_root
            )

        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass

            if temporary_path.exists():
                temporary_path.unlink(
                    missing_ok=True
                )

            raise

        return current_path

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

    def _require_directory(
        self,
        path: Path,
        *,
        role: str,
    ) -> None:
        self._reject_symlink_components(
            path
        )

        if (
            path.is_symlink()
            or not path.is_dir()
        ):
            raise DeploymentIntegrityError(
                f"{role} is not a safe directory"
            )

    def _require_regular_file(
        self,
        path: Path,
        *,
        role: str,
    ) -> None:
        self._reject_symlink_components(
            path
        )

        if (
            path.is_symlink()
            or not path.is_file()
        ):
            raise DeploymentIntegrityError(
                f"{role} is not a regular file"
            )

    def _make_directory(
        self,
        path: Path,
    ) -> None:
        self._reject_symlink_components(
            path
        )

        existed = path.exists()

        path.mkdir(
            parents=True,
            exist_ok=True,
        )

        if (
            path.is_symlink()
            or not path.is_dir()
        ):
            raise DeploymentPolicyError(
                "deployment directory is unsafe"
            )

        if not existed:
            path.chmod(0o750)

    @staticmethod
    def _reject_symlink_components(
        path: Path,
    ) -> None:
        absolute = (
            path.expanduser().absolute()
        )

        parts = absolute.parts

        if not parts:
            raise DeploymentPolicyError(
                "deployment path is invalid"
            )

        current = Path(parts[0])

        for part in parts[1:]:
            current = current / part

            if current.is_symlink():
                raise DeploymentPolicyError(
                    "deployment path contains "
                    "a symlink component"
                )

    def _fsync_tree(
        self,
        root: Path,
    ) -> None:
        self._reject_symlink_components(
            root
        )

        directories: list[Path] = [
            root
        ]

        for path in root.rglob("*"):
            if path.is_symlink():
                raise DeploymentPolicyError(
                    "deployment tree contains "
                    "a symlink"
                )

            if path.is_dir():
                directories.append(path)
                continue

            if not path.is_file():
                raise DeploymentPolicyError(
                    "deployment tree contains "
                    "a non-regular entry"
                )

            descriptor = os.open(
                path,
                os.O_RDONLY,
            )

            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

        directories.sort(
            key=lambda item: len(
                item.parts
            ),
            reverse=True,
        )

        for directory in directories:
            self._fsync_directory(
                directory
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
