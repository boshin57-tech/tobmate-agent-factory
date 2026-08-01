from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Sequence

from pydantic import BaseModel, Field

from af_core.runtime.command_runner import (
    CommandResult,
    RestrictedCommandRunner,
)


class ValidationStatus(StrEnum):
    NOT_RUN = "NOT_RUN"
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"


class ValidationCheck(BaseModel):
    name: str
    command: list[str]
    required: bool = True
    status: ValidationStatus = ValidationStatus.NOT_RUN
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    changed_files: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    passed: bool
    checks: list[ValidationCheck] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    evidence_summary: str


class ValidationPlan(BaseModel):
    checks: list[ValidationCheck]

    @classmethod
    def default_python(cls) -> "ValidationPlan":
        return cls(
            checks=[
                ValidationCheck(
                    name="git-diff-check",
                    command=["git", "diff", "--check"],
                ),
                ValidationCheck(
                    name="pytest",
                    command=["pytest"],
                ),
            ]
        )


class ValidationEngine:
    def __init__(
        self,
        workspace_path: str | Path,
        *,
        timeout_seconds: int = 120,
    ) -> None:
        self.workspace = Path(workspace_path).expanduser().resolve()
        self.runner = RestrictedCommandRunner(self.workspace)
        self.timeout_seconds = timeout_seconds

    async def validate(
        self,
        plan: ValidationPlan,
    ) -> ValidationResult:
        completed_checks: list[ValidationCheck] = []
        failures: list[str] = []

        for check in plan.checks:
            completed = await self._run_check(check)
            completed_checks.append(completed)

            if (
                completed.required
                and completed.status is not ValidationStatus.PASSED
            ):
                failures.append(
                    f"{completed.name}: "
                    f"{completed.stderr.strip() or completed.stdout.strip()}"
                )

        passed = not failures

        summary = (
            f"{len(completed_checks)} checks executed; "
            f"{sum(1 for item in completed_checks if item.status is ValidationStatus.PASSED)} passed; "
            f"{len(failures)} required checks failed."
        )

        return ValidationResult(
            passed=passed,
            checks=completed_checks,
            failures=failures,
            evidence_summary=summary,
        )

    async def _run_check(
        self,
        check: ValidationCheck,
    ) -> ValidationCheck:
        try:
            result: CommandResult = await self.runner.run(
                check.command,
                timeout=self.timeout_seconds,
            )
        except Exception as exc:
            return check.model_copy(
                update={
                    "status": ValidationStatus.ERROR,
                    "stderr": str(exc),
                }
            )

        if result.timed_out:
            status = ValidationStatus.ERROR
        elif result.returncode == 0:
            status = ValidationStatus.PASSED
        else:
            status = ValidationStatus.FAILED

        return check.model_copy(
            update={
                "status": status,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "timed_out": result.timed_out,
                "changed_files": result.changed_files,
            }
        )
