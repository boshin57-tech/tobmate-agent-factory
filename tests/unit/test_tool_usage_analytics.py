from __future__ import annotations

import asyncio
from datetime import timedelta
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
from af_core.tools.tool_telemetry import (
    InMemoryToolTelemetryStream,
    ToolTelemetryCollector,
    ToolTelemetryEvent,
    ToolTelemetryEventType,
    utc_now,
)
from af_core.tools.tool_usage_analytics import (
    ToolRankingMetric,
    ToolUsageAnalytics,
    ToolUsageAnalyticsBindingError,
    ToolUsageAnalyticsStreamBinding,
)


def usage_event(
    event_id: str,
    *,
    event_type: ToolTelemetryEventType = (
        ToolTelemetryEventType.CALL_SUCCEEDED
    ),
    tool_id: str | None = "tool.echo",
    project_id: str | None = "project-1",
    agent_id: str | None = "agent-1",
    duration_ms: float | None = 10,
    retry_count: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float = 0,
    occurred_at=None,
) -> ToolTelemetryEvent:
    return ToolTelemetryEvent(
        event_id=event_id,
        event_type=event_type,
        tool_id=tool_id,
        project_id=project_id,
        agent_id=agent_id,
        successful=(
            event_type
            is ToolTelemetryEventType
            .CALL_SUCCEEDED
        ),
        duration_ms=duration_ms,
        retry_count=retry_count,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        occurred_at=occurred_at or utc_now(),
    )


def record_standard_events(
    analytics: ToolUsageAnalytics,
) -> None:
    analytics.record(
        usage_event(
            "success",
            duration_ms=10,
            retry_count=1,
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.01,
        )
    )

    analytics.record(
        usage_event(
            "failed",
            event_type=(
                ToolTelemetryEventType
                .CALL_FAILED
            ),
            duration_ms=20,
            cost_usd=0.02,
        )
    )

    analytics.record(
        usage_event(
            "blocked",
            event_type=(
                ToolTelemetryEventType
                .CALL_BLOCKED
            ),
            duration_ms=None,
        )
    )

    analytics.record(
        usage_event(
            "timeout",
            event_type=(
                ToolTelemetryEventType
                .CALL_TIMED_OUT
            ),
            duration_ms=40,
            retry_count=2,
            cost_usd=0.03,
        )
    )


def test_terminal_events_are_aggregated() -> None:
    analytics = ToolUsageAnalytics()

    record_standard_events(analytics)

    statistics = analytics.get(
        tool_id="tool.echo",
        project_id="project-1",
        agent_id="agent-1",
    )

    assert statistics is not None
    assert statistics.total_calls == 4
    assert statistics.successful_calls == 1
    assert statistics.failed_calls == 1
    assert statistics.blocked_calls == 1
    assert statistics.timed_out_calls == 1
    assert statistics.unsuccessful_calls == 3
    assert statistics.success_rate == 0.25
    assert statistics.failure_rate == 0.75


def test_latency_retry_token_and_cost_are_aggregated() -> None:
    analytics = ToolUsageAnalytics()

    record_standard_events(analytics)

    statistics = analytics.get(
        tool_id="tool.echo",
        project_id="project-1",
        agent_id="agent-1",
    )

    assert statistics is not None
    assert statistics.retry_count == 3
    assert statistics.total_latency_ms == 70
    assert statistics.minimum_latency_ms == 10
    assert statistics.maximum_latency_ms == 40

    # Blocked Event에는 duration이 없지만,
    # total_calls에는 포함됩니다.
    assert statistics.average_latency_ms == 17.5

    assert statistics.input_tokens == 10
    assert statistics.output_tokens == 5
    assert statistics.total_cost_usd == (
        Decimal("0.06")
    )
    assert statistics.average_cost_usd == (
        Decimal("0.015")
    )


def test_non_terminal_and_missing_tool_events_are_ignored() -> None:
    analytics = ToolUsageAnalytics()

    requested = analytics.record(
        usage_event(
            "requested",
            event_type=(
                ToolTelemetryEventType
                .CALL_REQUESTED
            ),
        )
    )

    missing_tool = analytics.record(
        usage_event(
            "missing-tool",
            tool_id=None,
        )
    )

    assert requested is False
    assert missing_tool is False
    assert analytics.event_count() == 0
    assert analytics.snapshot().total_calls == 0


