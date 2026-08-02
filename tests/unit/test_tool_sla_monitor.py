from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from af_core.runtime.tool_call_models import (
    NormalizedToolCall,
)
from af_core.runtime.tool_call_runtime import (
    ToolCallRuntime,
)
from af_core.tools.models import (
    ExternalToolCall,
    ExternalToolDescriptor,
    ExternalToolResult,
    ExternalToolRisk,
    ToolExecutionStatus,
)
from af_core.tools.registry import (
    ExternalToolRegistry,
)
from af_core.tools.tool_sla_monitor import (
    ToolSLAChangeType,
    ToolSLAEvaluator,
    ToolSLAMonitor,
    ToolSLAPolicy,
    ToolSLAPolicyRegistry,
    ToolSLAPolicyRegistryError,
    ToolSLARealtimeBinding,
    ToolSLARealtimeBindingError,
    ToolSLAStatus,
    ToolSLABreachType,
)
from af_core.tools.tool_telemetry import (
    InMemoryToolTelemetryStream,
    ToolTelemetryCollector,
    ToolTelemetryEvent,
    ToolTelemetryEventType,
)
from af_core.tools.tool_usage_analytics import (
    ToolAnalyticsKey,
    ToolUsageAnalytics,
    ToolUsageAnalyticsStreamBinding,
    ToolUsageSnapshot,
    ToolUsageStatistics,
)


def policy(
    *,
    policy_id: str = "sla.default",
    minimum_sample_size: int = 1,
    minimum_availability: float = 0.95,
    minimum_success_rate: float = 0.90,
    maximum_average_latency_ms: (
        float | None
    ) = 500,
    maximum_latency_ms: (
        float | None
    ) = 1000,
    maximum_timeout_rate: (
        float | None
    ) = 0.10,
    maximum_retry_rate: (
        float | None
    ) = 0.50,
    maximum_average_cost_usd: (
        Decimal | None
    ) = Decimal("0.10"),
    error_budget_ratio: float = 0.10,
    warning_threshold_ratio: float = 0.80,
) -> ToolSLAPolicy:
    return ToolSLAPolicy(
        policy_id=policy_id,
        name=policy_id,
        minimum_sample_size=(
            minimum_sample_size
        ),
        minimum_availability=(
            minimum_availability
        ),
        minimum_success_rate=(
            minimum_success_rate
        ),
        maximum_average_latency_ms=(
            maximum_average_latency_ms
        ),
        maximum_latency_ms=(
            maximum_latency_ms
        ),
        maximum_timeout_rate=(
            maximum_timeout_rate
        ),
        maximum_retry_rate=(
            maximum_retry_rate
        ),
        maximum_average_cost_usd=(
            maximum_average_cost_usd
        ),
        error_budget_ratio=(
            error_budget_ratio
        ),
        warning_threshold_ratio=(
            warning_threshold_ratio
        ),
    )


def statistics(
    *,
    tool_id: str = "tool.echo",
    project_id: str | None = "project-1",
    agent_id: str | None = "agent-1",
    total_calls: int = 10,
    successful_calls: int = 10,
    failed_calls: int = 0,
    blocked_calls: int = 0,
    timed_out_calls: int = 0,
    retry_count: int = 0,
    total_latency_ms: float = 1000,
    maximum_latency_ms: float | None = 200,
    total_cost_usd: Decimal = Decimal("0.10"),
) -> ToolUsageStatistics:
    return ToolUsageStatistics(
        key=ToolAnalyticsKey(
            tool_id=tool_id,
            project_id=project_id,
            agent_id=agent_id,
        ),
        total_calls=total_calls,
        successful_calls=successful_calls,
        failed_calls=failed_calls,
        blocked_calls=blocked_calls,
        timed_out_calls=timed_out_calls,
        retry_count=retry_count,
        total_latency_ms=total_latency_ms,
        minimum_latency_ms=(
            0
            if total_calls > 0
            else None
        ),
        maximum_latency_ms=(
            maximum_latency_ms
        ),
        total_cost_usd=total_cost_usd,
    )


