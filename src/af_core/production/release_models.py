"""Release runbook, command execution and drill evidence models."""

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

from .deployment_models import (
    ReleaseIdentity,
)


_STEP_ID = re.compile(
    r"^[a-z][a-z0-9-]{0,62}$"
)


class ReleaseRunbookError(RuntimeError):
    """Base release-runbook failure."""


class ReleaseRunbookPolicyError(
    ReleaseRunbookError
):
    """Raised when release policy is invalid."""


class ReleaseExecutionError(
    ReleaseRunbookError
):
    """Raised when a release command cannot execute."""


class ReleaseMode(StrEnum):
    """Supported release operation modes."""

    INSTALL = "install"
    UPGRADE = "upgrade"
    ROLLBACK = "rollback"
    RECOVERY = "recovery"


class ReleasePhase(StrEnum):
    """Ordered release lifecycle phases."""

    PREFLIGHT = "preflight"
    BACKUP = "backup"
    VERIFY_PACKAGE = "verify_package"
    STOP = "stop"
    INSTALL = "install"
    CONFIGURE = "configure"
    START = "start"
    HEALTH = "health"
    ROLLBACK = "rollback"
    RECOVERY = "recovery"
    EVIDENCE = "evidence"


class ReleaseStepStatus(StrEnum):
    """One release-command result."""

    PASSED = "passed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    SKIPPED = "skipped"


class ReleaseDrillStatus(StrEnum):
    """Overall release-drill result."""

    PASSED = "passed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class ReleaseCommand(BaseModel):
    """One explicit argv-based release command."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    step_id: str
    phase: ReleasePhase
    argv: tuple[str, ...] = Field(
        min_length=1
    )
    working_directory: Path
    timeout_seconds: float = Field(
        default=300.0,
        gt=0.0,
        le=86400.0,
    )
    expected_exit_codes: tuple[int, ...] = (
        0,
    )
    required: bool = True

    @field_validator("step_id")
    @classmethod
    def validate_step_id(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().lower()

        if not _STEP_ID.fullmatch(
            normalized
        ):
            raise ValueError(
                "invalid release step identifier"
            )

        return normalized

    @field_validator("argv")
    @classmethod
    def validate_argv(
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
                    "release argv contains "
                    "an invalid argument"
                )

            normalized.append(item)

        return tuple(normalized)

    @field_validator("working_directory")
    @classmethod
    def validate_working_directory(
        cls,
        value: Path,
    ) -> Path:
        normalized = (
            Path(value)
            .expanduser()
        )

        if not normalized.is_absolute():
            raise ValueError(
                "release working directory "
                "must be absolute"
            )

        return normalized

    @field_validator("expected_exit_codes")
    @classmethod
    def validate_expected_exit_codes(
        cls,
        value: tuple[int, ...],
    ) -> tuple[int, ...]:
        normalized = tuple(value)

        if (
            not normalized
            or len(normalized)
            != len(set(normalized))
            or any(
                code < -255 or code > 255
                for code in normalized
            )
        ):
            raise ValueError(
                "expected exit codes must be "
                "unique values from -255 to 255"
            )

        return tuple(
            sorted(normalized)
        )


class ReleaseCommandOutcome(BaseModel):
    """Credential-free process execution outcome."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    exit_code: int | None = None
    duration_seconds: float = Field(
        ge=0.0
    )
    timed_out: bool = False

    @model_validator(mode="after")
    def validate_outcome(
        self,
    ) -> Self:
        if (
            self.timed_out
            and self.exit_code is not None
        ):
            raise ValueError(
                "timed-out command must not "
                "publish an exit code"
            )

        if (
            not self.timed_out
            and self.exit_code is None
        ):
            raise ValueError(
                "completed command requires "
                "an exit code"
            )

        return self


