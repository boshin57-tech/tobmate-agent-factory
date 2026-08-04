"""Process supervision, restart and systemd models."""

from __future__ import annotations

import re
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


_PROCESS_NAME = re.compile(
    r"^[a-z0-9][a-z0-9-]{0,62}$"
)

_ENVIRONMENT_KEY = re.compile(
    r"^[A-Z_][A-Z0-9_]{0,127}$"
)


class ProcessSupervisorError(RuntimeError):
    """Base process supervision failure."""


class ProcessSupervisorPolicyError(
    ProcessSupervisorError
):
    """Raised when process policy is invalid."""


class ProcessOwnershipError(
    ProcessSupervisorError
):
    """Raised for PID ownership conflicts."""


class ProcessReadinessError(
    ProcessSupervisorError
):
    """Raised when readiness cannot be achieved."""


class ProcessRestartLimitError(
    ProcessSupervisorError
):
    """Raised when restart limits are exhausted."""


class ProcessSupervisorState(StrEnum):
    """Process supervisor lifecycle."""

    CREATED = "created"
    ACQUIRING = "acquiring"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class RestartMode(StrEnum):
    """Supported process restart policies."""

    NEVER = "never"
    ON_FAILURE = "on_failure"
    ALWAYS = "always"


class RestartPolicy(BaseModel):
    """Bounded restart policy."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    mode: RestartMode = RestartMode.ON_FAILURE
    maximum_restarts: int = Field(
        default=3,
        ge=0,
        le=100,
    )
    window_seconds: float = Field(
        default=300.0,
        gt=0.0,
        le=86400.0,
    )
    backoff_seconds: float = Field(
        default=1.0,
        ge=0.0,
        le=3600.0,
    )

    @model_validator(mode="after")
    def validate_restart_policy(
        self,
    ) -> Self:
        if (
            self.mode is RestartMode.NEVER
            and self.maximum_restarts != 0
        ):
            raise ValueError(
                "restart mode never requires "
                "maximum_restarts=0"
            )

        return self


class ProcessSpecification(BaseModel):
    """Validated process and supervision contract."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    name: str
    command: tuple[str, ...] = Field(
        min_length=1
    )
    working_directory: Path
    pid_file: Path
    environment_file: Path | None = None
    environment_keys: tuple[str, ...] = ()
    readiness_timeout_seconds: float = Field(
        default=30.0,
        gt=0.0,
        le=3600.0,
    )
    shutdown_timeout_seconds: float = Field(
        default=30.0,
        gt=0.0,
        le=3600.0,
    )
    restart_policy: RestartPolicy = Field(
        default_factory=RestartPolicy
    )

    @field_validator("name")
    @classmethod
    def validate_name(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().lower()

        if not _PROCESS_NAME.fullmatch(
            normalized
        ):
            raise ValueError(
                "invalid process name"
            )

        return normalized

    @field_validator("command")
    @classmethod
    def validate_command(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        normalized: list[str] = []

        for argument in value:
            item = argument.strip()

            if (
                not item
                or "\x00" in item
                or "\n" in item
                or "\r" in item
            ):
                raise ValueError(
                    "process command contains "
                    "an invalid argument"
                )

            normalized.append(item)

        return tuple(normalized)

    @field_validator(
        "working_directory",
        "pid_file",
        "environment_file",
    )
    @classmethod
    def validate_absolute_path(
        cls,
        value: Path | None,
    ) -> Path | None:
        if value is None:
            return None

        normalized = Path(value).expanduser()

        if not normalized.is_absolute():
            raise ValueError(
                "process paths must be absolute"
            )

        return normalized

    @field_validator("environment_keys")
    @classmethod
    def validate_environment_keys(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        normalized: list[str] = []

        for key in value:
            item = key.strip().upper()

            if not _ENVIRONMENT_KEY.fullmatch(
                item
            ):
                raise ValueError(
                    "invalid environment key"
                )

            normalized.append(item)

        if len(normalized) != len(
            set(normalized)
        ):
            raise ValueError(
                "environment keys must be unique"
            )

        return tuple(sorted(normalized))

    @model_validator(mode="after")
    def validate_process_paths(
        self,
    ) -> Self:
        if self.pid_file == self.working_directory:
            raise ValueError(
                "PID file must not equal "
                "the working directory"
            )

        if (
            self.environment_file is not None
            and self.environment_file
            == self.pid_file
        ):
            raise ValueError(
                "environment file and PID file "
                "must be different"
            )

        return self


_OWNER_TOKEN = re.compile(
    r"^[0-9a-f]{32}$"
)

_SHA256 = re.compile(
    r"^[0-9a-f]{64}$"
)

_SYSTEM_IDENTITY = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_-]{0,62}$"
)

_SYSTEMD_TARGET = re.compile(
    r"^[A-Za-z0-9_.@-]{1,128}$"
)


class ProcessExitKind(StrEnum):
    """Normalized supervised process exit cause."""

    CLEAN = "clean"
    FAILURE = "failure"
    SIGNAL = "signal"
    READINESS_TIMEOUT = "readiness_timeout"
    SHUTDOWN_TIMEOUT = "shutdown_timeout"
    SUPERVISOR_FAILURE = "supervisor_failure"


class ProcessIdentityRecord(BaseModel):
    """Durable PID-file ownership record."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    schema_version: int = Field(
        default=1,
        ge=1,
    )
    process_name: str
    pid: int = Field(
        ge=1,
    )
    owner_token: str
    command_sha256: str
    acquired_at: datetime

    @field_validator("process_name")
    @classmethod
    def validate_process_name(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().lower()

        if not _PROCESS_NAME.fullmatch(
            normalized
        ):
            raise ValueError(
                "invalid process name"
            )

        return normalized

    @field_validator("owner_token")
    @classmethod
    def validate_owner_token(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().lower()

        if not _OWNER_TOKEN.fullmatch(
            normalized
        ):
            raise ValueError(
                "owner token must contain "
                "32 hexadecimal characters"
            )

        return normalized

    @field_validator("command_sha256")
    @classmethod
    def validate_command_sha256(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().lower()

        if not _SHA256.fullmatch(
            normalized
        ):
            raise ValueError(
                "command_sha256 must contain "
                "64 hexadecimal characters"
            )

        return normalized

    @field_validator("acquired_at")
    @classmethod
    def validate_acquired_at(
        cls,
        value: datetime,
    ) -> datetime:
        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                "acquired_at must be "
                "timezone-aware"
            )

        return value


class ProcessRestartRecord(BaseModel):
    """One immutable restart decision."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    sequence: int = Field(
        ge=1,
    )
    occurred_at: datetime
    exit_kind: ProcessExitKind
    exit_code: int | None = None
    delay_seconds: float = Field(
        ge=0.0,
        le=3600.0,
    )

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at(
        cls,
        value: datetime,
    ) -> datetime:
        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                "occurred_at must be "
                "timezone-aware"
            )

        return value


