import signal

import pytest

from af_core.production.service_runtime import (
    ServiceRuntime,
)
from af_core.production.signals import (
    SignalShutdownController,
)


class FakeLoop:
    def __init__(self) -> None:
        self.handlers: dict[
            int,
            tuple[object, tuple[object, ...]],
        ] = {}
        self.removed: list[int] = []

    def add_signal_handler(
        self,
        signum,
        callback,
        *args,
    ) -> None:
        self.handlers[int(signum)] = (
            callback,
            args,
        )

    def remove_signal_handler(
        self,
        signum,
    ) -> bool:
        normalized = int(signum)
        self.removed.append(normalized)

        return (
            self.handlers.pop(
                normalized,
                None,
            )
            is not None
        )


def test_signal_configuration_is_validated():
    runtime = ServiceRuntime()

    with pytest.raises(
        ValueError,
        match="at least one",
    ):
        SignalShutdownController(
            runtime,
            signals=(),
        )

    with pytest.raises(
        ValueError,
        match="unique",
    ):
        SignalShutdownController(
            runtime,
            signals=(
                signal.SIGTERM,
                signal.SIGTERM,
            ),
        )


def test_install_binds_sigterm_and_sigint():
    runtime = ServiceRuntime()
    loop = FakeLoop()

    controller = SignalShutdownController(
        runtime,
        loop=loop,
    )

    controller.install()

    assert controller.installed is True
    assert set(loop.handlers) == {
        int(signal.SIGTERM),
        int(signal.SIGINT),
    }


def test_bound_handler_requests_shutdown():
    runtime = ServiceRuntime()
    loop = FakeLoop()

    controller = SignalShutdownController(
        runtime,
        loop=loop,
    )
    controller.install()

    callback, arguments = loop.handlers[
        int(signal.SIGTERM)
    ]

    callback(*arguments)

    snapshot = runtime.snapshot()

    assert snapshot.shutdown_requested is True
    assert snapshot.shutdown_reason == (
        "signal:sigterm"
    )


def test_uninstall_removes_all_handlers():
    runtime = ServiceRuntime()
    loop = FakeLoop()

    controller = SignalShutdownController(
        runtime,
        loop=loop,
    )

    controller.install()
    controller.uninstall()

    assert controller.installed is False
    assert loop.handlers == {}
    assert set(loop.removed) == {
        int(signal.SIGTERM),
        int(signal.SIGINT),
    }


def test_install_and_uninstall_are_idempotent():
    runtime = ServiceRuntime()
    loop = FakeLoop()

    controller = SignalShutdownController(
        runtime,
        loop=loop,
    )

    controller.install()
    controller.install()

    assert len(loop.handlers) == 2

    controller.uninstall()
    controller.uninstall()

    assert len(loop.removed) == 2


def test_custom_signal_reason_is_supported():
    runtime = ServiceRuntime()
    loop = FakeLoop()

    controller = SignalShutdownController(
        runtime,
        loop=loop,
        signals=(99,),
    )

    controller.install()

    callback, arguments = loop.handlers[99]
    callback(*arguments)

    assert runtime.snapshot().shutdown_reason == (
        "signal:99"
    )
