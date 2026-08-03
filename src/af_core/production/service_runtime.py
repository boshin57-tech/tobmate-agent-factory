"""Production service lifecycle and graceful resource shutdown."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum


LifecycleCallback = Callable[[], object]


class ServiceRuntimeError(RuntimeError):
    """Base error for service lifecycle failures."""


class ServiceStartupError(ServiceRuntimeError):
    """Raised when a service resource cannot start."""


class ServiceShutdownError(ServiceRuntimeError):
    """Raised when graceful resource shutdown fails."""


class ServiceState(StrEnum):
    """Top-level production service lifecycle states."""

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ServiceResource:
    """One named resource managed by the service runtime."""

    name: str
    start: LifecycleCallback | None = None
    stop: LifecycleCallback | None = None
    required: bool = True

    def __post_init__(self) -> None:
        normalized = self.name.strip()

        if not normalized:
            raise ValueError(
                "service resource name must not be empty"
            )

        if normalized != self.name:
            object.__setattr__(
                self,
                "name",
                normalized,
            )

        if (
            self.start is not None
            and not callable(self.start)
        ):
            raise TypeError(
                "resource start callback must be callable"
            )

        if (
            self.stop is not None
            and not callable(self.stop)
        ):
            raise TypeError(
                "resource stop callback must be callable"
            )


@dataclass(frozen=True, slots=True)
class ServiceRuntimeSnapshot:
    """Credential-free service lifecycle snapshot."""

    state: ServiceState
    registered_resources: tuple[str, ...]
    started_resources: tuple[str, ...]
    shutdown_requested: bool
    shutdown_reason: str
    failure: str
    started_at: float | None
    stopped_at: float | None


class ServiceRuntime:
    """Coordinate ordered startup and reverse graceful shutdown."""

    def __init__(
        self,
        resources: Iterable[ServiceResource] = (),
        *,
        shutdown_timeout_seconds: float = 30.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if shutdown_timeout_seconds <= 0:
            raise ValueError(
                "shutdown_timeout_seconds must be positive"
            )

        self._resources: list[ServiceResource] = []
        self._started: list[ServiceResource] = []
        self._state = ServiceState.CREATED
        self._shutdown_timeout_seconds = (
            float(shutdown_timeout_seconds)
        )
        self._clock = clock
        self._shutdown_event = asyncio.Event()
        self._shutdown_reason = ""
        self._failure = ""
        self._started_at: float | None = None
        self._stopped_at: float | None = None
        self._lock = asyncio.Lock()

        for resource in resources:
            self.register(resource)

    @property
    def state(self) -> ServiceState:
        return self._state

    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown_event.is_set()

    @property
    def started_resources(self) -> tuple[str, ...]:
        return tuple(
            resource.name
            for resource in self._started
        )

    def snapshot(self) -> ServiceRuntimeSnapshot:
        return ServiceRuntimeSnapshot(
            state=self._state,
            registered_resources=tuple(
                resource.name
                for resource in self._resources
            ),
            started_resources=self.started_resources,
            shutdown_requested=(
                self.shutdown_requested
            ),
            shutdown_reason=self._shutdown_reason,
            failure=self._failure,
            started_at=self._started_at,
            stopped_at=self._stopped_at,
        )

    def register(
        self,
        resource: ServiceResource,
    ) -> None:
        """Register a unique resource before startup."""

        if self._state is not ServiceState.CREATED:
            raise ServiceRuntimeError(
                "resources may only be registered "
                "before service startup"
            )

        if any(
            existing.name == resource.name
            for existing in self._resources
        ):
            raise ServiceRuntimeError(
                "duplicate service resource: "
                f"{resource.name}"
            )

        self._resources.append(resource)

    async def start(self) -> ServiceRuntimeSnapshot:
        """Start resources in registration order."""

        async with self._lock:
            if self._state is not ServiceState.CREATED:
                raise ServiceRuntimeError(
                    "service may only start from "
                    "the created state"
                )

            self._state = ServiceState.STARTING
            self._failure = ""

            for resource in self._resources:
                try:
                    await self._invoke(
                        resource.start
                    )
                except BaseException as exc:
                    self._failure = (
                        f"{resource.name}: "
                        f"{type(exc).__name__}: {exc}"
                    )

                    rollback_errors = (
                        await self._shutdown_started(
                            self._shutdown_timeout_seconds
                        )
                    )

                    if rollback_errors:
                        self._failure += (
                            "; rollback: "
                            + "; ".join(
                                rollback_errors
                            )
                        )

                    self._state = ServiceState.FAILED

                    raise ServiceStartupError(
                        "service resource startup failed: "
                        f"{resource.name}"
                    ) from exc

                self._started.append(resource)

            self._state = ServiceState.RUNNING
            self._started_at = self._clock()

            return self.snapshot()

    async def stop(
        self,
        *,
        reason: str = "requested",
        timeout_seconds: float | None = None,
    ) -> ServiceRuntimeSnapshot:
        """Stop started resources in reverse order."""

        timeout = (
            self._shutdown_timeout_seconds
            if timeout_seconds is None
            else float(timeout_seconds)
        )

        if timeout <= 0:
            raise ValueError(
                "shutdown timeout must be positive"
            )

        async with self._lock:
            if self._state is ServiceState.STOPPED:
                return self.snapshot()

            normalized_reason = (
                reason.strip() or "requested"
            )
            self._shutdown_reason = (
                normalized_reason
            )
            self._shutdown_event.set()

            if self._state is ServiceState.CREATED:
                self._state = ServiceState.STOPPED
                self._stopped_at = self._clock()
                return self.snapshot()

            self._state = ServiceState.STOPPING

            errors = await self._shutdown_started(
                timeout
            )

            if errors:
                self._failure = "; ".join(errors)
                self._state = ServiceState.FAILED

                raise ServiceShutdownError(
                    "one or more service resources "
                    "failed to stop: "
                    + self._failure
                )

            self._state = ServiceState.STOPPED
            self._stopped_at = self._clock()

            return self.snapshot()

    def request_shutdown(
        self,
        reason: str = "requested",
    ) -> None:
        """Request graceful shutdown without stopping inline."""

        normalized = reason.strip() or "requested"

        if not self._shutdown_event.is_set():
            self._shutdown_reason = normalized

        self._shutdown_event.set()

    async def wait_for_shutdown(self) -> str:
        """Wait until an external shutdown request is made."""

        await self._shutdown_event.wait()
        return self._shutdown_reason or "requested"

    async def run_until_shutdown(
        self,
    ) -> ServiceRuntimeSnapshot:
        """Start, wait for a request, and shut down cleanly."""

        await self.start()
        reason = await self.wait_for_shutdown()

        return await self.stop(
            reason=reason
        )

    async def __aenter__(
        self,
    ) -> ServiceRuntime:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type,
        exc,
        traceback,
    ) -> bool:
        try:
            await self.stop(
                reason=(
                    "context-error"
                    if exc is not None
                    else "context-exit"
                )
            )
        except ServiceShutdownError:
            if exc is None:
                raise

        return False

    async def _shutdown_started(
        self,
        timeout_seconds: float,
    ) -> list[str]:
        """Stop all possible resources before the deadline."""

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        errors: list[str] = []

        for resource in reversed(
            tuple(self._started)
        ):
            remaining = deadline - loop.time()

            if remaining <= 0:
                errors.append(
                    f"{resource.name}: shutdown timeout"
                )
                break

            try:
                await asyncio.wait_for(
                    self._invoke(resource.stop),
                    timeout=remaining,
                )
            except asyncio.TimeoutError:
                errors.append(
                    f"{resource.name}: shutdown timeout"
                )
                break
            except BaseException as exc:
                errors.append(
                    f"{resource.name}: "
                    f"{type(exc).__name__}: {exc}"
                )
                continue

            self._started.remove(resource)

        return errors

    @staticmethod
    async def _invoke(
        callback: LifecycleCallback | None,
    ) -> None:
        if callback is None:
            return

        result = callback()

        if inspect.isawaitable(result):
            await result
