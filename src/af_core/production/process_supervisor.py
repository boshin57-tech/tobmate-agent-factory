"""PID-owned service runtime supervision and readiness control."""

from __future__ import annotations

import asyncio
import time
from collections.abc import (
    Callable,
    Coroutine,
)
from datetime import datetime, timezone
from typing import Any

from .health import (
    HealthRegistry,
    HealthScope,
    HealthStatus,
)
from .process_identity import (
    ProcessIdentityManager,
)
from .process_models import (
    ProcessExitKind,
    ProcessIdentityRecord,
    ProcessReadinessError,
    ProcessRestartLimitError,
    ProcessRestartRecord,
    ProcessSpecification,
    ProcessSupervisorPolicyError,
    ProcessSupervisorSnapshot,
    ProcessSupervisorState,
    RestartMode,
)
from .service_runtime import (
    ServiceRuntime,
)
from .signals import (
    SignalShutdownController,
)


class ProcessSupervisor:
    """Own and supervise one AF-Core service runtime."""

    def __init__(
        self,
        specification: ProcessSpecification,
        runtime: ServiceRuntime,
        health_registry: HealthRegistry,
        *,
        identity_manager: (
            ProcessIdentityManager | None
        ) = None,
        signal_controller: (
            SignalShutdownController | None
        ) = None,
        clock: Callable[[], datetime] = (
            lambda: datetime.now(timezone.utc)
        ),
        monotonic: Callable[[], float] = (
            time.monotonic
        ),
        sleeper: Callable[
            [float],
            Coroutine[Any, Any, None],
        ] = asyncio.sleep,
        readiness_poll_seconds: float = 0.1,
    ) -> None:
        if readiness_poll_seconds <= 0.0:
            raise ProcessSupervisorPolicyError(
                "readiness poll interval "
                "must be positive"
            )

        self._specification = specification
        self._runtime = runtime
        self._health_registry = (
            health_registry
        )
        self._identity_manager = (
            identity_manager
            or ProcessIdentityManager(
                clock=clock
            )
        )
        self._signal_controller = (
            signal_controller
            or SignalShutdownController(
                runtime
            )
        )
        self._clock = clock
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._readiness_poll_seconds = (
            readiness_poll_seconds
        )

        self._state = (
            ProcessSupervisorState.CREATED
        )
        self._identity: (
            ProcessIdentityRecord | None
        ) = None
        self._readiness_passed = False
        self._shutdown_requested = False
        self._started_at: datetime | None = None
        self._last_exit_kind: (
            ProcessExitKind | None
        ) = None
        self._last_exit_code: int | None = None
        self._restart_history: list[
            ProcessRestartRecord
        ] = []
        self._restart_times: list[float] = []

    @property
    def state(
        self,
    ) -> ProcessSupervisorState:
        return self._state

    @property
    def specification(
        self,
    ) -> ProcessSpecification:
        return self._specification

    @property
    def identity(
        self,
    ) -> ProcessIdentityRecord | None:
        return self._identity

    @property
    def restart_history(
        self,
    ) -> tuple[
        ProcessRestartRecord,
        ...,
    ]:
        return tuple(
            self._restart_history
        )

    def snapshot(
        self,
    ) -> ProcessSupervisorSnapshot:
        now = self._now()

        pid_owned = False

        if self._identity is not None:
            pid_owned = (
                self._identity_manager
                .is_owned(
                    self._specification,
                    self._identity,
                )
            )

        return ProcessSupervisorSnapshot(
            process_name=(
                self._specification.name
            ),
            state=self._state,
            pid=(
                self._identity.pid
                if self._identity is not None
                else None
            ),
            pid_owned=pid_owned,
            readiness_passed=(
                self._readiness_passed
            ),
            shutdown_requested=(
                self._shutdown_requested
            ),
            restart_count=len(
                self._restart_history
            ),
            started_at=self._started_at,
            updated_at=now,
            last_exit_kind=(
                self._last_exit_kind
            ),
            last_exit_code=(
                self._last_exit_code
            ),
        )

    async def start(
        self,
    ) -> ProcessSupervisorSnapshot:
        """Acquire PID ownership and pass startup gates."""

        if (
            self._state
            is not ProcessSupervisorState.CREATED
        ):
            raise ProcessSupervisorPolicyError(
                "process supervisor can only "
                "start from created state"
            )

        self._state = (
            ProcessSupervisorState.ACQUIRING
        )

        try:
            self._identity = (
                self._identity_manager.acquire(
                    self._specification
                )
            )

            self._state = (
                ProcessSupervisorState.STARTING
            )

            self._signal_controller.install()

            await self._runtime.start()

            await self._await_health(
                HealthScope.STARTUP,
                timeout_seconds=(
                    self._specification
                    .readiness_timeout_seconds
                ),
            )

            await self._await_health(
                HealthScope.READINESS,
                timeout_seconds=(
                    self._specification
                    .readiness_timeout_seconds
                ),
            )

            self._readiness_passed = True
            self._started_at = self._now()
            self._state = (
                ProcessSupervisorState.RUNNING
            )

            return self.snapshot()

        except BaseException:
            if self._last_exit_kind is None:
                self._last_exit_kind = (
                    ProcessExitKind
                    .SUPERVISOR_FAILURE
                )

            self._last_exit_code = None
            self._state = (
                ProcessSupervisorState.FAILED
            )

            await self._cleanup_failed_start()
            raise

    def request_shutdown(
        self,
        reason: str = "requested",
    ) -> None:
        """Request graceful service shutdown."""

        normalized = reason.strip()

        if not normalized:
            raise ProcessSupervisorPolicyError(
                "shutdown reason must not be empty"
            )

        self._shutdown_requested = True

        self._runtime.request_shutdown(
            normalized
        )

    async def run_until_shutdown(
        self,
    ) -> ProcessSupervisorSnapshot:
        """Start, wait for shutdown and stop safely."""

        await self.start()

        reason = await (
            self._runtime.wait_for_shutdown()
        )

        self._shutdown_requested = True

        return await self.stop(
            reason=reason
        )

    async def stop(
        self,
        *,
        reason: str = "requested",
    ) -> ProcessSupervisorSnapshot:
        """Stop runtime and release PID ownership."""

        normalized = reason.strip()

        if not normalized:
            raise ProcessSupervisorPolicyError(
                "shutdown reason must not be empty"
            )

        if (
            self._state
            is ProcessSupervisorState.STOPPED
        ):
            return self.snapshot()

        if (
            self._state
            is ProcessSupervisorState.CREATED
        ):
            self._state = (
                ProcessSupervisorState.STOPPED
            )
            return self.snapshot()

        self._shutdown_requested = True
        self._state = (
            ProcessSupervisorState.STOPPING
        )

        stop_error: BaseException | None = None
        release_error: BaseException | None = None

        try:
            await self._runtime.stop(
                reason=normalized,
                timeout_seconds=(
                    self._specification
                    .shutdown_timeout_seconds
                ),
            )
        except BaseException as exc:
            stop_error = exc
            self._last_exit_kind = (
                ProcessExitKind
                .SHUTDOWN_TIMEOUT
            )

        try:
            if self._signal_controller.installed:
                self._signal_controller.uninstall()
        except BaseException as exc:
            if stop_error is None:
                stop_error = exc

        if self._identity is not None:
            try:
                self._identity_manager.release(
                    self._specification,
                    self._identity,
                )
            except BaseException as exc:
                release_error = exc
            else:
                self._identity = None

        self._readiness_passed = False

        if (
            stop_error is not None
            or release_error is not None
        ):
            self._state = (
                ProcessSupervisorState.FAILED
            )

            error = (
                stop_error
                if stop_error is not None
                else release_error
            )

            assert error is not None
            raise error

        self._last_exit_kind = (
            ProcessExitKind.CLEAN
        )
        self._last_exit_code = 0
        self._state = (
            ProcessSupervisorState.STOPPED
        )

        return self.snapshot()

    async def _await_health(
        self,
        scope: HealthScope,
        *,
        timeout_seconds: float,
    ) -> None:
        deadline = (
            self._monotonic()
            + timeout_seconds
        )

        while True:
            evaluation = await (
                self._health_registry.evaluate(
                    scope
                )
            )

            if (
                evaluation.status
                is HealthStatus.HEALTHY
            ):
                return

            remaining = (
                deadline
                - self._monotonic()
            )

            if remaining <= 0.0:
                self._last_exit_kind = (
                    ProcessExitKind
                    .READINESS_TIMEOUT
                )

                raise ProcessReadinessError(
                    f"{scope.value} health gate "
                    "did not become healthy "
                    "before timeout"
                )

            await self._sleeper(
                min(
                    self._readiness_poll_seconds,
                    remaining,
                )
            )

    async def _cleanup_failed_start(
        self,
    ) -> None:
        try:
            await self._runtime.stop(
                reason="supervisor-start-failed",
                timeout_seconds=(
                    self._specification
                    .shutdown_timeout_seconds
                ),
            )
        except BaseException:
            pass

        try:
            if self._signal_controller.installed:
                self._signal_controller.uninstall()
        except BaseException:
            pass

        if self._identity is not None:
            try:
                if (
                    self._identity_manager
                    .is_owned(
                        self._specification,
                        self._identity,
                    )
                ):
                    self._identity_manager.release(
                        self._specification,
                        self._identity,
                    )
            except BaseException:
                pass

            self._identity = None

        self._readiness_passed = False

    def _now(
        self,
    ) -> datetime:
        value = self._clock()

        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ProcessSupervisorPolicyError(
                "process clock must return "
                "a timezone-aware datetime"
            )

        return value

    def restart_required(
        self,
        exit_kind: ProcessExitKind,
        *,
        exit_code: int | None = None,
    ) -> bool:
        """Return whether policy requires another process start."""

        policy = (
            self._specification
            .restart_policy
        )

        if self._shutdown_requested:
            return False

        if policy.mode is RestartMode.NEVER:
            return False

        if policy.mode is RestartMode.ALWAYS:
            return True

        return (
            exit_kind
            is not ProcessExitKind.CLEAN
            or exit_code not in {
                None,
                0,
            }
        )

    def record_restart(
        self,
        exit_kind: ProcessExitKind,
        *,
        exit_code: int | None = None,
    ) -> ProcessRestartRecord:
        """Record one bounded restart decision."""

        if not self.restart_required(
            exit_kind,
            exit_code=exit_code,
        ):
            raise ProcessSupervisorPolicyError(
                "restart is not permitted "
                "for this process exit"
            )

        policy = (
            self._specification
            .restart_policy
        )

        current = self._monotonic()

        minimum = (
            current
            - policy.window_seconds
        )

        self._restart_times = [
            occurred
            for occurred in self._restart_times
            if occurred >= minimum
        ]

        if (
            len(self._restart_times)
            >= policy.maximum_restarts
        ):
            self._last_exit_kind = exit_kind
            self._last_exit_code = exit_code
            self._state = (
                ProcessSupervisorState.FAILED
            )

            raise ProcessRestartLimitError(
                "process restart limit exhausted"
            )

        self._restart_times.append(
            current
        )

        record = ProcessRestartRecord(
            sequence=(
                len(self._restart_history)
                + 1
            ),
            occurred_at=self._now(),
            exit_kind=exit_kind,
            exit_code=exit_code,
            delay_seconds=(
                policy.backoff_seconds
            ),
        )

        self._restart_history.append(
            record
        )
        self._last_exit_kind = exit_kind
        self._last_exit_code = exit_code

        return record

    async def wait_for_restart(
        self,
        exit_kind: ProcessExitKind,
        *,
        exit_code: int | None = None,
    ) -> ProcessRestartRecord:
        """Apply restart limits and wait for backoff."""

        record = self.record_restart(
            exit_kind,
            exit_code=exit_code,
        )

        if record.delay_seconds > 0.0:
            await self._sleeper(
                record.delay_seconds
            )

        return record

    def classify_exit(
        self,
        exit_code: int,
    ) -> ProcessExitKind:
        """Normalize an operating-system process exit code."""

        if exit_code == 0:
            return ProcessExitKind.CLEAN

        if exit_code < 0:
            return ProcessExitKind.SIGNAL

        return ProcessExitKind.FAILURE