def policy_registry(
    *,
    default_policy: ToolSLAPolicy | None = None,
) -> ToolSLAPolicyRegistry:
    registry = ToolSLAPolicyRegistry()

    registry.register(
        default_policy or policy(),
        make_default=True,
    )

    return registry


def test_healthy_statistics_pass_all_sla_metrics() -> None:
    evaluation = ToolSLAEvaluator().evaluate(
        statistics=statistics(),
        policy=policy(),
    )

    assert evaluation.status is (
        ToolSLAStatus.HEALTHY
    )
    assert evaluation.healthy is True
    assert evaluation.breached is False
    assert evaluation.availability == 1
    assert evaluation.success_rate == 1
    assert evaluation.timeout_rate == 0
    assert evaluation.retry_rate == 0
    assert evaluation.average_latency_ms == 100
    assert evaluation.average_cost_usd == (
        Decimal("0.01")
    )
    assert evaluation.breaches == []
    assert evaluation.error_budget.exhausted is False


def test_insufficient_sample_returns_insufficient_data() -> None:
    evaluation = ToolSLAEvaluator().evaluate(
        statistics=statistics(
            total_calls=2,
            successful_calls=2,
            total_latency_ms=100,
        ),
        policy=policy(
            minimum_sample_size=5
        ),
    )

    assert evaluation.status is (
        ToolSLAStatus.INSUFFICIENT_DATA
    )
    assert evaluation.sample_size == 2
    assert evaluation.breaches == []


def test_all_sla_dimensions_can_breach() -> None:
    evaluation = ToolSLAEvaluator().evaluate(
        statistics=statistics(
            total_calls=100,
            successful_calls=80,
            failed_calls=10,
            blocked_calls=4,
            timed_out_calls=6,
            retry_count=40,
            total_latency_ms=60000,
            maximum_latency_ms=2000,
            total_cost_usd=Decimal("5.00"),
        ),
        policy=policy(
            minimum_availability=0.99,
            minimum_success_rate=0.98,
            maximum_average_latency_ms=300,
            maximum_latency_ms=1000,
            maximum_timeout_rate=0.02,
            maximum_retry_rate=0.20,
            maximum_average_cost_usd=(
                Decimal("0.03")
            ),
            error_budget_ratio=0.02,
        ),
    )

    assert evaluation.status is (
        ToolSLAStatus.BREACHED
    )
    assert evaluation.availability == 0.90
    assert evaluation.success_rate == 0.80
    assert evaluation.timeout_rate == 0.06
    assert evaluation.retry_rate == 0.40
    assert evaluation.error_budget.exhausted is True

    breach_types = {
        item.breach_type
        for item in evaluation.breaches
        if not item.warning
    }

    assert {
        ToolSLABreachType.AVAILABILITY,
        ToolSLABreachType.SUCCESS_RATE,
        ToolSLABreachType.LATENCY,
        ToolSLABreachType.TIMEOUT_RATE,
        ToolSLABreachType.RETRY_RATE,
        ToolSLABreachType.COST,
        ToolSLABreachType.ERROR_BUDGET,
    }.issubset(breach_types)


def test_warning_metrics_produce_warning_status() -> None:
    evaluation = ToolSLAEvaluator().evaluate(
        statistics=statistics(
            total_calls=10,
            successful_calls=10,
            retry_count=4,
            total_latency_ms=4000,
            maximum_latency_ms=800,
            total_cost_usd=Decimal("0.80"),
        ),
        policy=policy(
            minimum_availability=0.90,
            minimum_success_rate=0.90,
            maximum_average_latency_ms=500,
            maximum_latency_ms=1000,
            maximum_retry_rate=0.50,
            maximum_average_cost_usd=(
                Decimal("0.10")
            ),
            error_budget_ratio=0.20,
            warning_threshold_ratio=0.80,
        ),
    )

    assert evaluation.status is (
        ToolSLAStatus.WARNING
    )
    assert evaluation.breached is False
    assert evaluation.breaches
    assert all(
        item.warning
        for item in evaluation.breaches
    )


