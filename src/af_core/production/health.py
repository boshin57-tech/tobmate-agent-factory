"""Service startup, liveness and readiness health registry."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from .service_runtime import (
    ServiceRuntime,
    ServiceState,
)


class HealthRegistryError(RuntimeError):
    """Raised when health registry configuration is invalid."""


class HealthStatus(StrEnum):
    """Normalized service health states."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthScope(StrEnum):
    """Standard service probe scopes."""

    STARTUP = "startup"
    LIVENESS = "liveness"
    READINESS = "readiness"


@dataclass(frozen=True, slots=True)
class HealthOutcome:
    """Normalized health-check outcome."""

    status: HealthStatus
    detail: str = ""


HealthCallback = Callable[
    [],
    bool | HealthStatus | HealthOutcome | object,
]


@dataclass(frozen=True, slots=True)
class HealthCheck:
    """One named health dependency check."""

    name: str
    callback: HealthCallback
    scopes: frozenset[HealthScope] = field(
        default_factory=lambda: frozenset(
            {
                HealthScope.STARTUP,
                HealthScope.LIVENESS,
                HealthScope.READINESS,
            }
        )
    )
    required: bool = True
    timeout_seconds: float | None = 5.0

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()

        if not normalized_name:
            raise ValueError(
                "health check name must not be empty"
            )

        if normalized_name != self.name:
            object.__setattr__(
                self,
                "name",
                normalized_name,
            )

        if not callable(self.callback):
            raise TypeError(
                "health callback must be callable"
            )

        normalized_scopes = frozenset(
            HealthScope(scope)
            for scope in self.scopes
        )

        if not normalized_scopes:
            raise ValueError(
                "health check must have at least one scope"
            )

        object.__setattr__(
            self,
            "scopes",
            normalized_scopes,
        )

        if (
            self.timeout_seconds is not None
            and self.timeout_seconds <= 0
        ):
            raise ValueError(
                "health timeout must be positive"
            )


@dataclass(frozen=True, slots=True)
class HealthProbeResult:
    """Credential-free result for one health check."""

    name: str
    status: HealthStatus
    required: bool
    scopes: tuple[HealthScope, ...]
    detail: str
    checked_at: float
    duration_ms: float


@dataclass(frozen=True, slots=True)
class HealthEvaluation:
    """Evaluation for one standard probe scope."""

    scope: HealthScope
    status: HealthStatus
    checked_at: float
    checks: tuple[HealthProbeResult, ...]


@dataclass(frozen=True, slots=True)
class HealthSnapshot:
    """Combined startup, liveness and readiness state."""

    overall: HealthStatus
    startup: HealthStatus
    liveness: HealthStatus
    readiness: HealthStatus
    checked_at: float
    checks: tuple[HealthProbeResult, ...]


