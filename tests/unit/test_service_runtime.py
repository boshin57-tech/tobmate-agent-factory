import asyncio

import pytest

from af_core.production.service_runtime import (
    ServiceResource,
    ServiceRuntime,
    ServiceRuntimeError,
    ServiceShutdownError,
    ServiceStartupError,
    ServiceState,
)


def test_initial_snapshot_is_created():
    runtime = ServiceRuntime(
        (
            ServiceResource("database"),
            ServiceResource("artifact-store"),
        )
    )

    snapshot = runtime.snapshot()

    assert snapshot.state is ServiceState.CREATED
    assert snapshot.registered_resources == (
        "database",
        "artifact-store",
    )
    assert snapshot.started_resources == ()
    assert snapshot.shutdown_requested is False
    assert snapshot.failure == ""


def test_duplicate_resource_is_rejected():
    runtime = ServiceRuntime(
        (ServiceResource("database"),)
    )

    with pytest.raises(
        ServiceRuntimeError,
        match="duplicate",
    ):
        runtime.register(
            ServiceResource("database")
        )


@pytest.mark.asyncio
async def test_resources_start_in_registration_order():
    events: list[str] = []

    runtime = ServiceRuntime(
        (
            ServiceResource(
                "database",
                start=lambda: events.append(
                    "start-database"
                ),
            ),
            ServiceResource(
                "artifact-store",
                start=lambda: events.append(
                    "start-artifact"
                ),
            ),
        )
    )

    snapshot = await runtime.start()

    assert events == [
        "start-database",
        "start-artifact",
    ]
    assert snapshot.state is ServiceState.RUNNING
    assert snapshot.started_resources == (
        "database",
        "artifact-store",
    )


@pytest.mark.asyncio
async def test_resources_stop_in_reverse_order():
    events: list[str] = []

    runtime = ServiceRuntime(
        (
            ServiceResource(
                "database",
                stop=lambda: events.append(
                    "stop-database"
                ),
            ),
            ServiceResource(
                "artifact-store",
                stop=lambda: events.append(
                    "stop-artifact"
                ),
            ),
        )
    )

    await runtime.start()
    snapshot = await runtime.stop(
        reason="test-complete"
    )

    assert events == [
        "stop-artifact",
        "stop-database",
    ]
    assert snapshot.state is ServiceState.STOPPED
    assert snapshot.started_resources == ()
    assert snapshot.shutdown_reason == (
        "test-complete"
    )


@pytest.mark.asyncio
async def test_sync_and_async_callbacks_are_supported():
    events: list[str] = []

    async def async_start() -> None:
        await asyncio.sleep(0)
        events.append("async-start")

    async def async_stop() -> None:
        await asyncio.sleep(0)
        events.append("async-stop")

    runtime = ServiceRuntime(
        (
            ServiceResource(
                "sync",
                start=lambda: events.append(
                    "sync-start"
                ),
                stop=lambda: events.append(
                    "sync-stop"
                ),
            ),
            ServiceResource(
                "async",
                start=async_start,
                stop=async_stop,
            ),
        )
    )

    await runtime.start()
    await runtime.stop()

    assert events == [
        "sync-start",
        "async-start",
        "async-stop",
        "sync-stop",
    ]


@pytest.mark.asyncio
async def test_registration_after_start_is_rejected():
    runtime = ServiceRuntime()

    await runtime.start()

    with pytest.raises(
        ServiceRuntimeError,
        match="before service startup",
    ):
        runtime.register(
            ServiceResource("late")
        )


@pytest.mark.asyncio
async def test_duplicate_start_is_rejected():
    runtime = ServiceRuntime()

    await runtime.start()

    with pytest.raises(
        ServiceRuntimeError,
        match="created state",
    ):
        await runtime.start()


@pytest.mark.asyncio
async def test_stop_before_start_is_safe():
    runtime = ServiceRuntime()

    first = await runtime.stop(
        reason="never-started"
    )
    second = await runtime.stop()

    assert first.state is ServiceState.STOPPED
    assert second.state is ServiceState.STOPPED
    assert first.shutdown_reason == (
        "never-started"
    )


@pytest.mark.asyncio
async def test_stop_is_idempotent():
    calls = 0

    def stop_resource() -> None:
        nonlocal calls
        calls += 1

    runtime = ServiceRuntime(
        (
            ServiceResource(
                "resource",
                stop=stop_resource,
            ),
        )
    )

    await runtime.start()
    first = await runtime.stop()
    second = await runtime.stop()

    assert calls == 1
    assert first.state is ServiceState.STOPPED
    assert second.state is ServiceState.STOPPED


