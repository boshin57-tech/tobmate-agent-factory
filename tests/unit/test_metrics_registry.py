import math
from concurrent.futures import (
    ThreadPoolExecutor,
)

import pytest

from af_core.production.metrics import (
    HistogramPoint,
    MetricsRegistry,
    MetricsRegistryError,
    MetricType,
    ServiceRuntimeMetricsAdapter,
)
from af_core.production.service_runtime import (
    ServiceResource,
    ServiceRuntime,
)


def test_metric_and_label_definitions_are_validated():
    registry = MetricsRegistry(
        maximum_labels=1
    )

    with pytest.raises(
        MetricsRegistryError,
        match="invalid metric name",
    ):
        registry.counter(
            "invalid-name",
            "Invalid metric.",
        )

    with pytest.raises(
        MetricsRegistryError,
        match="must not be empty",
    ):
        registry.counter(
            "valid_name",
            "",
        )

    with pytest.raises(
        MetricsRegistryError,
        match="label limit",
    ):
        registry.counter(
            "too_many_labels",
            "Too many labels.",
            label_names=("a", "b"),
        )

    with pytest.raises(
        MetricsRegistryError,
        match="unique",
    ):
        MetricsRegistry().counter(
            "duplicate_labels",
            "Duplicate labels.",
            label_names=("kind", "kind"),
        )

    with pytest.raises(
        MetricsRegistryError,
        match="invalid metric label",
    ):
        MetricsRegistry().counter(
            "invalid_label",
            "Invalid label.",
            label_names=("bad-label",),
        )


def test_duplicate_metric_is_rejected():
    registry = MetricsRegistry()

    registry.counter(
        "requests_total",
        "Request count.",
    )

    with pytest.raises(
        MetricsRegistryError,
        match="duplicate",
    ):
        registry.gauge(
            "requests_total",
            "Duplicate metric.",
        )


def test_counter_increments():
    counter = MetricsRegistry().counter(
        "jobs_total",
        "Completed jobs.",
        label_names=("status",),
    )

    counter.inc(
        labels={"status": "complete"}
    )
    counter.inc(
        2.5,
        labels={"status": "complete"},
    )

    assert counter.value(
        labels={"status": "complete"}
    ) == 3.5


def test_counter_rejects_invalid_increment():
    counter = MetricsRegistry().counter(
        "events_total",
        "Event count.",
    )

    for invalid in (
        -1,
        math.inf,
        math.nan,
    ):
        with pytest.raises(
            MetricsRegistryError,
            match="non-negative",
        ):
            counter.inc(invalid)


def test_metric_labels_must_match_exactly():
    counter = MetricsRegistry().counter(
        "tasks_total",
        "Task count.",
        label_names=("state",),
    )

    with pytest.raises(
        MetricsRegistryError,
        match="exactly match",
    ):
        counter.inc()

    with pytest.raises(
        MetricsRegistryError,
        match="exactly match",
    ):
        counter.inc(
            labels={
                "state": "ready",
                "extra": "invalid",
            }
        )


def test_metric_cardinality_is_bounded():
    registry = MetricsRegistry(
        maximum_series_per_metric=2
    )
    counter = registry.counter(
        "worker_jobs_total",
        "Worker job count.",
        label_names=("worker",),
    )

    counter.inc(labels={"worker": "a"})
    counter.inc(labels={"worker": "b"})

    with pytest.raises(
        MetricsRegistryError,
        match="cardinality",
    ):
        counter.inc(
            labels={"worker": "c"}
        )


def test_gauge_set_increment_and_decrement():
    gauge = MetricsRegistry().gauge(
        "active_workers",
        "Active worker count.",
    )

    gauge.set(5)
    gauge.inc(2)
    gauge.dec(3)

    assert gauge.value() == 4


def test_gauge_rejects_non_finite_values():
    gauge = MetricsRegistry().gauge(
        "queue_depth",
        "Current queue depth.",
    )

    with pytest.raises(
        MetricsRegistryError,
        match="finite",
    ):
        gauge.set(math.inf)

    with pytest.raises(
        MetricsRegistryError,
        match="finite",
    ):
        gauge.inc(math.nan)


def test_histogram_uses_cumulative_buckets():
    histogram = MetricsRegistry().histogram(
        "request_duration_seconds",
        "Request duration.",
        buckets=(0.1, 0.5, 1.0),
    )

    histogram.observe(0.05)
    histogram.observe(0.7)

    snapshot = histogram.snapshot()
    point = snapshot.points[0]

    assert isinstance(
        point,
        HistogramPoint,
    )
    assert point.count == 2
    assert point.total == pytest.approx(0.75)
    assert point.buckets == (
        (0.1, 1),
        (0.5, 1),
        (1.0, 2),
    )