def test_statistics_are_partitioned_by_tool_project_agent() -> None:
    analytics = ToolUsageAnalytics()

    analytics.record(
        usage_event(
            "one",
            tool_id="tool.alpha",
            project_id="project-1",
            agent_id="agent-1",
        )
    )
    analytics.record(
        usage_event(
            "two",
            tool_id="tool.alpha",
            project_id="project-2",
            agent_id="agent-2",
        )
    )
    analytics.record(
        usage_event(
            "three",
            tool_id="tool.beta",
            project_id="project-1",
            agent_id="agent-1",
        )
    )

    assert len(
        analytics.tool_statistics(
            "tool.alpha"
        )
    ) == 2

    assert len(
        analytics.project_statistics(
            "project-1"
        )
    ) == 2

    assert len(
        analytics.agent_statistics(
            "agent-1"
        )
    ) == 2

    assert analytics.snapshot().tool_count == 3


def test_stream_binding_aggregates_terminal_events_in_real_time() -> None:
    stream = InMemoryToolTelemetryStream()
    analytics = ToolUsageAnalytics()

    binding = ToolUsageAnalyticsStreamBinding(
        analytics=analytics,
        stream=stream,
        subscriber_id="analytics",
    )

    binding.attach()

    async def publish() -> None:
        await stream.publish(
            usage_event(
                "requested",
                event_type=(
                    ToolTelemetryEventType
                    .CALL_REQUESTED
                ),
            )
        )

        await stream.publish(
            usage_event(
                "success",
                duration_ms=12,
                retry_count=1,
                input_tokens=8,
                output_tokens=4,
                cost_usd=0.02,
            )
        )

        await stream.publish(
            usage_event(
                "failed",
                event_type=(
                    ToolTelemetryEventType
                    .CALL_FAILED
                ),
                duration_ms=18,
                cost_usd=0.01,
            )
        )

    asyncio.run(publish())

    statistics = analytics.get(
        tool_id="tool.echo",
        project_id="project-1",
        agent_id="agent-1",
    )

    assert statistics is not None
    assert statistics.total_calls == 2
    assert statistics.successful_calls == 1
    assert statistics.failed_calls == 1
    assert statistics.retry_count == 1
    assert statistics.total_latency_ms == 30
    assert statistics.input_tokens == 8
    assert statistics.output_tokens == 4
    assert statistics.total_cost_usd == (
        Decimal("0.03")
    )

    assert binding.counters() == {
        "received_events": 3,
        "accepted_events": 2,
        "ignored_events": 1,
    }

    assert binding.attached is True
    assert stream.subscriber_ids() == [
        "analytics",
    ]


def test_detach_stops_real_time_aggregation() -> None:
    stream = InMemoryToolTelemetryStream()
    analytics = ToolUsageAnalytics()

    binding = ToolUsageAnalyticsStreamBinding(
        analytics=analytics,
        stream=stream,
    )

    binding.attach()

    asyncio.run(
        stream.publish(
            usage_event("before-detach")
        )
    )

    binding.detach()

    asyncio.run(
        stream.publish(
            usage_event("after-detach")
        )
    )

    statistics = analytics.get(
        tool_id="tool.echo",
        project_id="project-1",
        agent_id="agent-1",
    )

    assert statistics is not None
    assert statistics.total_calls == 1

    assert binding.attached is False
    assert binding.counters() == {
        "received_events": 1,
        "accepted_events": 1,
        "ignored_events": 0,
    }
    assert stream.subscriber_ids() == []


def test_binding_rejects_duplicate_attach_and_detach() -> None:
    stream = InMemoryToolTelemetryStream()
    analytics = ToolUsageAnalytics()

    binding = ToolUsageAnalyticsStreamBinding(
        analytics=analytics,
        stream=stream,
    )

    binding.attach()

    with pytest.raises(
        ToolUsageAnalyticsBindingError,
        match="already attached",
    ):
        binding.attach()

    binding.detach()

    with pytest.raises(
        ToolUsageAnalyticsBindingError,
        match="not attached",
    ):
        binding.detach()


