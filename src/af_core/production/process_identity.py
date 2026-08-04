"""Race-safe PID ownership and duplicate process prevention."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from .process_models import (
    ProcessIdentityRecord,
    ProcessOwnershipError,
    ProcessSpecification,
    ProcessSupervisorPolicyError,
)


class ProcessIdentityManager:
    """Acquire and release exclusive process PID ownership."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = (
            lambda: datetime.now(timezone.utc)
        ),
        pid_provider: Callable[[], int] = (
            os.getpid
        ),
        token_factory: Callable[[], str] = (
            lambda: secrets.token_hex(16)
        ),
        process_exists: Callable[[int], bool] | None = None,
    ) -> None:
        self._clock = clock
        self._pid_provider = pid_provider
        self._token_factory = token_factory
        self._process_exists = (
            process_exists
            or self._default_process_exists
        )

    def acquire(
        self,
        specification: ProcessSpecification,
    ) -> ProcessIdentityRecord:
        """Acquire exclusive ownership of a PID file."""

        pid_file = (
            specification.pid_file
            .expanduser()
            .absolute()
        )

        self._reject_symlink_components(
            pid_file
        )
        self._ensure_parent_directory(
            pid_file.parent
        )

        now = self._clock()

        if (
            now.tzinfo is None
            or now.utcoffset() is None
        ):
            raise ProcessSupervisorPolicyError(
                "process clock must return "
                "a timezone-aware datetime"
            )

        pid = self._pid_provider()

        if pid < 1:
            raise ProcessSupervisorPolicyError(
                "PID provider returned "
                "an invalid process ID"
            )

        owner_token = (
            self._token_factory()
            .strip()
            .lower()
        )

        record = ProcessIdentityRecord(
            process_name=specification.name,
            pid=pid,
            owner_token=owner_token,
            command_sha256=(
                self.command_sha256(
                    specification.command
                )
            ),
            acquired_at=now,
        )

        for attempt in range(2):
            try:
                self._create_pid_file(
                    pid_file,
                    record,
                )
                return record

            except FileExistsError:
                existing = self.load(
                    pid_file
                )

                if self._process_exists(
                    existing.pid
                ):
                    raise ProcessOwnershipError(
                        "process PID file is already "
                        "owned by a running process"
                    )

                self._remove_stale_record(
                    pid_file,
                    existing,
                )

                if attempt == 1:
                    raise ProcessOwnershipError(
                        "unable to replace stale "
                        "process PID ownership"
                    )

        raise ProcessOwnershipError(
            "unable to acquire process PID ownership"
        )

    def load(
        self,
        pid_file: str | Path,
    ) -> ProcessIdentityRecord:
        """Load and validate a PID ownership record."""

        path = (
            Path(pid_file)
            .expanduser()
            .absolute()
        )

        self._reject_symlink_components(
            path
        )

        if (
            path.is_symlink()
            or not path.is_file()
        ):
            raise ProcessOwnershipError(
                "process PID file is not "
                "a regular file"
            )

        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise ProcessOwnershipError(
                "process PID file cannot be read"
            ) from exc

        try:
            return (
                ProcessIdentityRecord
                .model_validate_json(payload)
            )
        except Exception as exc:
            raise ProcessOwnershipError(
                "process PID file is invalid"
            ) from exc

    @staticmethod
    def command_sha256(
        command: tuple[str, ...],
    ) -> str:
        """Return deterministic command identity."""

        digest = hashlib.sha256()

        for argument in command:
            encoded = argument.encode(
                "utf-8"
            )
            digest.update(
                len(encoded).to_bytes(
                    8,
                    byteorder="big",
                    signed=False,
                )
            )
            digest.update(encoded)

        return digest.hexdigest()

    @staticmethod
    def _create_pid_file(
        path: Path,
        record: ProcessIdentityRecord,
    ) -> None:
        payload = (
            json.dumps(
                record.model_dump(
                    mode="json"
                ),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")

        descriptor = os.open(
            path,
            (
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
            ),
            0o640,
        )

        try:
            with os.fdopen(
                descriptor,
                "wb",
                closefd=True,
            ) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(
                    stream.fileno()
                )
        except BaseException:
            try:
                path.unlink(
                    missing_ok=True
                )
            except OSError:
                pass
            raise

    def verify(
        self,
        specification: ProcessSpecification,
        record: ProcessIdentityRecord,
    ) -> ProcessIdentityRecord:
        """Verify that the caller still owns the PID file."""

        current = self.load(
            specification.pid_file
        )

        expected_command = (
            self.command_sha256(
                specification.command
            )
        )

        if (
            current.process_name
            != specification.name
            or current.pid != record.pid
            or current.owner_token
            != record.owner_token
            or current.command_sha256
            != expected_command
            or current != record
        ):
            raise ProcessOwnershipError(
                "process PID ownership does not match"
            )

        return current

    def release(
        self,
        specification: ProcessSpecification,
        record: ProcessIdentityRecord,
    ) -> None:
        """Release only PID ownership held by this record."""

        pid_file = (
            specification.pid_file
            .expanduser()
            .absolute()
        )

        self.verify(
            specification,
            record,
        )

        try:
            pid_file.unlink()
        except FileNotFoundError as exc:
            raise ProcessOwnershipError(
                "process PID ownership disappeared"
            ) from exc
        except OSError as exc:
            raise ProcessOwnershipError(
                "process PID ownership "
                "could not be released"
            ) from exc

        self._fsync_directory(
            pid_file.parent
        )

    def is_owned(
        self,
        specification: ProcessSpecification,
        record: ProcessIdentityRecord,
    ) -> bool:
        """Return whether the supplied record owns the PID file."""

        try:
            self.verify(
                specification,
                record,
            )
        except ProcessOwnershipError:
            return False

        return True

    def _remove_stale_record(
        self,
        path: Path,
        expected: ProcessIdentityRecord,
    ) -> None:
        current = self.load(path)

        if current != expected:
            raise ProcessOwnershipError(
                "process PID ownership changed "
                "during stale cleanup"
            )

        if self._process_exists(
            current.pid
        ):
            raise ProcessOwnershipError(
                "stale PID cleanup refused for "
                "a running process"
            )

        try:
            path.unlink()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise ProcessOwnershipError(
                "stale process PID ownership "
                "could not be removed"
            ) from exc

        self._fsync_directory(
            path.parent
        )

    def _ensure_parent_directory(
        self,
        directory: Path,
    ) -> None:
        self._reject_symlink_components(
            directory
        )

        existed = directory.exists()

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        if (
            directory.is_symlink()
            or not directory.is_dir()
        ):
            raise ProcessSupervisorPolicyError(
                "PID directory is unsafe"
            )

        if not existed:
            directory.chmod(0o750)

        self._fsync_directory(
            directory
        )

    @staticmethod
    def _reject_symlink_components(
        path: Path,
    ) -> None:
        absolute = (
            path.expanduser().absolute()
        )

        parts = absolute.parts

        if not parts:
            raise ProcessSupervisorPolicyError(
                "process path is invalid"
            )

        current = Path(parts[0])

        for part in parts[1:]:
            current = current / part

            if current.is_symlink():
                raise ProcessSupervisorPolicyError(
                    "process path contains "
                    "a symlink component"
                )

    @staticmethod
    def _default_process_exists(
        pid: int,
    ) -> bool:
        if pid < 1:
            return False

        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False

        return True

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