def test_policy_registry_selects_tool_binding_before_default() -> None:
    registry = policy_registry()

    strict = policy(
        policy_id="sla.strict",
        minimum_availability=0.99,
    )
    registry.register(strict)

    registry.bind_tool(
        tool_id="tool.critical",
        policy_id="sla.strict",
    )

    assert registry.policy_for_tool(
        "tool.normal"
    ).policy_id == "sla.default"

    assert registry.policy_for_tool(
        "tool.critical"
    ).policy_id == "sla.strict"

    registry.unbind_tool("tool.critical")

    assert registry.policy_for_tool(
        "tool.critical"
    ).policy_id == "sla.default"


def test_registry_blocks_duplicate_unknown_and_bound_removal() -> None:
    registry = policy_registry()

    with pytest.raises(
        ToolSLAPolicyRegistryError,
        match="already registered",
    ):
        registry.register(policy())

    with pytest.raises(
        ToolSLAPolicyRegistryError,
        match="Unknown SLA policy",
    ):
        registry.bind_tool(
            tool_id="tool.echo",
            policy_id="sla.missing",
        )

    strict = policy(
        policy_id="sla.strict"
    )
    registry.register(strict)
    registry.bind_tool(
        tool_id="tool.echo",
        policy_id="sla.strict",
    )

    with pytest.raises(
        ToolSLAPolicyRegistryError,
        match="bound to",
    ):
        registry.unregister("sla.strict")


def test_snapshot_monitor_records_latest_and_history() -> None:
    monitor = ToolSLAMonitor(
        policies=policy_registry(),
        maximum_history=2,
    )

    healthy = statistics()

    breached = statistics(
        successful_calls=8,
        failed_calls=2,
        total_latency_ms=6000,
    )

    monitor.evaluate_statistics(healthy)
    monitor.evaluate_statistics(breached)
    monitor.evaluate_statistics(healthy)

    latest = monitor.latest(
        tool_id="tool.echo",
        project_id="project-1",
        agent_id="agent-1",
    )

    assert latest is not None
    assert latest.status is (
        ToolSLAStatus.HEALTHY
    )

    assert monitor.history_count() == 2

    history = monitor.history(
        tool_id="tool.echo"
    )

    assert [
        item.evaluation_id
        for item in history
    ] == [
        "sla-evaluation-2",
        "sla-evaluation-3",
    ]

    breached_history = monitor.history(
        breached_only=True
    )

    assert len(breached_history) == 1
    assert breached_history[0].status is (
        ToolSLAStatus.BREACHED
    )


def test_snapshot_report_supports_multiple_policies() -> None:
    registry = policy_registry()
    registry.register(
        policy(
            policy_id="sla.strict",
            minimum_success_rate=0.99,
        )
    )
    registry.bind_tool(
        tool_id="tool.critical",
        policy_id="sla.strict",
    )

    monitor = ToolSLAMonitor(
        policies=registry
    )

    report = monitor.evaluate_snapshot(
        ToolUsageSnapshot(
            statistics=[
                statistics(
                    tool_id="tool.normal"
                ),
                statistics(
                    tool_id="tool.critical",
                    successful_calls=8,
                    failed_calls=2,
                ),
            ]
        )
    )

    assert report.policy_id == "MULTIPLE"
    assert len(report.evaluations) == 2
    assert report.healthy_count == 1
    assert report.breached_count == 1


def setup_realtime(
    *,
    notify_on_healthy: bool = False,
    suppress_unchanged: bool = True,
):
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

    monitor = ToolSLAMonitor(
        policies=policy_registry(
            default_policy=policy(
                minimum_availability=0.99,
                minimum_success_rate=0.99,
                maximum_average_latency_ms=100,
                error_budget_ratio=0.01,
            )
        )
    )

    sla_binding = ToolSLARealtimeBinding(
        analytics=analytics,
        monitor=monitor,
        stream=stream,
        subscriber_id="02-sla",
        notify_on_healthy=notify_on_healthy,
        suppress_unchanged=suppress_unchanged,
    )

    alerts = []
    sla_binding.subscribe(
        "collector",
        alerts.append,
    )
    sla_binding.attach()

    return (
        stream,
        analytics,
        analytics_binding,
        monitor,
        sla_binding,
        alerts,
    )