def test_rollups_merge_tool_project_and_agent_statistics() -> None:
    analytics = ToolUsageAnalytics()

    analytics.record(
        usage_event(
            "alpha-p1-a1",
            tool_id="tool.alpha",
            project_id="project-1",
            agent_id="agent-1",
            duration_ms=10,
            cost_usd=0.01,
        )
    )
    analytics.record(
        usage_event(
            "alpha-p2-a2",
            tool_id="tool.alpha",
            project_id="project-2",
            agent_id="agent-2",
            duration_ms=20,
            retry_count=1,
            cost_usd=0.02,
        )
    )
    analytics.record(
        usage_event(
            "beta-p1-a1",
            tool_id="tool.beta",
            project_id="project-1",
            agent_id="agent-1",
            event_type=(
                ToolTelemetryEventType
                .CALL_FAILED
            ),
            duration_ms=30,
            cost_usd=0.03,
        )
    )

    tool_rollups = {
        item.group_id: item.statistics
        for item in analytics.tool_rollups()
    }

    assert set(tool_rollups) == {
        "tool.alpha",
        "tool.beta",
    }

    alpha = tool_rollups["tool.alpha"]

    assert alpha.total_calls == 2
    assert alpha.successful_calls == 2
    assert alpha.retry_count == 1
    assert alpha.average_latency_ms == 15
    assert alpha.total_cost_usd == (
        Decimal("0.03")
    )

    project_rollups = {
        item.group_id: item.statistics
        for item in analytics.project_rollups()
    }

    assert project_rollups[
        "project-1"
    ].total_calls == 2

    assert project_rollups[
        "project-2"
    ].total_calls == 1

    agent_rollups = {
        item.group_id: item.statistics
        for item in analytics.agent_rollups()
    }

    assert agent_rollups[
        "agent-1"
    ].total_calls == 2

    assert agent_rollups[
        "agent-2"
    ].total_calls == 1


def test_tool_ranking_supports_all_metrics() -> None:
    analytics = ToolUsageAnalytics()

    analytics.record(
        usage_event(
            "alpha-1",
            tool_id="tool.alpha",
            duration_ms=20,
            retry_count=2,
            cost_usd=0.03,
        )
    )
    analytics.record(
        usage_event(
            "alpha-2",
            tool_id="tool.alpha",
            duration_ms=40,
            cost_usd=0.02,
        )
    )
    analytics.record(
        usage_event(
            "beta-1",
            tool_id="tool.beta",
            duration_ms=10,
            cost_usd=0.01,
        )
    )

    calls = analytics.top_tools(
        metric=ToolRankingMetric.CALL_COUNT
    )
    assert calls[0].statistics.key.tool_id == (
        "tool.alpha"
    )
    assert calls[0].score == 2

    retries = analytics.top_tools(
        metric=ToolRankingMetric.RETRY_COUNT
    )
    assert retries[0].statistics.key.tool_id == (
        "tool.alpha"
    )
    assert retries[0].score == 2

    cost = analytics.top_tools(
        metric=ToolRankingMetric.TOTAL_COST
    )
    assert cost[0].statistics.key.tool_id == (
        "tool.alpha"
    )

    latency = analytics.top_tools(
        metric=(
            ToolRankingMetric.AVERAGE_LATENCY
        )
    )

    # Latency 기본 Ranking은 낮은 값이 우선입니다.
    assert latency[0].statistics.key.tool_id == (
        "tool.beta"
    )
    assert latency[0].score == 10

    success = analytics.top_tools(
        metric=ToolRankingMetric.SUCCESS_RATE
    )
    assert success[0].score == 1

    with pytest.raises(
        ValueError,
        match="must be positive",
    ):
        analytics.top_tools(
            metric=ToolRankingMetric.CALL_COUNT,
            limit=0,
        )


def test_time_window_comparison_calculates_deltas() -> None:
    analytics = ToolUsageAnalytics()
    now = utc_now()

    analytics.record(
        usage_event(
            "previous",
            tool_id="tool.echo",
            duration_ms=10,
            retry_count=0,
            cost_usd=0.01,
            occurred_at=now,
        )
    )

    analytics.record(
        usage_event(
            "current-success",
            tool_id="tool.echo",
            duration_ms=20,
            retry_count=1,
            cost_usd=0.02,
            occurred_at=(
                now + timedelta(minutes=10)
            ),
        )
    )

    analytics.record(
        usage_event(
            "current-failed",
            tool_id="tool.echo",
            event_type=(
                ToolTelemetryEventType
                .CALL_FAILED
            ),
            duration_ms=40,
            retry_count=2,
            cost_usd=0.03,
            occurred_at=(
                now + timedelta(minutes=11)
            ),
        )
    )

    comparison = analytics.compare_windows(
        previous_start=(
            now - timedelta(seconds=1)
        ),
        previous_end=(
            now + timedelta(seconds=1)
        ),
        current_start=(
            now + timedelta(minutes=9)
        ),
        current_end=(
            now + timedelta(minutes=12)
        ),
        tool_id="tool.echo",
    )

    assert comparison.previous.total_calls == 1
    assert comparison.current.total_calls == 2

    assert comparison.call_count_change == 1
    assert comparison.success_rate_change == (
        -0.5
    )
    assert (
        comparison.average_latency_change_ms
        == 20
    )
    assert comparison.retry_count_change == 3
    assert comparison.total_cost_change_usd == (
        Decimal("0.04")
    )

    with pytest.raises(
        ValueError,
        match="Current window start",
    ):
        analytics.compare_windows(
            current_start=now,
            current_end=(
                now - timedelta(seconds=1)
            ),
            previous_start=now,
            previous_end=now,
        )


