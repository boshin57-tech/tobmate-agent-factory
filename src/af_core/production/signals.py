"""Operating-system signal binding for graceful shutdown."""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Iterable

from .service_runtime import ServiceRuntime


class SignalBindingError(RuntimeError):
    """Raised when service shutdown signals cannot be bound."""


class SignalShutdownController:
    """Bind SIGTERM/SIGINT to ServiceRuntime shutdown requests."""

    def __init__(
        self,
        runtime: ServiceRuntime,
        *,
        loop=None,
        signals: Iterable[int] = (
            signal.SIGTERM,
            signal.SIGINT,
        ),
    ) -> None:
        normalized = tuple(
            int(signum)
            for signum in signals
        )

        if not normalized:
            raise ValueError(
                "at least one shutdown signal is required"
            )

        if len(normalized) != len(
            set(normalized)
        ):
            raise ValueError(
                "shutdown signals must be unique"
            )

        self.runtime = runtime
        self._loop = loop
        self._signals = normalized
        self._installed = False
        self._bound_loop = None

    @property
    def installed(self) -> bool:
        return self._installed

    @property
    def bound_signals(self) -> tuple[int, ...]:
        return self._signals

    def install(self) -> None:
        """Install event-loop signal callbacks once."""

        if self._installed:
            return

        loop = self._loop

        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError as exc:
                raise SignalBindingError(
                    "signal installation requires "
                    "a running event loop"
                ) from exc

        installed: list[int] = []

        try:
            for signum in self._signals:
                loop.add_signal_handler(
                    signum,
                    self.handle_signal,
                    signum,
                )
                installed.append(signum)

        except (
            NotImplementedError,
            RuntimeError,
            ValueError,
        ) as exc:
            for signum in installed:
                loop.remove_signal_handler(
                    signum
                )

            raise SignalBindingError(
                "operating-system signal "
                "binding failed"
            ) from exc

        self._bound_loop = loop
        self._installed = True

    def uninstall(self) -> None:
        """Remove installed callbacks safely."""

        if not self._installed:
            return

        assert self._bound_loop is not None

        for signum in self._signals:
            self._bound_loop.remove_signal_handler(
                signum
            )

        self._bound_loop = None
        self._installed = False

    def handle_signal(
        self,
        signum: int,
    ) -> None:
        """Convert an OS signal into a graceful shutdown request."""

        self.runtime.request_shutdown(
            self._reason(signum)
        )

    @staticmethod
    def _reason(
        signum: int,
    ) -> str:
        try:
            name = signal.Signals(
                signum
            ).name.lower()
        except ValueError:
            name = str(signum)

        return f"signal:{name}"
