from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from af_core.production.service_host_models import (
    ServiceHostConfigurationError,
    ServiceHostSettings,
    ServiceHostSnapshot,
    ServiceHostState,
)


def test_service_host_settings_defaults() -> None:
    settings = ServiceHostSettings()

    assert settings.probe_enabled is True
    assert settings.probe_host == "127.0.0.1"
    assert settings.probe_port == 8080
    assert settings.request_timeout_seconds == 5.0
    assert settings.shutdown_timeout_seconds == 30.0
    assert settings.maximum_request_bytes == 8192
    assert settings.backlog == 128

    snapshot = settings.public_snapshot()

    assert snapshot == {
        "probe_enabled": True,
        "probe_host": "127.0.0.1",
        "probe_port": 8080,
        "request_timeout_seconds": 5.0,
        "shutdown_timeout_seconds": 30.0,
        "maximum_request_bytes": 8192,
        "backlog": 128,
    }


def test_service_host_settings_from_environment() -> None:
    settings = ServiceHostSettings.from_environment(
        {
            "AF_CORE_HOST_PROBE_ENABLED": "false",
            "AF_CORE_HOST_PROBE_HOST": "localhost",
            "AF_CORE_HOST_PROBE_PORT": "9090",
            "AF_CORE_HOST_REQUEST_TIMEOUT_SECONDS": "2.5",
            "AF_CORE_HOST_SHUTDOWN_TIMEOUT_SECONDS": "15",
            "AF_CORE_HOST_MAXIMUM_REQUEST_BYTES": "4096",
            "AF_CORE_HOST_BACKLOG": "32",
        }
    )

    assert settings.probe_enabled is False
    assert settings.probe_host == "localhost"
    assert settings.probe_port == 9090
    assert settings.request_timeout_seconds == 2.5
    assert settings.shutdown_timeout_seconds == 15.0
    assert settings.maximum_request_bytes == 4096
    assert settings.backlog == 32


def test_service_host_settings_reject_unknown_key() -> None:
    with pytest.raises(
        ServiceHostConfigurationError,
        match="unknown service-host environment keys",
    ):
        ServiceHostSettings.from_environment(
            {
                "AF_CORE_HOST_UNAPPROVED_SECRET": "value",
            }
        )


def test_service_host_settings_reject_invalid_boolean() -> None:
    with pytest.raises(
        ServiceHostConfigurationError,
        match="must be a boolean",
    ):
        ServiceHostSettings.from_environment(
            {
                "AF_CORE_HOST_PROBE_ENABLED": "perhaps",
            }
        )


def test_service_host_snapshot_is_frozen() -> None:
    snapshot = ServiceHostSnapshot(
        state=ServiceHostState.RUNNING,
        service_name="af-core",
        instance_id="unit-test",
        runtime_state="running",
        probe_enabled=True,
        configured_probe_host="127.0.0.1",
        configured_probe_port=0,
        bound_probe_host="127.0.0.1",
        bound_probe_port=41001,
        signal_controller_installed=False,
    )

    assert snapshot.bound_probe_port == 41001

    with pytest.raises(ValidationError):
        snapshot.state = ServiceHostState.FAILED

from af_core.production.configuration import (
    ProductionSettings,
)
from af_core.production.service_host import (
    ProductionServiceHost,
)
from af_core.production.service_host_models import (
    ServiceHostShutdownError,
    ServiceHostStartupError,
)


def make_host(
    *,
    probe_enabled: bool = False,
) -> ProductionServiceHost:
    return ProductionServiceHost(
        ProductionSettings(
            service_name="af-core",
            instance_id="service-host-test",
        ),
        ServiceHostSettings(
            probe_enabled=probe_enabled,
            probe_port=0,
            shutdown_timeout_seconds=5.0,
        ),
        manage_signals=False,
    )


@pytest.mark.asyncio
async def test_service_host_start_and_stop() -> None:
    host = make_host()

    started = await host.start()

    assert started.state is ServiceHostState.RUNNING
    assert started.runtime_state == "running"
    assert host.state is ServiceHostState.RUNNING

    stopped = await host.stop(
        reason="unit-test-complete",
    )

    assert stopped.state is ServiceHostState.STOPPED
    assert stopped.runtime_state == "stopped"
    assert (
        stopped.shutdown_reason
        == "unit-test-complete"
    )