class HealthRegistry:
    """Register and evaluate service dependency checks."""

    def __init__(
        self,
        checks: Iterable[HealthCheck] = (),
        *,
        clock: Callable[[], float] = time.time,
        timer: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._checks: list[HealthCheck] = []
        self._clock = clock
        self._timer = timer

        for check in checks:
            self.register(check)

    @property
    def registered_names(self) -> tuple[str, ...]:
        return tuple(
            check.name
            for check in self._checks
        )

    def register(
        self,
        check: HealthCheck,
    ) -> None:
        if any(
            existing.name == check.name
            for existing in self._checks
        ):
            raise HealthRegistryError(
                f"duplicate health check: {check.name}"
            )

        self._checks.append(check)

    async def evaluate(
        self,
        scope: HealthScope,
    ) -> HealthEvaluation:
        normalized_scope = HealthScope(scope)

        relevant = tuple(
            check
            for check in self._checks
            if normalized_scope in check.scopes
        )

        results = tuple(
            [
                await self._execute(check)
                for check in relevant
            ]
        )

        return HealthEvaluation(
            scope=normalized_scope,
            status=self._aggregate(results),
            checked_at=self._clock(),
            checks=results,
        )

    async def snapshot(self) -> HealthSnapshot:
        results = tuple(
            [
                await self._execute(check)
                for check in self._checks
            ]
        )

        startup = self._aggregate_for_scope(
            results,
            HealthScope.STARTUP,
        )
        liveness = self._aggregate_for_scope(
            results,
            HealthScope.LIVENESS,
        )
        readiness = self._aggregate_for_scope(
            results,
            HealthScope.READINESS,
        )

        overall = self._aggregate_statuses(
            (
                startup,
                liveness,
                readiness,
            )
        )

        return HealthSnapshot(
            overall=overall,
            startup=startup,
            liveness=liveness,
            readiness=readiness,
            checked_at=self._clock(),
            checks=results,
        )

    async def _execute(
        self,
        check: HealthCheck,
    ) -> HealthProbeResult:
        started = self._timer()

        try:
            value = check.callback()

            if inspect.isawaitable(value):
                if check.timeout_seconds is None:
                    value = await value
                else:
                    value = await asyncio.wait_for(
                        value,
                        timeout=check.timeout_seconds,
                    )

            outcome = self._normalize(value)

        except asyncio.TimeoutError:
            outcome = HealthOutcome(
                status=HealthStatus.UNHEALTHY,
                detail="health callback timed out",
            )

        except Exception as exc:
            # Exception messages may contain credentials.
            # Expose only the exception class.
            outcome = HealthOutcome(
                status=HealthStatus.UNHEALTHY,
                detail=(
                    "health callback failed: "
                    f"{type(exc).__name__}"
                ),
            )

        duration_ms = max(
            0.0,
            (self._timer() - started) * 1000.0,
        )

        return HealthProbeResult(
            name=check.name,
            status=outcome.status,
            required=check.required,
            scopes=tuple(
                sorted(
                    check.scopes,
                    key=lambda scope: scope.value,
                )
            ),
            detail=outcome.detail,
            checked_at=self._clock(),
            duration_ms=duration_ms,
        )

    @staticmethod
    def _normalize(
        value: object,
    ) -> HealthOutcome:
        if isinstance(value, HealthOutcome):
            return value

        if isinstance(value, HealthStatus):
            return HealthOutcome(
                status=value
            )

        if isinstance(value, bool):
            return HealthOutcome(
                status=(
                    HealthStatus.HEALTHY
                    if value
                    else HealthStatus.UNHEALTHY
                )
            )

        raise TypeError(
            "health callback returned an unsupported result"
        )

    @classmethod
    def _aggregate_for_scope(
        cls,
        results: tuple[HealthProbeResult, ...],
        scope: HealthScope,
    ) -> HealthStatus:
        return cls._aggregate(
            tuple(
                result
                for result in results
                if scope in result.scopes
            )
        )

    @staticmethod
    def _aggregate(
        results: tuple[HealthProbeResult, ...],
    ) -> HealthStatus:
        if not results:
            return HealthStatus.HEALTHY

        if any(
            result.required
            and result.status is HealthStatus.UNHEALTHY
            for result in results
        ):
            return HealthStatus.UNHEALTHY

        if any(
            result.status
            in {
                HealthStatus.DEGRADED,
                HealthStatus.UNHEALTHY,
            }
            for result in results
        ):
            return HealthStatus.DEGRADED

        return HealthStatus.HEALTHY

    @staticmethod
    def _aggregate_statuses(
        statuses: tuple[HealthStatus, ...],
    ) -> HealthStatus:
        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY

        if HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED

        return HealthStatus.HEALTHY


class ServiceRuntimeHealthAdapter:
    """Expose ServiceRuntime state as standard health checks."""

    def __init__(
        self,
        runtime: ServiceRuntime,
    ) -> None:
        self.runtime = runtime

    def startup(self) -> HealthOutcome:
        state = self.runtime.state

        return HealthOutcome(
            status=(
                HealthStatus.HEALTHY
                if state is ServiceState.RUNNING
                else HealthStatus.UNHEALTHY
            ),
            detail=f"service_state={state.value}",
        )

    def liveness(self) -> HealthOutcome:
        state = self.runtime.state

        live_states = {
            ServiceState.STARTING,
            ServiceState.RUNNING,
            ServiceState.STOPPING,
        }

        return HealthOutcome(
            status=(
                HealthStatus.HEALTHY
                if state in live_states
                else HealthStatus.UNHEALTHY
            ),
            detail=f"service_state={state.value}",
        )

    def readiness(self) -> HealthOutcome:
        ready = (
            self.runtime.state is ServiceState.RUNNING
            and not self.runtime.shutdown_requested
        )

        return HealthOutcome(
            status=(
                HealthStatus.HEALTHY
                if ready
                else HealthStatus.UNHEALTHY
            ),
            detail=(
                f"service_state={self.runtime.state.value};"
                "shutdown_requested="
                f"{str(self.runtime.shutdown_requested).lower()}"
            ),
        )

    def checks(self) -> tuple[HealthCheck, ...]:
        return (
            HealthCheck(
                name="service-startup",
                callback=self.startup,
                scopes=frozenset(
                    {HealthScope.STARTUP}
                ),
            ),
            HealthCheck(
                name="service-liveness",
                callback=self.liveness,
                scopes=frozenset(
                    {HealthScope.LIVENESS}
                ),
            ),
            HealthCheck(
                name="service-readiness",
                callback=self.readiness,
                scopes=frozenset(
                    {HealthScope.READINESS}
                ),
            ),
        )