def terminal_event(
    event_id: str,
    *,
    event_type: ToolTelemetryEventType,
    duration_ms: float = 10,
) -> ToolTelemetryEvent:
    return ToolTelemetryEvent(
        event_id=event_id,
        event_type=event_type,
        tool_id="tool.echo",
        project_id="project-1",
        agent_id="agent-1",
        successful=(
            event_type is (
                ToolTelemetryEventType
                .CALL_SUCCEEDED
            )
        ),
        duration_ms=duration_ms,
    )


def test_realtime_binding_alerts_when_status_becomes_breached() -> None:
    (
        stream,
        analytics,
        analytics_binding,
        monitor,
        sla_binding,
        alerts,
    ) = setup_realtime()

    del analytics

    async def publish() -> None:
        await stream.publish(
            terminal_event(
                "success",
                event_type=(
                    ToolTelemetryEventType
                    .CALL_SUCCEEDED
                ),
            )
        )
        await stream.publish(
            terminal_event(
                "failed",
                event_type=(
                    ToolTelemetryEventType
                    .CALL_FAILED
                ),
            )
        )

    asyncio.run(publish())

    assert len(alerts) == 1
    assert alerts[0].change_type is (
        ToolSLAChangeType.STATUS_CHANGED
    )
    assert alerts[0].previous_status is (
        ToolSLAStatus.HEALTHY
    )
    assert alerts[0].current_status is (
        ToolSLAStatus.BREACHED
    )
    assert alerts[0].triggered_by_event_id == (
        "failed"
    )

    latest = monitor.latest(
        tool_id="tool.echo",
        project_id="project-1",
        agent_id="agent-1",
    )

    assert latest is not None
    assert latest.status is (
        ToolSLAStatus.BREACHED
    )

    assert sla_binding.counters() == {
        "received_events": 2,
        "evaluated_events": 2,
        "ignored_events": 0,
        "alerts_emitted": 1,
    }

    sla_binding.detach()
    analytics_binding.detach()


def test_realtime_binding_can_notify_initial_healthy_state() -> None:
    (
        stream,
        analytics,
        analytics_binding,
        monitor,
        sla_binding,
        alerts,
    ) = setup_realtime(
        notify_on_healthy=True
    )

    del analytics, monitor

    asyncio.run(
        stream.publish(
            terminal_event(
                "healthy",
                event_type=(
                    ToolTelemetryEventType
                    .CALL_SUCCEEDED
                ),
            )
        )
    )

    assert len(alerts) == 1
    assert alerts[0].change_type is (
        ToolSLAChangeType.INITIAL
    )
    assert alerts[0].current_status is (
        ToolSLAStatus.HEALTHY
    )

    sla_binding.detach()
    analytics_binding.detach()


def test_realtime_binding_ignores_non_terminal_events() -> None:
    (
        stream,
        analytics,
        analytics_binding,
        monitor,
        sla_binding,
        alerts,
    ) = setup_realtime()

    del analytics, monitor

    asyncio.run(
        stream.publish(
            ToolTelemetryEvent(
                event_id="requested",
                event_type=(
                    ToolTelemetryEventType
                    .CALL_REQUESTED
                ),
                tool_id="tool.echo",
            )
        )
    )

    assert alerts == []
    assert sla_binding.counters() == {
        "received_events": 1,
        "evaluated_events": 0,
        "ignored_events": 1,
        "alerts_emitted": 0,
    }

    sla_binding.detach()
    analytics_binding.detach()