class ReleaseStepResult(BaseModel):
    """Credential-free evidence for one release step."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    step_id: str
    phase: ReleasePhase
    status: ReleaseStepStatus
    exit_code: int | None = None
    duration_seconds: float = Field(
        ge=0.0
    )
    started_at: datetime
    completed_at: datetime
    failure: str = ""

    @field_validator("step_id")
    @classmethod
    def validate_result_step_id(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().lower()

        if not _STEP_ID.fullmatch(
            normalized
        ):
            raise ValueError(
                "invalid release step identifier"
            )

        return normalized

    @field_validator(
        "started_at",
        "completed_at",
    )
    @classmethod
    def validate_result_time(
        cls,
        value: datetime,
    ) -> datetime:
        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                "release evidence timestamps "
                "must be timezone-aware"
            )

        return value

    @field_validator("failure")
    @classmethod
    def validate_failure(
        cls,
        value: str,
    ) -> str:
        normalized = " ".join(
            value.split()
        )

        if (
            "\x00" in normalized
            or len(normalized) > 240
        ):
            raise ValueError(
                "invalid release failure summary"
            )

        return normalized

    @model_validator(mode="after")
    def validate_result(
        self,
    ) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError(
                "release step completion precedes start"
            )

        if (
            self.status
            is ReleaseStepStatus.PASSED
            and self.failure
        ):
            raise ValueError(
                "passed release step must not "
                "contain a failure summary"
            )

        if (
            self.status
            in {
                ReleaseStepStatus.FAILED,
                ReleaseStepStatus.TIMED_OUT,
            }
            and not self.failure
        ):
            raise ValueError(
                "failed release step requires "
                "a failure summary"
            )

        return self


_MAIN_PHASE_ORDER = {
    ReleasePhase.PREFLIGHT: 0,
    ReleasePhase.BACKUP: 1,
    ReleasePhase.VERIFY_PACKAGE: 2,
    ReleasePhase.STOP: 3,
    ReleasePhase.INSTALL: 4,
    ReleasePhase.CONFIGURE: 5,
    ReleasePhase.START: 6,
    ReleasePhase.HEALTH: 7,
    ReleasePhase.EVIDENCE: 8,
}

_ROLLBACK_PHASE_ORDER = {
    ReleasePhase.STOP: 0,
    ReleasePhase.ROLLBACK: 1,
    ReleasePhase.RECOVERY: 2,
    ReleasePhase.CONFIGURE: 3,
    ReleasePhase.START: 4,
    ReleasePhase.HEALTH: 5,
    ReleasePhase.EVIDENCE: 6,
}

_RESTORE_PHASE_ORDER = {
    ReleasePhase.PREFLIGHT: 0,
    ReleasePhase.STOP: 1,
    ReleasePhase.ROLLBACK: 2,
    ReleasePhase.RECOVERY: 2,
    ReleasePhase.CONFIGURE: 3,
    ReleasePhase.START: 4,
    ReleasePhase.HEALTH: 5,
    ReleasePhase.EVIDENCE: 6,
}

_REQUIRED_PHASES = {
    ReleaseMode.INSTALL: {
        ReleasePhase.PREFLIGHT,
        ReleasePhase.VERIFY_PACKAGE,
        ReleasePhase.INSTALL,
        ReleasePhase.CONFIGURE,
        ReleasePhase.START,
        ReleasePhase.HEALTH,
        ReleasePhase.EVIDENCE,
    },
    ReleaseMode.UPGRADE: {
        ReleasePhase.PREFLIGHT,
        ReleasePhase.BACKUP,
        ReleasePhase.VERIFY_PACKAGE,
        ReleasePhase.STOP,
        ReleasePhase.INSTALL,
        ReleasePhase.CONFIGURE,
        ReleasePhase.START,
        ReleasePhase.HEALTH,
        ReleasePhase.EVIDENCE,
    },
    ReleaseMode.ROLLBACK: {
        ReleasePhase.PREFLIGHT,
        ReleasePhase.STOP,
        ReleasePhase.ROLLBACK,
        ReleasePhase.START,
        ReleasePhase.HEALTH,
        ReleasePhase.EVIDENCE,
    },
    ReleaseMode.RECOVERY: {
        ReleasePhase.PREFLIGHT,
        ReleasePhase.STOP,
        ReleasePhase.RECOVERY,
        ReleasePhase.START,
        ReleasePhase.HEALTH,
        ReleasePhase.EVIDENCE,
    },
}


class ReleaseRunbookPlan(BaseModel):
    """Validated ordered release and rollback command plan."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    identity: ReleaseIdentity
    mode: ReleaseMode
    steps: tuple[
        ReleaseCommand,
        ...,
    ] = Field(min_length=1)
    rollback_steps: tuple[
        ReleaseCommand,
        ...,
    ] = ()
    report_path: Path
    rollback_on_failure: bool = True

    @field_validator("report_path")
    @classmethod
    def validate_report_path(
        cls,
        value: Path,
    ) -> Path:
        normalized = (
            Path(value)
            .expanduser()
        )

        if not normalized.is_absolute():
            raise ValueError(
                "release report path must be absolute"
            )

        if normalized.suffix != ".json":
            raise ValueError(
                "release report path must use "
                "the .json suffix"
            )

        return normalized

    @model_validator(mode="after")
    def validate_plan(
        self,
    ) -> Self:
        all_steps = (
            self.steps
            + self.rollback_steps
        )

        identifiers = tuple(
            step.step_id
            for step in all_steps
        )

        if len(identifiers) != len(
            set(identifiers)
        ):
            raise ValueError(
                "release step identifiers "
                "must be unique"
            )

        main_order = (
            _MAIN_PHASE_ORDER
            if self.mode
            in {
                ReleaseMode.INSTALL,
                ReleaseMode.UPGRADE,
            }
            else _RESTORE_PHASE_ORDER
        )

        self._validate_phase_order(
            self.steps,
            order=main_order,
            role="main",
        )

        phases = {
            step.phase
            for step in self.steps
        }

        missing = (
            _REQUIRED_PHASES[self.mode]
            - phases
        )

        if missing:
            rendered = ", ".join(
                sorted(
                    phase.value
                    for phase in missing
                )
            )

            raise ValueError(
                "release plan is missing "
                f"required phases: {rendered}"
            )

        if (
            self.steps[0].phase
            is not ReleasePhase.PREFLIGHT
        ):
            raise ValueError(
                "release plan must begin "
                "with preflight"
            )

        if (
            self.steps[-1].phase
            is not ReleasePhase.EVIDENCE
        ):
            raise ValueError(
                "release plan must end "
                "with evidence capture"
            )

        if self.rollback_steps:
            self._validate_phase_order(
                self.rollback_steps,
                order=_ROLLBACK_PHASE_ORDER,
                role="rollback",
            )

            rollback_phases = {
                step.phase
                for step in self.rollback_steps
            }

            if not (
                {
                    ReleasePhase.ROLLBACK,
                    ReleasePhase.RECOVERY,
                }
                & rollback_phases
            ):
                raise ValueError(
                    "rollback plan must contain "
                    "rollback or recovery"
                )

            if (
                self.rollback_steps[-1].phase
                is not ReleasePhase.EVIDENCE
            ):
                raise ValueError(
                    "rollback plan must end "
                    "with evidence capture"
                )

        if (
            self.rollback_on_failure
            and self.mode
            is ReleaseMode.UPGRADE
            and not self.rollback_steps
        ):
            raise ValueError(
                "upgrade rollback policy requires "
                "rollback steps"
            )

        return self

    @staticmethod
    def _validate_phase_order(
        steps: tuple[
            ReleaseCommand,
            ...,
        ],
        *,
        order: dict[
            ReleasePhase,
            int,
        ],
        role: str,
    ) -> None:
        indexes: list[int] = []

        for step in steps:
            if step.phase not in order:
                raise ValueError(
                    f"{role} release plan contains "
                    f"an invalid phase: "
                    f"{step.phase.value}"
                )

            indexes.append(
                order[step.phase]
            )

        if indexes != sorted(indexes):
            raise ValueError(
                f"{role} release phases "
                "must be ordered"
            )