def test_histogram_rejects_invalid_values():
    registry = MetricsRegistry()

    with pytest.raises(
        MetricsRegistryError,
        match="non-empty and finite",
    ):
        registry.histogram(
            "empty_histogram",
            "Empty histogram.",
            buckets=(),
        )

    histogram = registry.histogram(
        "valid_histogram",
        "Valid histogram.",
        buckets=(1.0,),
    )

    with pytest.raises(
        MetricsRegistryError,
        match="finite",
    ):
        histogram.observe(math.nan)


def test_prometheus_counter_and_gauge_rendering():
    registry = MetricsRegistry()

    counter = registry.counter(
        "requests_total",
        "Processed requests.",
        label_names=("status",),
    )
    gauge = registry.gauge(
        "active_jobs",
        "Active jobs.",
    )

    counter.inc(
        3,
        labels={"status": "ok"},
    )
    gauge.set(2)

    output = registry.render_prometheus()

    assert (
        "# TYPE requests_total counter"
        in output
    )
    assert (
        'requests_total{status="ok"} 3'
        in output
    )
    assert "# TYPE active_jobs gauge" in output
    assert "active_jobs 2" in output


def test_prometheus_histogram_rendering():
    registry = MetricsRegistry()
    histogram = registry.histogram(
        "latency_seconds",
        "Operation latency.",
        buckets=(0.5, 1.0),
        label_names=("operation",),
    )

    histogram.observe(
        0.7,
        labels={"operation": "build"},
    )

    output = registry.render_prometheus()

    assert (
        'latency_seconds_bucket'
        '{operation="build",le="0.5"} 0'
        in output
    )
    assert (
        'latency_seconds_bucket'
        '{operation="build",le="1"} 1'
        in output
    )
    assert (
        'latency_seconds_bucket'
        '{operation="build",le="+Inf"} 1'
        in output
    )
    assert (
        'latency_seconds_count'
        '{operation="build"} 1'
        in output
    )


def test_prometheus_text_escapes_help_and_labels():
    registry = MetricsRegistry()
    counter = registry.counter(
        "escaped_total",
        "Line one\nLine two\\",
        label_names=("value",),
    )

    counter.inc(
        labels={
            "value": 'a"b\nc\\d',
        }
    )

    output = registry.render_prometheus()

    assert "Line one\\nLine two\\\\" in output
    assert '\\"' in output
    assert "\\n" in output
    assert "\\\\d" in output


def test_metric_collection_is_deterministic():
    registry = MetricsRegistry()

    registry.gauge(
        "z_metric",
        "Z metric.",
    ).set(1)

    registry.counter(
        "a_metric",
        "A metric.",
    ).inc()

    snapshots = registry.collect()

    assert tuple(
        snapshot.name
        for snapshot in snapshots
    ) == (
        "a_metric",
        "z_metric",
    )

    assert snapshots[0].metric_type is (
        MetricType.COUNTER
    )
    assert snapshots[1].metric_type is (
        MetricType.GAUGE
    )


def test_counter_is_thread_safe():
    counter = MetricsRegistry().counter(
        "thread_operations_total",
        "Thread operations.",
    )

    def increment_many() -> None:
        for _ in range(1000):
            counter.inc()

    with ThreadPoolExecutor(
        max_workers=4
    ) as executor:
        futures = [
            executor.submit(increment_many)
            for _ in range(4)
        ]

        for future in futures:
            future.result()

    assert counter.value() == 4000


@pytest.mark.asyncio
async def test_service_runtime_metrics_adapter():
    runtime = ServiceRuntime(
        (
            ServiceResource("database"),
            ServiceResource("artifact-store"),
        )
    )
    registry = MetricsRegistry()
    adapter = ServiceRuntimeMetricsAdapter(
        runtime,
        registry,
    )

    adapter.observe()

    assert adapter.state.value(
        labels={"state": "created"}
    ) == 1
    assert adapter.registered_resources.value() == 2
    assert adapter.started_resources.value() == 0

    await runtime.start()
    adapter.observe()

    assert adapter.state.value(
        labels={"state": "running"}
    ) == 1
    assert adapter.started_resources.value() == 2

    runtime.request_shutdown("sigterm")
    adapter.observe()

    assert adapter.shutdown_requested.value() == 1

    await runtime.stop(reason="sigterm")
    adapter.observe()

    assert adapter.state.value(
        labels={"state": "stopped"}
    ) == 1

    assert adapter.state_transitions.value(
        labels={"state": "created"}
    ) == 1
    assert adapter.state_transitions.value(
        labels={"state": "running"}
    ) == 1
    assert adapter.state_transitions.value(
        labels={"state": "stopped"}
    ) == 1
