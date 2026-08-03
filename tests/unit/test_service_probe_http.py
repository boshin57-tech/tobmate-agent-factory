import json

import pytest

from af_core.production.health import (
    HealthCheck,
    HealthOutcome,
    HealthRegistry,
    HealthScope,
    HealthStatus,
    ServiceRuntimeHealthAdapter,
)
from af_core.production.metrics import (
    MetricsRegistry,
    ServiceRuntimeMetricsAdapter,
)
from af_core.production.probe_http import (
    JSON_CONTENT_TYPE,
    ServiceProbeApplication,
)
from af_core.production.service_runtime import (
    ServiceRuntime,
)


def runtime_probe():
    runtime = ServiceRuntime()
    health = HealthRegistry(
        ServiceRuntimeHealthAdapter(
            runtime
        ).checks()
    )
    metrics = MetricsRegistry()
    metric_adapter = (
        ServiceRuntimeMetricsAdapter(
            runtime,
            metrics,
        )
    )
    metric_adapter.observe()

    application = ServiceProbeApplication(
        health,
        metrics,
    )

    return (
        runtime,
        metric_adapter,
        application,
    )


@pytest.mark.asyncio
async def test_startup_is_unhealthy_before_start():
    _, _, application = runtime_probe()

    response = await application.handle(
        "GET",
        "/health/startup",
    )

    payload = json.loads(response.body)

    assert response.status_code == 503
    assert response.content_type == (
        JSON_CONTENT_TYPE
    )
    assert payload["scope"] == "startup"
    assert payload["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_running_service_probes_are_healthy():
    runtime, _, application = runtime_probe()

    await runtime.start()

    for path in (
        "/health/startup",
        "/health/live",
        "/health/ready",
        "/health",
    ):
        response = await application.handle(
            "GET",
            path,
        )

        assert response.status_code == 200


@pytest.mark.asyncio
async def test_shutdown_request_removes_readiness():
    runtime, _, application = runtime_probe()

    await runtime.start()
    runtime.request_shutdown("sigterm")

    readiness = await application.handle(
        "GET",
        "/health/ready",
    )
    liveness = await application.handle(
        "GET",
        "/health/live",
    )

    assert readiness.status_code == 503
    assert liveness.status_code == 200

    await runtime.stop(reason="sigterm")


@pytest.mark.asyncio
async def test_optional_degraded_probe_returns_200():
    health = HealthRegistry(
        (
            HealthCheck(
                "optional-cache",
                lambda: False,
                scopes=frozenset(
                    {HealthScope.READINESS}
                ),
                required=False,
            ),
        )
    )

    application = ServiceProbeApplication(
        health,
        MetricsRegistry(),
    )

    response = await application.handle(
        "GET",
        "/health/ready",
    )

    payload = json.loads(response.body)

    assert response.status_code == 200
    assert payload["status"] == "degraded"


@pytest.mark.asyncio
async def test_public_probe_omits_check_detail():
    secret = "postgresql://user:secret@host/db"

    health = HealthRegistry(
        (
            HealthCheck(
                "database",
                lambda: HealthOutcome(
                    status=HealthStatus.DEGRADED,
                    detail=secret,
                ),
                required=False,
            ),
        )
    )

    application = ServiceProbeApplication(
        health,
        MetricsRegistry(),
    )

    response = await application.handle(
        "GET",
        "/health",
    )

    text = response.body.decode("utf-8")

    assert secret not in text
    assert '"detail"' not in text


@pytest.mark.asyncio
async def test_metrics_endpoint_renders_registry():
    runtime, adapter, application = (
        runtime_probe()
    )

    await runtime.start()
    adapter.observe()

    response = await application.handle(
        "GET",
        "/metrics",
    )

    text = response.body.decode("utf-8")

    assert response.status_code == 200
    assert (
        response.content_type
        == "text/plain; version=0.0.4; charset=utf-8"
    )
    assert "af_core_service_state" in text
    assert 'state="running"' in text


@pytest.mark.asyncio
async def test_head_returns_no_body_with_get_length():
    runtime = ServiceRuntime()

    health = HealthRegistry(
        ServiceRuntimeHealthAdapter(
            runtime
        ).checks(),
        clock=lambda: 1000.0,
        timer=lambda: 2000.0,
    )

    application = ServiceProbeApplication(
        health,
        MetricsRegistry(),
    )

    get_response = await application.handle(
        "GET",
        "/health",
    )
    head_response = await application.handle(
        "HEAD",
        "/health",
    )

    assert head_response.status_code == (
        get_response.status_code
    )
    assert head_response.content_type == (
        get_response.content_type
    )
    assert head_response.body == b""
    assert head_response.header(
        "content-length"
    ) == str(len(get_response.body))


@pytest.mark.asyncio
async def test_unsupported_method_returns_405():
    _, _, application = runtime_probe()

    response = await application.handle(
        "POST",
        "/health",
    )

    assert response.status_code == 405
    assert response.header("allow") == (
        "GET, HEAD"
    )


@pytest.mark.asyncio
async def test_unknown_path_returns_404():
    _, _, application = runtime_probe()

    response = await application.handle(
        "GET",
        "/unknown",
    )

    payload = json.loads(response.body)

    assert response.status_code == 404
    assert payload == {
        "error": "not_found",
    }


@pytest.mark.asyncio
async def test_probe_responses_disable_caching():
    _, _, application = runtime_probe()

    response = await application.handle(
        "GET",
        "/health",
    )

    assert response.header(
        "cache-control"
    ) == "no-store"

    assert response.header(
        "x-content-type-options"
    ) == "nosniff"


@pytest.mark.asyncio
async def test_asgi_request_is_served():
    _, _, application = runtime_probe()
    sent: list[dict] = []

    async def receive():
        return {
            "type": "http.request",
            "body": b"",
            "more_body": False,
        }

    async def send(event):
        sent.append(event)

    await application(
        {
            "type": "http",
            "method": "GET",
            "path": "/health",
        },
        receive,
        send,
    )

    assert sent[0]["type"] == (
        "http.response.start"
    )
    assert sent[0]["status"] == 503
    assert sent[1]["type"] == (
        "http.response.body"
    )
    assert sent[1]["more_body"] is False


@pytest.mark.asyncio
async def test_asgi_non_http_scope_is_rejected():
    _, _, application = runtime_probe()

    async def receive():
        return {
            "type": "lifespan.startup",
        }

    async def send(event):
        raise AssertionError(
            f"unexpected send: {event}"
        )

    with pytest.raises(
        RuntimeError,
        match="ASGI HTTP",
    ):
        await application(
            {
                "type": "lifespan",
            },
            receive,
            send,
        )
