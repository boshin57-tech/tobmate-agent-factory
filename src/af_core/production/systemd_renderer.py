"""Deterministic and hardened systemd unit rendering."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .process_models import (
    ProcessSpecification,
    ProcessSupervisorPolicyError,
    RestartMode,
    SystemdUnitSpecification,
)


class SystemdUnitRenderer:
    """Render AF-Core process policy as a systemd service unit."""

    def render(
        self,
        process: ProcessSpecification,
        unit: SystemdUnitSpecification,
    ) -> str:
        """Return one deterministic systemd service definition."""

        environment_file = (
            unit.environment_file
            or process.environment_file
        )

        if (
            unit.environment_file is not None
            and process.environment_file is not None
            and unit.environment_file
            != process.environment_file
        ):
            raise ProcessSupervisorPolicyError(
                "process and systemd environment "
                "files must match"
            )

        command = " ".join(
            self._quote_argument(argument)
            for argument in process.command
        )

        restart_value = {
            RestartMode.NEVER: "no",
            RestartMode.ON_FAILURE: "on-failure",
            RestartMode.ALWAYS: "always",
        }[
            process.restart_policy.mode
        ]

        writable_paths = sorted(
            {
                process.working_directory,
                process.pid_file.parent,
            },
            key=lambda path: str(path),
        )

        lines = [
            "[Unit]",
            f"Description={self._escape_value(unit.description)}",
            (
                "After="
                + " ".join(unit.after)
            ),
            (
                "StartLimitIntervalSec="
                + self._format_seconds(
                    process.restart_policy
                    .window_seconds
                )
            ),
            (
                "StartLimitBurst="
                + str(
                    process.restart_policy
                    .maximum_restarts
                )
            ),
            "",
            "[Service]",
            "Type=simple",
            f"User={unit.user}",
            f"Group={unit.group}",
            (
                "WorkingDirectory="
                + self._escape_path(
                    process.working_directory
                )
            ),
            f"ExecStart={command}",
            "KillSignal=SIGTERM",
            "KillMode=mixed",
            (
                "TimeoutStopSec="
                + self._format_seconds(
                    process.shutdown_timeout_seconds
                )
            ),
            f"Restart={restart_value}",
            (
                "RestartSec="
                + self._format_seconds(
                    process.restart_policy
                    .backoff_seconds
                )
            ),
        ]

        if environment_file is not None:
            lines.append(
                "EnvironmentFile="
                + self._escape_path(
                    environment_file
                )
            )

        if process.environment_keys:
            lines.append(
                "PassEnvironment="
                + " ".join(
                    process.environment_keys
                )
            )

        lines.extend(
            [
                (
                    "NoNewPrivileges="
                    + self._boolean(
                        unit.no_new_privileges
                    )
                ),
                (
                    "PrivateTmp="
                    + self._boolean(
                        unit.private_tmp
                    )
                ),
                (
                    "ProtectSystem="
                    + unit.protect_system
                ),
                (
                    "ProtectHome="
                    + self._boolean(
                        unit.protect_home
                    )
                ),
                "ProtectKernelTunables=yes",
                "ProtectKernelModules=yes",
                "ProtectKernelLogs=yes",
                "ProtectControlGroups=yes",
                "RestrictSUIDSGID=yes",
                "LockPersonality=yes",
                "RestrictRealtime=yes",
                "PrivateDevices=yes",
                "CapabilityBoundingSet=",
                "AmbientCapabilities=",
            ]
        )

        for path in writable_paths:
            lines.append(
                "ReadWritePaths="
                + self._escape_path(path)
            )

        lines.extend(
            [
                "",
                "[Install]",
                (
                    "WantedBy="
                    + " ".join(
                        unit.wanted_by
                    )
                ),
                "",
            ]
        )

        return "\n".join(lines)

    @staticmethod
    def _quote_argument(
        value: str,
    ) -> str:
        if (
            not value
            or "\x00" in value
            or "\n" in value
            or "\r" in value
        ):
            raise ProcessSupervisorPolicyError(
                "systemd command argument is invalid"
            )

        escaped = (
            value
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("$", "$$")
            .replace("%", "%%")
            .replace("\t", "\\t")
        )

        return f'"{escaped}"'

    @classmethod
    def _escape_path(
        cls,
        path: Path,
    ) -> str:
        normalized = (
            Path(path)
            .expanduser()
        )

        if not normalized.is_absolute():
            raise ProcessSupervisorPolicyError(
                "systemd paths must be absolute"
            )

        return cls._quote_argument(
            str(normalized)
        )

    @staticmethod
    def _escape_value(
        value: str,
    ) -> str:
        if (
            not value
            or "\x00" in value
            or "\n" in value
            or "\r" in value
        ):
            raise ProcessSupervisorPolicyError(
                "systemd value is invalid"
            )

        return (
            value
            .replace("\\", "\\\\")
            .replace("%", "%%")
        )

    @staticmethod
    def _boolean(
        value: bool,
    ) -> str:
        return "yes" if value else "no"

    @staticmethod
    def _format_seconds(
        value: float,
    ) -> str:
        if value < 0.0:
            raise ProcessSupervisorPolicyError(
                "systemd duration must not be negative"
            )

        if value.is_integer():
            return f"{int(value)}s"

        rendered = (
            f"{value:.6f}"
            .rstrip("0")
            .rstrip(".")
        )

        return f"{rendered}s"

    def write(
        self,
        process: ProcessSpecification,
        unit: SystemdUnitSpecification,
        destination: str | Path,
    ) -> Path:
        """Atomically publish one systemd service unit."""

        path = (
            Path(destination)
            .expanduser()
        )

        if not path.is_absolute():
            raise ProcessSupervisorPolicyError(
                "systemd destination "
                "must be absolute"
            )

        if path.suffix != ".service":
            raise ProcessSupervisorPolicyError(
                "systemd destination must use "
                "the .service suffix"
            )

        self._reject_symlink_components(
            path
        )

        parent = path.parent
        parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._reject_symlink_components(
            parent
        )

        if (
            parent.is_symlink()
            or not parent.is_dir()
        ):
            raise ProcessSupervisorPolicyError(
                "systemd destination directory "
                "is unsafe"
            )

        if path.exists() and not path.is_file():
            raise ProcessSupervisorPolicyError(
                "systemd destination must be "
                "a regular file"
            )

        if path.is_symlink():
            raise ProcessSupervisorPolicyError(
                "systemd destination must not "
                "be a symlink"
            )

        payload = self.render(
            process,
            unit,
        ).encode("utf-8")

        descriptor, temporary_name = (
            tempfile.mkstemp(
                prefix=f".{path.name}.",
                dir=parent,
            )
        )

        temporary_path = Path(
            temporary_name
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

            temporary_path.chmod(0o644)

            os.replace(
                temporary_path,
                path,
            )

            self._fsync_directory(
                parent
            )

        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass

            temporary_path.unlink(
                missing_ok=True
            )
            raise

        return path

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
                "systemd path is invalid"
            )

        current = Path(parts[0])

        for part in parts[1:]:
            current = current / part

            if current.is_symlink():
                raise ProcessSupervisorPolicyError(
                    "systemd path contains "
                    "a symlink component"
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
