from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from af_core.tools.tool_anomaly_detection import (
    CallbackToolQuarantineAdapter,
    ToolAnomalyAction,
    ToolAnomalyBaselineRegistry,
    ToolAnomalyBaselineRegistryError,
    ToolAnomalyDetector,
    ToolAnomalyMetric,
    ToolAnomalyMonitor,
    ToolAnomalyMonitorError,
    ToolAnomalyPolicy,
    ToolAnomalyPolicyRegistry,
    ToolAnomalyPolicyRegistryError,
    ToolAnomalyRealtimeBinding,
    ToolAnomalySeverity,
    ToolQuarantineResult,
)
from af_core.tools.tool_telemetry import (
    InMemoryToolTelemetryStream,
    ToolTelemetryEvent,
    ToolTelemetryEventType,
)
from af_core.tools.tool_usage_analytics import (
    ToolAnalyticsKey,
    ToolUsageAnalytics,
    ToolUsageAnalyticsStreamBinding,
    ToolUsageStatistics,
)


def stats(
    *,
    total_calls: int = 100,
    successful_calls: int = 100,
    failed_calls: int = 0,
    blocked_calls: int = 0,
    timed_out_calls: int = 0,
    retry_count: int = 0,
    total_latency_ms: float = 5000,
    total_cost_usd: Decimal = Decimal("1.00"),
) -> ToolUsageStatistics:
    return ToolUsageStatistics(
        key=ToolAnalyticsKey(
            tool_id="tool.echo",
            project_id="project-1",
            agent_id="agent-1",
        ),
        total_calls=total_calls,
        successful_calls=successful_calls,
        failed_calls=failed_calls,
        blocked_calls=blocked_calls,
        timed_out_calls=timed_out_calls,
        retry_count=retry_count,
        total_latency_ms=total_latency_ms,
        total_cost_usd=total_cost_usd,
    )


def anomaly_policy() -> ToolAnomalyPolicy:
    return ToolAnomalyPolicy(
        policy_id="anomaly.default",
        name="Default anomaly policy",
        minimum_sample_size=10,
        absolute_failure_rate=0.10,
        absolute_latency_ms=200,
        absolute_retry_rate=0.20,
        absolute_average_cost_usd=(
            Decimal("0.05")
        ),
        absolute_timeout_rate=0.05,
        absolute_block_rate=0.05,
        warning_score=0.25,
        high_score=1.0,
        critical_score=2.0,
        quarantine_at=(
            ToolAnomalySeverity.HIGH
        ),
    )


def setup_monitor():
    detector = ToolAnomalyDetector()

    baselines = ToolAnomalyBaselineRegistry()
    baselines.register(
        detector.baseline_from_statistics(
            stats()
        )
    )

    policies = ToolAnomalyPolicyRegistry()
    policies.register(
        anomaly_policy(),
        make_default=True,
    )

    monitor = ToolAnomalyMonitor(
        policies=policies,
        baselines=baselines,
        detector=detector,
    )

    return (
        detector,
        baselines,
        policies,
        monitor,
    )


def test_baseline_builder_calculates_rates() -> None:
    detector = ToolAnomalyDetector()

    baseline = detector.baseline_from_statistics(
        stats(
            successful_calls=90,
            failed_calls=4,
            blocked_calls=2,
            timed_out_calls=4,
            retry_count=20,
        )
    )

    assert baseline.sample_size == 100
    assert baseline.failure_rate == 0.10
    assert baseline.retry_rate == 0.20
    assert baseline.timeout_rate == 0.04
    assert baseline.block_rate == 0.02


def test_detector_identifies_multiple_anomalies() -> None:
    detector = ToolAnomalyDetector()

    baseline = detector.baseline_from_statistics(
        stats()
    )

    evaluation = detector.evaluate(
        statistics=stats(
            successful_calls=60,
            failed_calls=20,
            blocked_calls=5,
            timed_out_calls=15,
            retry_count=50,
            total_latency_ms=50000,
            total_cost_usd=Decimal("10.00"),
        ),
        baseline=baseline,
        policy=anomaly_policy(),
    )

    assert evaluation.anomalous is True
    assert evaluation.recommended_action is (
        ToolAnomalyAction.QUARANTINE
    )

    metrics = {
        signal.metric
        for signal in evaluation.signals
    }

    assert {
        ToolAnomalyMetric.FAILURE_RATE,
        ToolAnomalyMetric.LATENCY,
        ToolAnomalyMetric.RETRY_RATE,
        ToolAnomalyMetric.COST,
        ToolAnomalyMetric.TIMEOUT_RATE,
        ToolAnomalyMetric.BLOCK_RATE,
    }.issubset(metrics)


