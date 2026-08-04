"""Controlled release execution, rollback and evidence publication."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from collections.abc import (
    Awaitable,
    Callable,
)
from datetime import datetime, timezone
from pathlib import Path

from .release_models import (
    ReleaseCommand,
    ReleaseCommandOutcome,
    ReleaseDrillReport,
    ReleaseDrillResult,
    ReleaseDrillStatus,
    ReleaseExecutionError,
    ReleaseRunbookPlan,
    ReleaseRunbookPolicyError,
    ReleaseStepResult,
    ReleaseStepStatus,
)


CommandRunner = Callable[
    [ReleaseCommand],
    Awaitable[ReleaseCommandOutcome],
]


class ReleaseRunbookService:
    """Execute an ordered release plan without shell evaluation."""

    def __init__(
        self,
        *,
        runner: CommandRunner | None = None,
        clock: Callable[[], datetime] = (
            lambda: datetime.now(timezone.utc)
        ),
        monotonic: Callable[[], float] = (
            time.monotonic
        ),
    ) -> None:
        self._runner = (
            runner
            or self._run_subprocess
        )
        self._clock = clock
        self._monotonic = monotonic

    async def execute(
        self,
        plan: ReleaseRunbookPlan,
    ) -> ReleaseDrillResult:
        """Execute main steps and controlled rollback when required."""

        started_at = self._now()
        results: list[
            ReleaseStepResult
        ] = []

        failure_step_id: str | None = None
        rollback_triggered = False
        rollback_succeeded = False

        for index, step in enumerate(
            plan.steps
        ):
            result = await self._execute_step(
                step
            )
            results.append(result)

            if (
                result.status
                in {
                    ReleaseStepStatus.FAILED,
                    ReleaseStepStatus.TIMED_OUT,
                }
            ):
                if failure_step_id is None:
                    failure_step_id = (
                        step.step_id
                    )

                if not step.required:
                    continue

                for remaining in (
                    plan.steps[index + 1 :]
                ):
                    results.append(
                        self._skipped_result(
                            remaining,
                            reason=(
                                "skipped after required "
                                "release-step failure"
                            ),
                        )
                    )

                if (
                    plan.rollback_on_failure
                    and plan.rollback_steps
                ):
                    rollback_triggered = True
                    rollback_succeeded = (
                        await self._execute_rollback(
                            plan.rollback_steps,
                            results,
                        )
                    )

                break

        completed_at = self._now()

        if failure_step_id is None:
            status = (
                ReleaseDrillStatus.PASSED
            )
        elif (
            rollback_triggered
            and rollback_succeeded
        ):
            status = (
                ReleaseDrillStatus
                .ROLLED_BACK
            )
        else:
            status = (
                ReleaseDrillStatus.FAILED
            )

        report = ReleaseDrillReport(
            identity=plan.identity,
            mode=plan.mode,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            total_steps=len(results),
            passed_steps=sum(
                result.status
                is ReleaseStepStatus.PASSED
                for result in results
            ),
            failed_steps=sum(
                result.status
                in {
                    ReleaseStepStatus.FAILED,
                    ReleaseStepStatus.TIMED_OUT,
                }
                for result in results
            ),
            skipped_steps=sum(
                result.status
                is ReleaseStepStatus.SKIPPED
                for result in results
            ),
            rollback_triggered=(
                rollback_triggered
            ),
            failure_step_id=(
                failure_step_id
            ),
            results=tuple(results),
        )

        report_path = self._publish_report(
            plan.report_path,
            report,
        )

        return ReleaseDrillResult(
            report=report,
            report_path=report_path,
        )

    async def _execute_rollback(
        self,
        steps: tuple[
            ReleaseCommand,
            ...,
        ],
        results: list[
            ReleaseStepResult
        ],
    ) -> bool:
        rollback_succeeded = True
        required_failure = False

        for step in steps:
            if required_failure:
                results.append(
                    self._skipped_result(
                        step,
                        reason=(
                            "skipped after required "
                            "rollback-step failure"
                        ),
                    )
                )
                continue

            result = await self._execute_step(
                step
            )
            results.append(result)

            if (
                result.status
                in {
                    ReleaseStepStatus.FAILED,
                    ReleaseStepStatus.TIMED_OUT,
                }
            ):
                rollback_succeeded = False

                if step.required:
                    required_failure = True

        return rollback_succeeded

    async def _execute_step(
        self,
        command: ReleaseCommand,
    ) -> ReleaseStepResult:
        started_at = self._now()
        started = self._monotonic()

        try:
            outcome = await self._runner(
                command
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            completed_at = self._now()

            return ReleaseStepResult(
                step_id=command.step_id,
                phase=command.phase,
                status=(
                    ReleaseStepStatus.FAILED
                ),
                exit_code=None,
                duration_seconds=max(
                    0.0,
                    self._monotonic()
                    - started,
                ),
                started_at=started_at,
                completed_at=completed_at,
                failure=(
                    "release command could "
                    "not be executed"
                ),
            )

        completed_at = self._now()

        if outcome.timed_out:
            status = (
                ReleaseStepStatus.TIMED_OUT
            )
            failure = (
                "release command exceeded "
                "its execution timeout"
            )
        elif (
            outcome.exit_code
            not in command.expected_exit_codes
        ):
            status = (
                ReleaseStepStatus.FAILED
            )
            failure = (
                "release command returned "
                "an unexpected exit code"
            )
        else:
            status = (
                ReleaseStepStatus.PASSED
            )
            failure = ""

        return ReleaseStepResult(
            step_id=command.step_id,
            phase=command.phase,
            status=status,
            exit_code=outcome.exit_code,
            duration_seconds=(
                outcome.duration_seconds
            ),
            started_at=started_at,
            completed_at=completed_at,
            failure=failure,
        )

    async def _run_subprocess(
        self,
        command: ReleaseCommand,
    ) -> ReleaseCommandOutcome:
        """Execute argv directly without shell interpretation."""

        working_directory = (
            command.working_directory
            .expanduser()
            .absolute()
        )

        self._reject_symlink_components(
            working_directory
        )

        if (
            working_directory.is_symlink()
            or not working_directory.is_dir()
        ):
            raise ReleaseExecutionError(
                "release working directory "
                "is not a safe directory"
            )

        started = self._monotonic()

        try:
            process = await (
                asyncio.create_subprocess_exec(
                    *command.argv,
                    cwd=str(working_directory),
                    stdout=(
                        asyncio.subprocess.DEVNULL
                    ),
                    stderr=(
                        asyncio.subprocess.DEVNULL
                    ),
                    start_new_session=True,
                )
            )
        except (
            OSError,
            ValueError,
        ) as exc:
            raise ReleaseExecutionError(
                "release command process "
                "could not be created"
            ) from exc

        try:
            exit_code = await asyncio.wait_for(
                process.wait(),
                timeout=command.timeout_seconds,
            )

        except TimeoutError:
            await self._terminate_process(
                process
            )

            return ReleaseCommandOutcome(
                exit_code=None,
                duration_seconds=max(
                    0.0,
                    self._monotonic()
                    - started,
                ),
                timed_out=True,
            )

        return ReleaseCommandOutcome(
            exit_code=exit_code,
            duration_seconds=max(
                0.0,
                self._monotonic()
                - started,
            ),
            timed_out=False,
        )

    @staticmethod
    async def _terminate_process(
        process: asyncio.subprocess.Process,
    ) -> None:
        """Terminate and then forcibly kill a timed-out process."""

        if process.returncode is not None:
            return

        try:
            process.terminate()
        except ProcessLookupError:
            return

        try:
            await asyncio.wait_for(
                process.wait(),
                timeout=5.0,
            )
            return

        except TimeoutError:
            pass

        try:
            process.kill()
        except ProcessLookupError:
            return

        await process.wait()

    def _skipped_result(
        self,
        command: ReleaseCommand,
        *,
        reason: str,
    ) -> ReleaseStepResult:
        """Create credential-free evidence for a skipped step."""

        timestamp = self._now()

        return ReleaseStepResult(
            step_id=command.step_id,
            phase=command.phase,
            status=ReleaseStepStatus.SKIPPED,
            exit_code=None,
            duration_seconds=0.0,
            started_at=timestamp,
            completed_at=timestamp,
            failure=reason,
        )

    def _publish_report(
        self,
        destination: Path,
        report: ReleaseDrillReport,
    ) -> Path:
        """Atomically publish credential-free release evidence."""

        path = (
            Path(destination)
            .expanduser()
            .absolute()
        )

        self._reject_symlink_components(
            path
        )

        parent = path.parent
        existed = parent.exists()

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
            raise ReleaseRunbookPolicyError(
                "release report directory "
                "is unsafe"
            )

        if not existed:
            parent.chmod(0o750)

        if path.is_symlink():
            raise ReleaseRunbookPolicyError(
                "release report path must not "
                "be a symlink"
            )

        if (
            path.exists()
            and not path.is_file()
        ):
            raise ReleaseRunbookPolicyError(
                "release report destination "
                "must be a regular file"
            )

        payload = (
            json.dumps(
                report.model_dump(
                    mode="json"
                ),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
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

            temporary_path.chmod(0o640)

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

    def _now(
        self,
    ) -> datetime:
        value = self._clock()

        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ReleaseRunbookPolicyError(
                "release clock must return "
                "a timezone-aware datetime"
            )

        return value

    @staticmethod
    def _reject_symlink_components(
        path: Path,
    ) -> None:
        absolute = (
            path.expanduser().absolute()
        )

        parts = absolute.parts

        if not parts:
            raise ReleaseRunbookPolicyError(
                "release path is invalid"
            )

        current = Path(parts[0])

        for part in parts[1:]:
            current = current / part

            if current.is_symlink():
                raise ReleaseRunbookPolicyError(
                    "release path contains "
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