class ReleaseDrillReport(BaseModel):
    """Credential-free immutable release-drill report."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    schema_version: int = Field(
        default=1,
        ge=1,
    )
    identity: ReleaseIdentity
    mode: ReleaseMode
    status: ReleaseDrillStatus
    started_at: datetime
    completed_at: datetime
    total_steps: int = Field(
        ge=1,
    )
    passed_steps: int = Field(
        ge=0,
    )
    failed_steps: int = Field(
        ge=0,
    )
    skipped_steps: int = Field(
        ge=0,
    )
    rollback_triggered: bool = False
    failure_step_id: str | None = None
    results: tuple[
        ReleaseStepResult,
        ...,
    ] = Field(min_length=1)

    @field_validator(
        "started_at",
        "completed_at",
    )
    @classmethod
    def validate_report_time(
        cls,
        value: datetime,
    ) -> datetime:
        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                "release report timestamps "
                "must be timezone-aware"
            )

        return value

    @field_validator("failure_step_id")
    @classmethod
    def validate_failure_step_id(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip().lower()

        if not _STEP_ID.fullmatch(
            normalized
        ):
            raise ValueError(
                "invalid failure step identifier"
            )

        return normalized

    @model_validator(mode="after")
    def validate_report(
        self,
    ) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError(
                "release completion precedes start"
            )

        if self.total_steps != len(
            self.results
        ):
            raise ValueError(
                "total_steps must match results"
            )

        identifiers = tuple(
            result.step_id
            for result in self.results
        )

        if len(identifiers) != len(
            set(identifiers)
        ):
            raise ValueError(
                "release report step identifiers "
                "must be unique"
            )

        passed = sum(
            result.status
            is ReleaseStepStatus.PASSED
            for result in self.results
        )
        failed = sum(
            result.status
            in {
                ReleaseStepStatus.FAILED,
                ReleaseStepStatus.TIMED_OUT,
            }
            for result in self.results
        )
        skipped = sum(
            result.status
            is ReleaseStepStatus.SKIPPED
            for result in self.results
        )

        if (
            self.passed_steps != passed
            or self.failed_steps != failed
            or self.skipped_steps != skipped
        ):
            raise ValueError(
                "release result counters "
                "must match results"
            )

        if (
            self.status
            is ReleaseDrillStatus.PASSED
        ):
            if (
                failed != 0
                or self.rollback_triggered
                or self.failure_step_id
                is not None
            ):
                raise ValueError(
                    "passed release drill must not "
                    "contain failure or rollback"
                )

        else:
            if (
                failed == 0
                or self.failure_step_id is None
                or self.failure_step_id
                not in identifiers
            ):
                raise ValueError(
                    "failed release drill requires "
                    "a recorded failing step"
                )

        if (
            self.status
            is ReleaseDrillStatus.ROLLED_BACK
            and not self.rollback_triggered
        ):
            raise ValueError(
                "rolled-back release drill must "
                "record rollback activation"
            )

        return self


@dataclass(frozen=True, slots=True)
class ReleaseDrillResult:
    """Published release-drill report result."""

    report: ReleaseDrillReport
    report_path: Path

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "report_path",
            Path(self.report_path),
        )