def test_minimum_sample_is_not_anomalous() -> None:
    detector = ToolAnomalyDetector()

    baseline = detector.baseline_from_statistics(
        stats()
    )

    evaluation = detector.evaluate(
        statistics=stats(
            total_calls=2,
            successful_calls=0,
            failed_calls=2,
            total_latency_ms=2000,
        ),
        baseline=baseline,
        policy=anomaly_policy(),
    )

    assert evaluation.anomalous is False
    assert evaluation.severity is (
        ToolAnomalySeverity.INFO
    )
    assert evaluation.recommended_action is (
        ToolAnomalyAction.OBSERVE
    )


def test_policy_and_baseline_registries() -> None:
    detector = ToolAnomalyDetector()

    baseline = detector.baseline_from_statistics(
        stats()
    )

    baselines = ToolAnomalyBaselineRegistry()
    baselines.register(baseline)

    with pytest.raises(
        ToolAnomalyBaselineRegistryError,
        match="already exists",
    ):
        baselines.register(baseline)

    policies = ToolAnomalyPolicyRegistry()
    policies.register(
        anomaly_policy(),
        make_default=True,
    )

    with pytest.raises(
        ToolAnomalyPolicyRegistryError,
        match="already registered",
    ):
        policies.register(anomaly_policy())

    assert policies.policy_for_tool(
        "tool.echo"
    ).policy_id == "anomaly.default"


def test_monitor_records_latest_and_history() -> None:
    (
        detector,
        baselines,
        policies,
        monitor,
    ) = setup_monitor()

    del detector, baselines, policies

    evaluation = monitor.evaluate_statistics(
        stats(
            successful_calls=60,
            failed_calls=40,
            total_latency_ms=40000,
        ),
        triggered_by_event_id="event-1",
    )

    assert evaluation.anomalous is True
    assert monitor.history_count() == 1

    latest = monitor.latest(
        tool_id="tool.echo",
        project_id="project-1",
        agent_id="agent-1",
    )

    assert latest is not None
    assert latest.anomalous is True

    history = monitor.history(
        anomalous_only=True
    )

    assert len(history) == 1
    assert history[0].triggered_by_event_id == (
        "event-1"
    )


def test_monitor_requires_existing_baseline() -> None:
    policies = ToolAnomalyPolicyRegistry()
    policies.register(
        anomaly_policy(),
        make_default=True,
    )

    monitor = ToolAnomalyMonitor(
        policies=policies,
        baselines=ToolAnomalyBaselineRegistry(),
    )

    with pytest.raises(
        ToolAnomalyMonitorError,
        match="No anomaly baseline",
    ):
        monitor.evaluate_statistics(stats())


def test_realtime_binding_triggers_quarantine_once() -> None:
    stream = InMemoryToolTelemetryStream()
    analytics = ToolUsageAnalytics()

    analytics_binding = (
        ToolUsageAnalyticsStreamBinding(
            analytics=analytics,
            stream=stream,
            subscriber_id="01-analytics",
        )
    )
    analytics_binding.attach()

    (
        detector,
        baselines,
        policies,
        monitor,
    ) = setup_monitor()

    del detector, baselines, policies

    quarantine_calls = []

    async def quarantine_handler(
        tool_id,
        reason,
        evaluation,
    ):
        quarantine_calls.append(
            (
                tool_id,
                reason,
                evaluation.severity,
            )
        )

        return ToolQuarantineResult(
            tool_id=tool_id,
            requested=True,
            successful=True,
            request_id="request-1",
            lifecycle_state="QUARANTINED",
        )

    alerts = []

    binding = ToolAnomalyRealtimeBinding(
        analytics=analytics,
        monitor=monitor,
        stream=stream,
        quarantine_adapter=(
            CallbackToolQuarantineAdapter(
                quarantine_handler
            )
        ),
        subscriber_id="03-anomaly",
    )

    binding.subscribe(
        "collector",
        alerts.append,
    )
    binding.attach()

    async def publish() -> None:
        for index in range(10):
            await stream.publish(
                ToolTelemetryEvent(
                    event_id=f"failure-{index}",
                    event_type=(
                        ToolTelemetryEventType
                        .CALL_FAILED
                    ),
                    tool_id="tool.echo",
                    project_id="project-1",
                    agent_id="agent-1",
                    successful=False,
                    duration_ms=500,
                    retry_count=2,
                    cost_usd=0.10,
                )
            )

    asyncio.run(publish())

    assert quarantine_calls
    assert len(quarantine_calls) == 1
    assert alerts

    assert binding.counters()[
        "quarantine_attempts"
    ] == 1
    assert binding.counters()[
        "quarantine_successes"
    ] == 1

    binding.detach()
    analytics_binding.detach()
