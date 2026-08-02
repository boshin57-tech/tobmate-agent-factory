from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from af_core.tools.tool_telemetry import (
    InMemoryToolTelemetryStream,
    ToolTelemetryCollector,
    ToolTelemetryEvent,
    ToolTelemetryEventType,
    ToolTelemetryFilter,
    ToolTelemetrySeverity,
    ToolTelemetryStreamError,
    utc_now,
)


def event(
    event_id: str,
    *,
    event_type: ToolTelemetryEventType = (
        ToolTelemetryEventType.CALL_SUCCEEDED
    ),
    severity: ToolTelemetrySeverity = (
        ToolTelemetrySeverity.INFO
    ),
    tool_id: str = "tool.echo",
    project_id: str = "project-1",
    agent_id: str = "agent-1",
    successful: bool | None = True,
) -> ToolTelemetryEvent:
    return ToolTelemetryEvent(
        event_id=event_id,
        event_type=event_type,
        severity=severity,
        tool_id=tool_id,
        project_id=project_id,
        agent_id=agent_id,
        successful=successful,
    )


def test_async_publish_notifies_sync_and_async_subscribers() -> None:
    received_sync: list[str] = []
    received_async: list[str] = []

    async def async_handler(
        value: ToolTelemetryEvent,
    ) -> None:
        received_async.append(value.event_id)

    stream = InMemoryToolTelemetryStream()

    stream.subscribe(
        "sync",
        lambda value: received_sync.append(
            value.event_id
        ),
    )
    stream.subscribe(
        "async",
        async_handler,
    )

    asyncio.run(
        stream.publish(event("event-1"))
    )

    assert received_sync == ["event-1"]
    assert received_async == ["event-1"]
    assert stream.event_ids() == ["event-1"]
    assert stream.subscriber_ids() == [
        "async",
        "sync",
    ]


def test_retention_keeps_only_latest_events() -> None:
    stream = InMemoryToolTelemetryStream(
        maximum_events=3
    )

    async def publish_all() -> None:
        for index in range(5):
            await stream.publish(
                event(f"event-{index}")
            )

    asyncio.run(publish_all())

    assert stream.count() == 3
    assert stream.event_ids() == [
        "event-2",
        "event-3",
        "event-4",
    ]

    stream.clear()

    assert stream.count() == 0
    assert stream.latest() is None


def test_duplicate_and_unknown_subscribers_are_rejected() -> None:
    stream = InMemoryToolTelemetryStream()

    stream.subscribe(
        "collector",
        lambda value: None,
    )

    with pytest.raises(
        ToolTelemetryStreamError,
        match="already exists",
    ):
        stream.subscribe(
            "collector",
            lambda value: None,
        )

    stream.unsubscribe("collector")

    with pytest.raises(
        ToolTelemetryStreamError,
        match="Unknown telemetry subscriber",
    ):
        stream.unsubscribe("collector")


def test_publish_nowait_rejects_async_subscriber() -> None:
    stream = InMemoryToolTelemetryStream()

    async def handler(
        value: ToolTelemetryEvent,
    ) -> None:
        del value

    stream.subscribe("async", handler)

    with pytest.raises(
        ToolTelemetryStreamError,
        match="requires publish",
    ):
        stream.publish_nowait(
            event("event-1")
        )


def test_event_filter_combines_all_constraints() -> None:
    stream = InMemoryToolTelemetryStream()

    now = utc_now()

    values = [
        event(
            "success",
            tool_id="tool.echo",
            project_id="project-1",
            agent_id="agent-1",
            successful=True,
        ),
        event(
            "failed",
            event_type=(
                ToolTelemetryEventType.CALL_FAILED
            ),
            severity=ToolTelemetrySeverity.ERROR,
            tool_id="tool.echo",
            project_id="project-1",
            agent_id="agent-1",
            successful=False,
        ),
        event(
            "other",
            tool_id="tool.other",
            project_id="project-2",
            agent_id="agent-2",
            successful=True,
        ),
    ]

    values[0].occurred_at = now
    values[1].occurred_at = (
        now + timedelta(seconds=1)
    )
    values[2].occurred_at = (
        now + timedelta(seconds=2)
    )

    for value in values:
        stream.publish_nowait(value)

    results = stream.list_events(
        ToolTelemetryFilter(
            event_types={
                ToolTelemetryEventType.CALL_FAILED
            },
            severities={
                ToolTelemetrySeverity.ERROR
            },
            tool_ids={"tool.echo"},
            project_ids={"project-1"},
            agent_ids={"agent-1"},
            successful=False,
            occurred_after=now,
            occurred_before=(
                now + timedelta(seconds=1)
            ),
        )
    )

    assert [
        value.event_id
        for value in results
    ] == ["failed"]


def test_stream_returns_deep_copies() -> None:
    stream = InMemoryToolTelemetryStream()

    original = event("event-copy")
    original.metadata["nested"] = {
        "value": 1,
    }

    stream.publish_nowait(original)

    returned = stream.list_events()
    returned[0].metadata["nested"]["value"] = 99

    stored = stream.latest()

    assert stored is not None
    assert stored.metadata["nested"]["value"] == 1


def test_collector_generates_unique_ids_and_error_fields() -> None:
    stream = InMemoryToolTelemetryStream()
    collector = ToolTelemetryCollector(
        stream=stream,
        event_prefix="test-event",
    )

    async def collect() -> None:
        await collector.call_requested(
            tool_id="tool.echo",
            call_id="call-1",
        )

        await collector.call_failed(
            tool_id="tool.echo",
            call_id="call-1",
            error=ValueError("invalid input"),
            duration_ms=2.5,
            retry_count=2,
        )

    asyncio.run(collect())

    events = stream.list_events()

    assert [
        value.event_id
        for value in events
    ] == [
        "test-event-1",
        "test-event-2",
    ]

    failed = events[-1]

    assert failed.event_type is (
        ToolTelemetryEventType.CALL_FAILED
    )
    assert failed.severity is (
        ToolTelemetrySeverity.ERROR
    )
    assert failed.successful is False
    assert failed.error_type == "ValueError"
    assert failed.error_message == "invalid input"
    assert failed.duration_ms == 2.5
    assert failed.retry_count == 2


def test_invalid_stream_capacity_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="must be positive",
    ):
        InMemoryToolTelemetryStream(
            maximum_events=0
        )