@pytest.mark.asyncio
async def test_service_host_running_start_is_idempotent() -> None:
    host = make_host()

    first = await host.start()
    second = await host.start()

    assert first.state is ServiceHostState.RUNNING
    assert second.state is ServiceHostState.RUNNING
    assert host.runtime.started_resources == ()

    await host.stop(
        reason="idempotent-start-complete",
    )


@pytest.mark.asyncio
async def test_service_host_run_stops_after_shutdown_request() -> None:
    host = make_host()

    task = asyncio.create_task(
        host.run()
    )

    for _ in range(100):
        if host.state is ServiceHostState.RUNNING:
            break

        await asyncio.sleep(0)

    assert host.state is ServiceHostState.RUNNING

    host.request_shutdown(
        "unit-test-shutdown",
    )

    stopped = await task

    assert stopped.state is ServiceHostState.STOPPED
    assert (
        stopped.shutdown_reason
        == "unit-test-shutdown"
    )


def test_service_host_rejects_empty_shutdown_reason() -> None:
    host = make_host()

    with pytest.raises(
        ServiceHostShutdownError,
        match="must not be empty",
    ):
        host.request_shutdown("   ")


async def send_probe_request(
    host: str,
    port: int,
    payload: bytes,
) -> bytes:
    reader, writer = await asyncio.open_connection(
        host,
        port,
    )

    writer.write(payload)
    await writer.drain()

    response = await asyncio.wait_for(
        reader.read(),
        timeout=2.0,
    )

    writer.close()
    await writer.wait_closed()

    return response


@pytest.mark.asyncio
async def test_service_host_probe_routes() -> None:
    host = make_host(
        probe_enabled=True,
    )

    await host.start()

    address = host.bound_probe_address

    assert address is not None

    probe_host, probe_port = address

    expected = {
        "/health": b"HTTP/1.1 200 ",
        "/health/live": b"HTTP/1.1 200 ",
        "/health/ready": b"HTTP/1.1 200 ",
        "/health/startup": b"HTTP/1.1 200 ",
        "/metrics": b"HTTP/1.1 200 ",
        "/unknown": b"HTTP/1.1 404 ",
    }

    for path, status in expected.items():
        response = await send_probe_request(
            probe_host,
            probe_port,
            (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {probe_host}\r\n"
                "Connection: close\r\n"
                "\r\n"
            ).encode("ascii"),
        )

        assert response.startswith(status)
        assert b"Connection: close\r\n" in response
        assert b"Cache-Control: no-store\r\n" in response
        assert (
            b"X-Content-Type-Options: nosniff\r\n"
            in response
        )

    await host.stop(
        reason="probe-route-test-complete",
    )


@pytest.mark.asyncio
async def test_service_host_probe_rejects_invalid_header() -> None:
    host = make_host(
        probe_enabled=True,
    )

    await host.start()

    address = host.bound_probe_address

    assert address is not None

    probe_host, probe_port = address

    response = await send_probe_request(
        probe_host,
        probe_port,
        (
            b"GET /health HTTP/1.1\r\n"
            b"Invalid-Header\r\n"
            b"\r\n"
        ),
    )

    assert response.startswith(
        b"HTTP/1.1 400 "
    )
    assert b'"error":"bad request"' in response

    await host.stop(
        reason="invalid-header-test-complete",
    )


@pytest.mark.asyncio
async def test_service_host_probe_rejects_request_body() -> None:
    host = make_host(
        probe_enabled=True,
    )

    await host.start()

    address = host.bound_probe_address

    assert address is not None

    probe_host, probe_port = address

    response = await send_probe_request(
        probe_host,
        probe_port,
        (
            b"GET /health HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 1\r\n"
            b"\r\n"
            b"X"
        ),
    )

    assert response.startswith(
        b"HTTP/1.1 400 "
    )
    assert b'"error":"bad request"' in response

    await host.stop(
        reason="request-body-test-complete",
    )


@pytest.mark.asyncio
async def test_service_host_stop_releases_probe_socket() -> None:
    host = make_host(
        probe_enabled=True,
    )

    await host.start()

    address = host.bound_probe_address

    assert address is not None

    probe_host, probe_port = address

    stopped = await host.stop(
        reason="socket-release-test",
    )

    assert stopped.state is ServiceHostState.STOPPED
    assert host.bound_probe_address is None

    with pytest.raises(OSError):
        await asyncio.open_connection(
            probe_host,
            probe_port,
        )