@pytest.mark.asyncio
async def test_startup_failure_rolls_back_started_resources():
    events: list[str] = []

    def fail_start() -> None:
        events.append("start-second")
        raise RuntimeError("startup failed")

    runtime = ServiceRuntime(
        (
            ServiceResource(
                "first",
                start=lambda: events.append(
                    "start-first"
                ),
                stop=lambda: events.append(
                    "stop-first"
                ),
            ),
            ServiceResource(
                "second",
                start=fail_start,
            ),
        )
    )

    with pytest.raises(
        ServiceStartupError,
        match="second",
    ):
        await runtime.start()

    snapshot = runtime.snapshot()

    assert events == [
        "start-first",
        "start-second",
        "stop-first",
    ]
    assert snapshot.state is ServiceState.FAILED
    assert snapshot.started_resources == ()
    assert "startup failed" in snapshot.failure


@pytest.mark.asyncio
async def test_shutdown_failure_continues_and_can_retry():
    events: list[str] = []
    fail_once = True

    def stop_first() -> None:
        nonlocal fail_once
        events.append("stop-first")

        if fail_once:
            fail_once = False
            raise RuntimeError("temporary failure")

    runtime = ServiceRuntime(
        (
            ServiceResource(
                "first",
                stop=stop_first,
            ),
            ServiceResource(
                "second",
                stop=lambda: events.append(
                    "stop-second"
                ),
            ),
        )
    )

    await runtime.start()

    with pytest.raises(
        ServiceShutdownError,
        match="temporary failure",
    ):
        await runtime.stop()

    failed = runtime.snapshot()

    assert events == [
        "stop-second",
        "stop-first",
    ]
    assert failed.state is ServiceState.FAILED
    assert failed.started_resources == (
        "first",
    )

    recovered = await runtime.stop(
        reason="retry"
    )

    assert events == [
        "stop-second",
        "stop-first",
        "stop-first",
    ]
    assert recovered.state is ServiceState.STOPPED
    assert recovered.started_resources == ()


@pytest.mark.asyncio
async def test_shutdown_timeout_preserves_pending_resource():
    async def slow_stop() -> None:
        await asyncio.sleep(0.05)

    runtime = ServiceRuntime(
        (
            ServiceResource(
                "slow",
                stop=slow_stop,
            ),
        ),
        shutdown_timeout_seconds=0.01,
    )

    await runtime.start()

    with pytest.raises(
        ServiceShutdownError,
        match="timeout",
    ):
        await runtime.stop()

    assert runtime.state is ServiceState.FAILED
    assert runtime.started_resources == ("slow",)

    snapshot = await runtime.stop(
        timeout_seconds=0.2,
        reason="retry-after-timeout",
    )

    assert snapshot.state is ServiceState.STOPPED
    assert snapshot.started_resources == ()


@pytest.mark.asyncio
async def test_shutdown_request_can_be_awaited():
    runtime = ServiceRuntime()

    waiter = asyncio.create_task(
        runtime.wait_for_shutdown()
    )

    await asyncio.sleep(0)
    runtime.request_shutdown("sigterm")

    assert await waiter == "sigterm"
    assert runtime.shutdown_requested is True


@pytest.mark.asyncio
async def test_run_until_shutdown_manages_full_lifecycle():
    events: list[str] = []

    runtime = ServiceRuntime(
        (
            ServiceResource(
                "database",
                start=lambda: events.append(
                    "start"
                ),
                stop=lambda: events.append(
                    "stop"
                ),
            ),
        )
    )

    task = asyncio.create_task(
        runtime.run_until_shutdown()
    )

    for _ in range(20):
        if runtime.state is ServiceState.RUNNING:
            break

        await asyncio.sleep(0)

    assert runtime.state is ServiceState.RUNNING

    runtime.request_shutdown("operator")

    snapshot = await task

    assert snapshot.state is ServiceState.STOPPED
    assert snapshot.shutdown_reason == "operator"
    assert events == ["start", "stop"]


@pytest.mark.asyncio
async def test_async_context_manager_starts_and_stops():
    events: list[str] = []

    runtime = ServiceRuntime(
        (
            ServiceResource(
                "resource",
                start=lambda: events.append(
                    "start"
                ),
                stop=lambda: events.append(
                    "stop"
                ),
            ),
        )
    )

    async with runtime as active:
        assert active.state is ServiceState.RUNNING
        assert events == ["start"]

    assert runtime.state is ServiceState.STOPPED
    assert events == ["start", "stop"]