def test_report_contains_snapshot_rollups_and_rankings() -> None:
    analytics = ToolUsageAnalytics()

    analytics.record(
        usage_event(
            "alpha",
            tool_id="tool.alpha",
            project_id="project-1",
            agent_id="agent-1",
            cost_usd=0.01,
        )
    )
    analytics.record(
        usage_event(
            "beta",
            tool_id="tool.beta",
            project_id="project-2",
            agent_id="agent-2",
            event_type=(
                ToolTelemetryEventType
                .CALL_FAILED
            ),
            cost_usd=0.02,
        )
    )

    report = analytics.report(
        ranking_limit=1
    )

    assert report.snapshot.total_calls == 2
    assert report.snapshot.tool_count == 2
    assert len(report.tool_rollups) == 2
    assert len(report.project_rollups) == 2
    assert len(report.agent_rollups) == 2

    assert set(report.rankings) == set(
        ToolRankingMetric
    )

    assert all(
        len(items) == 1
        for items in report.rankings.values()
    )

    call_ranking = report.rankings[
        ToolRankingMetric.CALL_COUNT
    ]

    assert call_ranking[0].rank == 1
    assert call_ranking[0].metric is (
        ToolRankingMetric.CALL_COUNT
    )


def test_tool_runtime_stream_analytics_e2e() -> None:
    registry = ExternalToolRegistry()

    async def handler(
        call: ExternalToolCall,
    ) -> ExternalToolResult:
        return ExternalToolResult(
            call_id=call.call_id,
            tool_id=call.tool_id,
            status=ToolExecutionStatus.SUCCEEDED,
        )

    registry.register(
        descriptor=ExternalToolDescriptor(
            tool_id="tool.e2e",
            name="e2e",
            description="E2E analytics Tool",
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
        stream=stream,
        event_prefix="e2e-event",
    )
    analytics = ToolUsageAnalytics()

    binding = ToolUsageAnalyticsStreamBinding(
        analytics=analytics,
        stream=stream,
        subscriber_id="analytics-e2e",
    )
    binding.attach()

    runtime = ToolCallRuntime(
        registry=registry,
        telemetry_collector=collector,
    )

    record = asyncio.run(
        runtime.execute_one(
            NormalizedToolCall(
                call_id="call-e2e",
                tool_name="e2e",
                arguments={},
            ),
            project_id="project-e2e",
            run_id="run-e2e",
            task_id="task-e2e",
            agent_name="agent-e2e",
        )
    )

    assert record.successful is True

    statistics = analytics.get(
        tool_id="tool.e2e",
        project_id="project-e2e",
        agent_id="agent-e2e",
    )

    assert statistics is not None
    assert statistics.total_calls == 1
    assert statistics.successful_calls == 1
    assert statistics.failed_calls == 0
    assert statistics.blocked_calls == 0
    assert statistics.timed_out_calls == 0
    assert statistics.retry_count == 0
    assert statistics.total_latency_ms >= 0
    assert statistics.minimum_latency_ms is not None
    assert statistics.maximum_latency_ms is not None
    assert statistics.success_rate == 1
    assert statistics.failure_rate == 0

    assert binding.counters() == {
        "received_events": 3,
        "accepted_events": 1,
        "ignored_events": 2,
    }

    snapshot = analytics.snapshot()

    assert snapshot.total_calls == 1
    assert snapshot.tool_count == 1

    ranking = analytics.top_tools(
        metric=ToolRankingMetric.CALL_COUNT
    )

    assert len(ranking) == 1
    assert ranking[0].statistics.key.tool_id == (
        "tool.e2e"
    )
    assert ranking[0].score == 1

    report = analytics.report()

    assert report.snapshot.total_calls == 1
    assert len(report.tool_rollups) == 1
    assert len(report.project_rollups) == 1
    assert len(report.agent_rollups) == 1

    binding.detach()

    assert stream.subscriber_ids() == []
