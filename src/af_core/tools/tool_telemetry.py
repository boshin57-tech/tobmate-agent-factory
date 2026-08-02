from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ToolTelemetryEventType(StrEnum):
    CALL_REQUESTED = "CALL_REQUESTED"
    CALL_STARTED = "CALL_STARTED"
    CALL_SUCCEEDED = "CALL_SUCCEEDED"
    CALL_FAILED = "CALL_FAILED"
    CALL_BLOCKED = "CALL_BLOCKED"
    CALL_TIMED_OUT = "CALL_TIMED_OUT"
    CALL_CANCELLED = "CALL_CANCELLED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    BUDGET_REJECTED = "BUDGET_REJECTED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    TOOL_PROVISIONED = "TOOL_PROVISIONED"
    TOOL_RELEASED = "TOOL_RELEASED"
    TOOL_INSTALLED = "TOOL_INSTALLED"
    TOOL_QUARANTINED = "TOOL_QUARANTINED"
    TOOL_REVOKED = "TOOL_REVOKED"


class ToolTelemetrySeverity(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ToolTelemetryEvent(BaseModel):
    event_id: str
    event_type: ToolTelemetryEventType
    severity: ToolTelemetrySeverity = (
        ToolTelemetrySeverity.INFO
    )

    tool_id: str | None = None
    call_id: str | None = None
    batch_id: str | None = None
    server_id: str | None = None

    project_id: str | None = None
    run_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    role: str | None = None

    provider_id: str | None = None
    model_id: str | None = None
    transport: str | None = None

    successful: bool | None = None
    duration_ms: float | None = Field(
        default=None,
        ge=0,
    )
    retry_count: int = Field(
        default=0,
        ge=0,
    )

    input_tokens: int = Field(
        default=0,
        ge=0,
    )
    output_tokens: int = Field(
        default=0,
        ge=0,
    )
    cost_usd: float = Field(
        default=0,
        ge=0,
    )

    error_type: str | None = None
    error_message: str | None = None

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )
    occurred_at: datetime = Field(
        default_factory=utc_now
    )


class ToolTelemetryFilter(BaseModel):
    event_types: set[
        ToolTelemetryEventType
    ] = Field(default_factory=set)

    severities: set[
        ToolTelemetrySeverity
    ] = Field(default_factory=set)

    tool_ids: set[str] = Field(
        default_factory=set
    )
    project_ids: set[str] = Field(
        default_factory=set
    )
    agent_ids: set[str] = Field(
        default_factory=set
    )

    successful: bool | None = None
    occurred_after: datetime | None = None
    occurred_before: datetime | None = None


from collections.abc import (
    Awaitable,
    Callable,
)
import inspect


ToolTelemetrySubscriber = Callable[
    [ToolTelemetryEvent],
    None | Awaitable[None],
]


class ToolTelemetryStreamError(RuntimeError):
    """Raised for invalid telemetry stream operations."""


class InMemoryToolTelemetryStream:
    def __init__(
        self,
        *,
        maximum_events: int = 10000,
    ) -> None:
        if maximum_events <= 0:
            raise ValueError(
                "maximum_events must be positive."
            )

        self.maximum_events = maximum_events
        self._events: list[
            ToolTelemetryEvent
        ] = []
        self._subscribers: dict[
            str,
            ToolTelemetrySubscriber,
        ] = {}

    def subscribe(
        self,
        subscriber_id: str,
        handler: ToolTelemetrySubscriber,
    ) -> None:
        subscriber_id = subscriber_id.strip()

        if not subscriber_id:
            raise ToolTelemetryStreamError(
                "Subscriber ID is required."
            )

        if subscriber_id in self._subscribers:
            raise ToolTelemetryStreamError(
                "Telemetry subscriber already exists: "
                f"{subscriber_id}"
            )

        self._subscribers[
            subscriber_id
        ] = handler

    def unsubscribe(
        self,
        subscriber_id: str,
    ) -> None:
        if subscriber_id not in self._subscribers:
            raise ToolTelemetryStreamError(
                "Unknown telemetry subscriber: "
                f"{subscriber_id}"
            )

        del self._subscribers[subscriber_id]

    def subscriber_ids(self) -> list[str]:
        return sorted(self._subscribers)

    async def publish(
        self,
        event: ToolTelemetryEvent,
    ) -> None:
        self._events.append(
            event.model_copy(deep=True)
        )

        overflow = (
            len(self._events)
            - self.maximum_events
        )

        if overflow > 0:
            del self._events[:overflow]

        for subscriber_id in sorted(
            self._subscribers
        ):
            handler = self._subscribers[
                subscriber_id
            ]

            result = handler(
                event.model_copy(deep=True)
            )

            if inspect.isawaitable(result):
                await result

    def publish_nowait(
        self,
        event: ToolTelemetryEvent,
    ) -> None:
        self._events.append(
            event.model_copy(deep=True)
        )

        overflow = (
            len(self._events)
            - self.maximum_events
        )

        if overflow > 0:
            del self._events[:overflow]

        for subscriber_id in sorted(
            self._subscribers
        ):
            handler = self._subscribers[
                subscriber_id
            ]

            result = handler(
                event.model_copy(deep=True)
            )

            if inspect.isawaitable(result):
                close = getattr(result, "close", None)

                if close is not None:
                    close()

                raise ToolTelemetryStreamError(
                    "Async subscriber requires "
                    "publish(), not publish_nowait()."
                )

    def clear(self) -> None:
        self._events.clear()

    def count(self) -> int:
        return len(self._events)

    def list_events(
        self,
        query: ToolTelemetryFilter | None = None,
    ) -> list[ToolTelemetryEvent]:
        if query is None:
            return [
                event.model_copy(deep=True)
                for event in self._events
            ]

        results: list[
            ToolTelemetryEvent
        ] = []

        for event in self._events:
            if (
                query.event_types
                and event.event_type
                not in query.event_types
            ):
                continue

            if (
                query.severities
                and event.severity
                not in query.severities
            ):
                continue

            if (
                query.tool_ids
                and event.tool_id
                not in query.tool_ids
            ):
                continue

            if (
                query.project_ids
                and event.project_id
                not in query.project_ids
            ):
                continue

            if (
                query.agent_ids
                and event.agent_id
                not in query.agent_ids
            ):
                continue

            if (
                query.successful is not None
                and event.successful
                is not query.successful
            ):
                continue

            if (
                query.occurred_after is not None
                and event.occurred_at
                < query.occurred_after
            ):
                continue

            if (
                query.occurred_before is not None
                and event.occurred_at
                > query.occurred_before
            ):
                continue

            results.append(
                event.model_copy(deep=True)
            )

        return results

    def latest(
        self,
        query: ToolTelemetryFilter | None = None,
    ) -> ToolTelemetryEvent | None:
        events = self.list_events(query)

        if not events:
            return None

        return events[-1]

    def event_ids(self) -> list[str]:
        return [
            event.event_id
            for event in self._events
        ]


