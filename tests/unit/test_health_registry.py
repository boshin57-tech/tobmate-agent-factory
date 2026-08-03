import asyncio

import pytest

from af_core.production.health import (
    HealthCheck,
    HealthOutcome,
    HealthRegistry,
    HealthRegistryError,
    HealthScope,
    HealthStatus,
    ServiceRuntimeHealthAdapter,
)
from af_core.production.service_runtime import (
    ServiceRuntime,
    ServiceState,
)


@pytest.mark.asyncio
async def test_empty_registry_is_healthy():
    snapshot = await HealthRegistry().snapshot()

    assert snapshot.overall is HealthStatus.HEALTHY
    assert snapshot.startup is HealthStatus.HEALTHY
    assert snapshot.liveness is HealthStatus.HEALTHY
    assert snapshot.readiness is HealthStatus.HEALTHY
    assert snapshot.checks == ()


def test_duplicate_check_is_rejected():
    registry = HealthRegistry(
        (
            HealthCheck(
                "database",
                lambda: True,
            ),
        )
    )

    with pytest.raises(
        HealthRegistryError,
        match="duplicate",
    ):
        registry.register(
            HealthCheck(
                "database",
                lambda: True,
            )
        )


@pytest.mark.asyncio
async def test_required_failure_is_unhealthy():
    registry = HealthRegistry(
        (
            HealthCheck(
                "database",
                lambda: False,
                scopes=frozenset(
                    {HealthScope.READINESS}
                ),
            ),
        )
    )

    evaluation = await registry.evaluate(
        HealthScope.READINESS
    )

    assert (
        evaluation.status
        is HealthStatus.UNHEALTHY
    )


@pytest.mark.asyncio
async def test_optional_failure_is_degraded():
    registry = HealthRegistry(
        (
            HealthCheck(
                "analytics",
                lambda: False,
                scopes=frozenset(
                    {HealthScope.READINESS}
                ),
                required=False,
            ),
        )
    )

    evaluation = await registry.evaluate(
        HealthScope.READINESS
    )

    assert (
        evaluation.status
        is HealthStatus.DEGRADED
    )


@pytest.mark.asyncio
async def test_async_callback_and_outcome_are_supported():
    async def check() -> HealthOutcome:
        await asyncio.sleep(0)

        return HealthOutcome(
            status=HealthStatus.DEGRADED,
            detail="replica lag",
        )

    registry = HealthRegistry(
        (
            HealthCheck(
                "replica",
                check,
                required=False,
            ),
        )
    )

    snapshot = await registry.snapshot()

    assert (
        snapshot.checks[0].status
        is HealthStatus.DEGRADED
    )
    assert snapshot.checks[0].detail == (
        "replica lag"
    )


@pytest.mark.asyncio
async def test_callback_exception_redacts_message():
    def failing_check() -> bool:
        raise RuntimeError(
            "postgresql://user:secret@host/database"
        )

    registry = HealthRegistry(
        (
            HealthCheck(
                "database",
                failing_check,
            ),
        )
    )

    result = await registry.evaluate(
        HealthScope.READINESS
    )

    assert result.status is HealthStatus.UNHEALTHY
    assert "RuntimeError" in result.checks[0].detail
    assert "secret" not in result.checks[0].detail
    assert "postgresql" not in result.checks[0].detail


@pytest.mark.asyncio
async def test_async_timeout_is_unhealthy():
    async def slow_check() -> bool:
        await asyncio.sleep(0.05)
        return True

    registry = HealthRegistry(
        (
            HealthCheck(
                "slow",
                slow_check,
                timeout_seconds=0.01,
            ),
        )
    )

    result = await registry.evaluate(
        HealthScope.LIVENESS
    )

    assert result.status is HealthStatus.UNHEALTHY
    assert result.checks[0].detail == (
        "health callback timed out"
    )


@pytest.mark.asyncio
async def test_scope_filtering_is_preserved():
    registry = HealthRegistry(
        (
            HealthCheck(
                "database",
                lambda: True,
                scopes=frozenset(
                    {HealthScope.READINESS}
                ),
            ),
            HealthCheck(
                "process",
                lambda: True,
                scopes=frozenset(
                    {HealthScope.LIVENESS}
                ),
            ),
        )
    )

    readiness = await registry.evaluate(
        HealthScope.READINESS
    )
    liveness = await registry.evaluate(
        HealthScope.LIVENESS
    )

    assert tuple(
        check.name
        for check in readiness.checks
    ) == ("database",)

    assert tuple(
        check.name
        for check in liveness.checks
    ) == ("process",)


@pytest.mark.asyncio
async def test_runtime_adapter_tracks_running_state():
    runtime = ServiceRuntime()
    adapter = ServiceRuntimeHealthAdapter(
        runtime
    )
    registry = HealthRegistry(
        adapter.checks()
    )

    before = await registry.snapshot()

    assert before.startup is HealthStatus.UNHEALTHY
    assert before.readiness is HealthStatus.UNHEALTHY

    await runtime.start()

    running = await registry.snapshot()

    assert runtime.state is ServiceState.RUNNING
    assert running.startup is HealthStatus.HEALTHY
    assert running.liveness is HealthStatus.HEALTHY
    assert running.readiness is HealthStatus.HEALTHY


@pytest.mark.asyncio
async def test_shutdown_request_removes_readiness():
    runtime = ServiceRuntime()
    adapter = ServiceRuntimeHealthAdapter(
        runtime
    )
    registry = HealthRegistry(
        adapter.checks()
    )

    await runtime.start()
    runtime.request_shutdown("sigterm")

    snapshot = await registry.snapshot()

    assert snapshot.liveness is HealthStatus.HEALTHY
    assert snapshot.readiness is HealthStatus.UNHEALTHY

    await runtime.stop(reason="sigterm")