def test_realtime_binding_rejects_invalid_lifecycle() -> None:
    stream = InMemoryToolTelemetryStream()
    analytics = ToolUsageAnalytics()
    monitor = ToolSLAMonitor(
        policies=policy_registry()
    )

    binding = ToolSLARealtimeBinding(
        analytics=analytics,
        monitor=monitor,
        stream=stream,
    )

    binding.attach()

    with pytest.raises(
        ToolSLARealtimeBindingError,
        match="already attached",
    ):
        binding.attach()

    binding.detach()

    with pytest.raises(
        ToolSLARealtimeBindingError,
        match="not attached",
    ):
        binding.detach()


def test_tool_runtime_to_realtime_sla_e2e() -> None:
    registry = ExternalToolRegistry()
    calls = 0

    async def handler(
        call: ExternalToolCall,
    ) -> ExternalToolResult:
        nonlocal calls
        calls += 1

        status = (
            ToolExecutionStatus.SUCCEEDED
            if calls == 1
            else ToolExecutionStatus.FAILED
        )

        return ExternalToolResult(
            call_id=call.call_id,
            tool_id=call.tool_id,
            status=status,
            is_error=(
                status is ToolExecutionStatus.FAILED
            ),
            error=(
                "simulated failure"
                if status is (
                    ToolExecutionStatus.FAILED
                )
                else None
            ),
        )

    registry.register(
        descriptor=ExternalToolDescriptor(
            tool_id="tool.sla-e2e",
            name="sla_e2e",
            description="SLA E2E Tool",
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            risk=ExternalToolRisk.READ_ONLY,
        ),
        handler=handler,
    )

    stream = InMemoryToolTelemetryStream()
    collector = ToolTelemetryCollector(
        stream=stream
    )
    analytics = ToolUsageAnalytics()

    analytics_binding = (
        ToolUsageAnalyticsStreamBinding(
            analytics=analytics,
            stream=stream,
            subscriber_id="01-analytics",
        )
    )
    analytics_binding.attach()

    monitor = ToolSLAMonitor(
        policies=policy_registry(
            default_policy=policy(
                minimum_success_rate=0.99,
                error_budget_ratio=0.01,
            )
        )
    )

    alerts = []

    sla_binding = ToolSLARealtimeBinding(
        analytics=analytics,
        monitor=monitor,
        stream=stream,
        subscriber_id="02-sla",
    )
    sla_binding.subscribe(
        "collector",
        alerts.append,
    )
    sla_binding.attach()

    runtime = ToolCallRuntime(
        registry=registry,
        telemetry_collector=collector,
    )

    first = asyncio.run(
        runtime.execute_one(
            NormalizedToolCall(
                call_id="call-1",
                tool_name="sla_e2e",
                arguments={},
            ),
            project_id="project-e2e",
            agent_name="agent-e2e",
        )
    )

    second = asyncio.run(
        runtime.execute_one(
            NormalizedToolCall(
                call_id="call-2",
                tool_name="sla_e2e",
                arguments={},
            ),
            project_id="project-e2e",
            agent_name="agent-e2e",
        )
    )

    assert first.successful is True
    assert second.successful is False

    usage = analytics.get(
        tool_id="tool.sla-e2e",
        project_id="project-e2e",
        agent_id="agent-e2e",
    )

    assert usage is not None
    assert usage.total_calls == 2
    assert usage.successful_calls == 1
    assert usage.failed_calls == 1

    latest = monitor.latest(
        tool_id="tool.sla-e2e",
        project_id="project-e2e",
        agent_id="agent-e2e",
    )

    assert latest is not None
    assert latest.status is (
        ToolSLAStatus.BREACHED
    )
    assert latest.success_rate == 0.5
    assert latest.error_budget.exhausted is True

    assert len(alerts) == 1
    assert alerts[0].change_type is (
        ToolSLAChangeType.STATUS_CHANGED
    )
    assert alerts[0].current_status is (
        ToolSLAStatus.BREACHED
    )

    sla_binding.detach()
    analytics_binding.detach()