class ProcessSupervisorSnapshot(BaseModel):
    """Credential-free supervisor state snapshot."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    process_name: str
    state: ProcessSupervisorState
    pid: int | None = Field(
        default=None,
        ge=1,
    )
    pid_owned: bool = False
    readiness_passed: bool = False
    shutdown_requested: bool = False
    restart_count: int = Field(
        default=0,
        ge=0,
    )
    started_at: datetime | None = None
    updated_at: datetime
    last_exit_kind: ProcessExitKind | None = None
    last_exit_code: int | None = None

    @field_validator("process_name")
    @classmethod
    def validate_snapshot_name(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().lower()

        if not _PROCESS_NAME.fullmatch(
            normalized
        ):
            raise ValueError(
                "invalid process name"
            )

        return normalized

    @field_validator(
        "started_at",
        "updated_at",
    )
    @classmethod
    def validate_snapshot_time(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None

        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                "supervisor timestamps must be "
                "timezone-aware"
            )

        return value

    @model_validator(mode="after")
    def validate_snapshot_state(
        self,
    ) -> Self:
        if (
            self.state
            is ProcessSupervisorState.RUNNING
        ):
            if (
                self.pid is None
                or not self.pid_owned
                or not self.readiness_passed
            ):
                raise ValueError(
                    "running supervisor requires "
                    "owned PID and readiness"
                )

        if (
            self.state
            in {
                ProcessSupervisorState.CREATED,
                ProcessSupervisorState.STOPPED,
            }
            and self.pid is not None
        ):
            raise ValueError(
                "inactive supervisor must not "
                "publish a PID"
            )

        return self


class SystemdUnitSpecification(BaseModel):
    """Validated systemd service rendering policy."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    description: str = Field(
        min_length=1,
        max_length=160,
    )
    user: str
    group: str
    after: tuple[str, ...] = (
        "network-online.target",
    )
    wanted_by: tuple[str, ...] = (
        "multi-user.target",
    )
    environment_file: Path | None = None
    private_tmp: bool = True
    protect_system: str = "strict"
    protect_home: bool = True
    no_new_privileges: bool = True

    @field_validator("description")
    @classmethod
    def validate_description(
        cls,
        value: str,
    ) -> str:
        normalized = " ".join(
            value.split()
        )

        if (
            not normalized
            or "\x00" in normalized
        ):
            raise ValueError(
                "invalid systemd description"
            )

        return normalized

    @field_validator(
        "user",
        "group",
    )
    @classmethod
    def validate_system_identity(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not _SYSTEM_IDENTITY.fullmatch(
            normalized
        ):
            raise ValueError(
                "invalid system identity"
            )

        return normalized

    @field_validator(
        "after",
        "wanted_by",
    )
    @classmethod
    def validate_targets(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        normalized = tuple(
            item.strip()
            for item in value
        )

        if (
            not normalized
            or len(normalized)
            != len(set(normalized))
            or any(
                not _SYSTEMD_TARGET.fullmatch(
                    item
                )
                for item in normalized
            )
        ):
            raise ValueError(
                "invalid or duplicate "
                "systemd target"
            )

        return tuple(
            sorted(normalized)
        )

    @field_validator("environment_file")
    @classmethod
    def validate_environment_file(
        cls,
        value: Path | None,
    ) -> Path | None:
        if value is None:
            return None

        normalized = Path(
            value
        ).expanduser()

        if not normalized.is_absolute():
            raise ValueError(
                "systemd environment file "
                "must be absolute"
            )

        return normalized

    @field_validator("protect_system")
    @classmethod
    def validate_protect_system(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().lower()

        if normalized not in {
            "yes",
            "full",
            "strict",
        }:
            raise ValueError(
                "protect_system must be "
                "yes, full or strict"
            )

        return normalized