from itertools import count
from threading import Lock


class ToolTelemetryCollector:
    def __init__(
        self,
        *,
        stream: InMemoryToolTelemetryStream,
        event_prefix: str = "tool-event",
    ) -> None:
        self.stream = stream
        self.event_prefix = event_prefix
        self._counter = count(1)
        self._counter_lock = Lock()

    def next_event_id(self) -> str:
        with self._counter_lock:
            value = next(self._counter)

        return f"{self.event_prefix}-{value}"

    async def emit(
        self,
        *,
        event_type: ToolTelemetryEventType,
        severity: ToolTelemetrySeverity = (
            ToolTelemetrySeverity.INFO
        ),
        tool_id: str | None = None,
        call_id: str | None = None,
        batch_id: str | None = None,
        project_id: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        successful: bool | None = None,
        duration_ms: float | None = None,
        retry_count: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0,
        error: Exception | str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolTelemetryEvent:
        error_type: str | None = None
        error_message: str | None = None

        if isinstance(error, Exception):
            error_type = type(error).__name__
            error_message = str(error)
        elif isinstance(error, str):
            error_type = "RuntimeError"
            error_message = error

        event = ToolTelemetryEvent(
            event_id=self.next_event_id(),
            event_type=event_type,
            severity=severity,
            tool_id=tool_id,
            call_id=call_id,
            batch_id=batch_id,
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            agent_id=agent_id,
            successful=successful,
            duration_ms=duration_ms,
            retry_count=retry_count,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            error_type=error_type,
            error_message=error_message,
            metadata=metadata or {},
        )

        await self.stream.publish(event)

        return event.model_copy(deep=True)

    async def call_requested(
        self,
        *,
        tool_id: str | None,
        call_id: str,
        project_id: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolTelemetryEvent:
        return await self.emit(
            event_type=(
                ToolTelemetryEventType
                .CALL_REQUESTED
            ),
            tool_id=tool_id,
            call_id=call_id,
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            agent_id=agent_id,
            metadata=metadata,
        )

    async def call_started(
        self,
        *,
        tool_id: str,
        call_id: str,
        project_id: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
    ) -> ToolTelemetryEvent:
        return await self.emit(
            event_type=(
                ToolTelemetryEventType.CALL_STARTED
            ),
            tool_id=tool_id,
            call_id=call_id,
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            agent_id=agent_id,
        )

    async def call_succeeded(
        self,
        *,
        tool_id: str,
        call_id: str,
        duration_ms: float,
        project_id: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        retry_count: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> ToolTelemetryEvent:
        return await self.emit(
            event_type=(
                ToolTelemetryEventType
                .CALL_SUCCEEDED
            ),
            tool_id=tool_id,
            call_id=call_id,
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            agent_id=agent_id,
            successful=True,
            duration_ms=duration_ms,
            retry_count=retry_count,
            metadata=metadata,
        )

    async def call_failed(
        self,
        *,
        tool_id: str | None,
        call_id: str,
        error: Exception | str,
        duration_ms: float | None = None,
        project_id: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        retry_count: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> ToolTelemetryEvent:
        return await self.emit(
            event_type=(
                ToolTelemetryEventType.CALL_FAILED
            ),
            severity=ToolTelemetrySeverity.ERROR,
            tool_id=tool_id,
            call_id=call_id,
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            agent_id=agent_id,
            successful=False,
            duration_ms=duration_ms,
            retry_count=retry_count,
            error=error,
            metadata=metadata,
        )

    async def call_timed_out(
        self,
        *,
        tool_id: str,
        call_id: str,
        duration_ms: float,
        project_id: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        retry_count: int = 0,
    ) -> ToolTelemetryEvent:
        return await self.emit(
            event_type=(
                ToolTelemetryEventType
                .CALL_TIMED_OUT
            ),
            severity=ToolTelemetrySeverity.ERROR,
            tool_id=tool_id,
            call_id=call_id,
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            agent_id=agent_id,
            successful=False,
            duration_ms=duration_ms,
            retry_count=retry_count,
            error="Tool Call timed out.",
        )

    async def call_blocked(
        self,
        *,
        tool_id: str | None,
        call_id: str,
        reason: str,
        project_id: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
    ) -> ToolTelemetryEvent:
        return await self.emit(
            event_type=(
                ToolTelemetryEventType.CALL_BLOCKED
            ),
            severity=ToolTelemetrySeverity.WARNING,
            tool_id=tool_id,
            call_id=call_id,
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            agent_id=agent_id,
            successful=False,
            error=reason,
        )