@pytest.mark.asyncio
async def test_service_host_stop_before_start() -> None:
    host = make_host()

    first = await host.stop(
        reason="not-started",
    )

    second = await host.stop(
        reason="already-stopped",
    )

    assert first.state is ServiceHostState.STOPPED
    assert second.state is ServiceHostState.STOPPED
    assert first.runtime_state == "created"
    assert second.shutdown_reason == "not-started"


@pytest.mark.asyncio
async def test_service_host_async_context_manager() -> None:
    host = make_host()

    async with host as running:
        assert running is host
        assert host.state is ServiceHostState.RUNNING

    snapshot = host.snapshot()

    assert snapshot.state is ServiceHostState.STOPPED
    assert snapshot.shutdown_reason == "context-exit"


@pytest.mark.asyncio
async def test_service_host_rejects_restart_after_stop() -> None:
    host = make_host()

    await host.stop(
        reason="pre-start-stop",
    )

    with pytest.raises(
        ServiceHostStartupError,
        match="cannot start",
    ):
        await host.start()


@pytest.mark.asyncio
async def test_service_host_bind_failure_sets_failed_state() -> None:
    blocker = await asyncio.start_server(
        lambda reader, writer: writer.close(),
        host="127.0.0.1",
        port=0,
    )

    sockets = tuple(blocker.sockets or ())

    assert sockets

    blocked_port = int(
        sockets[0].getsockname()[1]
    )

    host = ProductionServiceHost(
        ProductionSettings(
            service_name="af-core",
            instance_id="bind-failure-test",
        ),
        ServiceHostSettings(
            probe_enabled=True,
            probe_host="127.0.0.1",
            probe_port=blocked_port,
            shutdown_timeout_seconds=5.0,
        ),
        manage_signals=False,
    )

    try:
        with pytest.raises(
            ServiceHostStartupError,
            match="failed to start",
        ):
            await host.start()

        assert host.state is ServiceHostState.FAILED
        assert host.bound_probe_address is None

    finally:
        blocker.close()
        await blocker.wait_closed()


@pytest.mark.asyncio
async def test_service_host_context_error_stops_resources() -> None:
    host = make_host(
        probe_enabled=True,
    )

    with pytest.raises(
        RuntimeError,
        match="deliberate context failure",
    ):
        async with host:
            assert host.state is ServiceHostState.RUNNING
            assert host.bound_probe_address is not None

            raise RuntimeError(
                "deliberate context failure"
            )

    snapshot = host.snapshot()

    assert snapshot.state is ServiceHostState.STOPPED
    assert snapshot.shutdown_reason == "context-error"
    assert host.bound_probe_address is None


class FakeSignalController:
    def __init__(
        self,
        *,
        fail_install: bool = False,
    ) -> None:
        self.installed = False
        self.install_count = 0
        self.uninstall_count = 0
        self.fail_install = fail_install

    def install(self) -> None:
        self.install_count += 1

        if self.fail_install:
            raise RuntimeError(
                "signal installation failed"
            )

        self.installed = True

    def uninstall(self) -> None:
        self.uninstall_count += 1
        self.installed = False


@pytest.mark.asyncio
async def test_service_host_installs_and_uninstalls_signals() -> None:
    controller = FakeSignalController()

    host = ProductionServiceHost(
        ProductionSettings(
            service_name="af-core",
            instance_id="signal-lifecycle-test",
        ),
        ServiceHostSettings(
            probe_enabled=False,
        ),
        signal_controller=controller,
        manage_signals=True,
    )

    started = await host.start()

    assert started.state is ServiceHostState.RUNNING
    assert started.signal_controller_installed is True
    assert controller.install_count == 1

    stopped = await host.stop(
        reason="signal-test-complete",
    )

    assert stopped.state is ServiceHostState.STOPPED
    assert stopped.signal_controller_installed is False
    assert controller.uninstall_count == 1


@pytest.mark.asyncio
async def test_service_host_signal_install_failure() -> None:
    controller = FakeSignalController(
        fail_install=True,
    )

    host = ProductionServiceHost(
        ProductionSettings(
            service_name="af-core",
            instance_id="signal-failure-test",
        ),
        ServiceHostSettings(
            probe_enabled=False,
        ),
        signal_controller=controller,
        manage_signals=True,
    )

    with pytest.raises(
        ServiceHostStartupError,
        match="failed to start",
    ):
        await host.start()

    assert host.state is ServiceHostState.FAILED
    assert controller.install_count == 1
    assert controller.uninstall_count == 0
