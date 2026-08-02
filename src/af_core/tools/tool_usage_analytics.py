from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from .tool_telemetry import (
    ToolTelemetryEvent,
    ToolTelemetryEventType,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ToolRankingMetric(StrEnum):
    CALL_COUNT = "CALL_COUNT"
    SUCCESS_RATE = "SUCCESS_RATE"
    AVERAGE_LATENCY = "AVERAGE_LATENCY"
    TOTAL_COST = "TOTAL_COST"
    RETRY_COUNT = "RETRY_COUNT"


class ToolAnalyticsKey(BaseModel):
    tool_id: str
    project_id: str | None = None
    agent_id: str | None = None

    @property
    def identity(self) -> tuple[
        str,
        str | None,
        str | None,
    ]:
        return (
            self.tool_id,
            self.project_id,
            self.agent_id,
        )


class ToolUsageStatistics(BaseModel):
    key: ToolAnalyticsKey

    total_calls: int = Field(default=0, ge=0)
    successful_calls: int = Field(default=0, ge=0)
    failed_calls: int = Field(default=0, ge=0)
    blocked_calls: int = Field(default=0, ge=0)
    timed_out_calls: int = Field(default=0, ge=0)

    retry_count: int = Field(default=0, ge=0)

    total_latency_ms: float = Field(
        default=0,
        ge=0,
    )
    minimum_latency_ms: float | None = Field(
        default=None,
        ge=0,
    )
    maximum_latency_ms: float | None = Field(
        default=None,
        ge=0,
    )

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    total_cost_usd: Decimal = Field(
        default=Decimal("0"),
        ge=0,
    )

    first_event_at: datetime | None = None
    last_event_at: datetime | None = None

    @property
    def unsuccessful_calls(self) -> int:
        return (
            self.failed_calls
            + self.blocked_calls
            + self.timed_out_calls
        )

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 0

        return (
            self.successful_calls
            / self.total_calls
        )

    @property
    def failure_rate(self) -> float:
        if self.total_calls == 0:
            return 0

        return (
            self.unsuccessful_calls
            / self.total_calls
        )

    @property
    def average_latency_ms(self) -> float:
        if self.total_calls == 0:
            return 0

        return (
            self.total_latency_ms
            / self.total_calls
        )

    @property
    def average_cost_usd(self) -> Decimal:
        if self.total_calls == 0:
            return Decimal("0")

        return (
            self.total_cost_usd
            / Decimal(self.total_calls)
        )


class ToolUsageSnapshot(BaseModel):
    statistics: list[
        ToolUsageStatistics
    ] = Field(default_factory=list)

    generated_at: datetime = Field(
        default_factory=utc_now
    )
    window_start: datetime | None = None
    window_end: datetime | None = None

    @property
    def tool_count(self) -> int:
        return len(self.statistics)

    @property
    def total_calls(self) -> int:
        return sum(
            item.total_calls
            for item in self.statistics
        )

    @property
    def total_cost_usd(self) -> Decimal:
        return sum(
            (
                item.total_cost_usd
                for item in self.statistics
            ),
            Decimal("0"),
        )


class ToolUsageRankingItem(BaseModel):
    rank: int = Field(ge=1)
    metric: ToolRankingMetric
    statistics: ToolUsageStatistics
    score: float


class ToolUsageAnalytics:
    _TERMINAL_EVENTS = {
        ToolTelemetryEventType.CALL_SUCCEEDED,
        ToolTelemetryEventType.CALL_FAILED,
        ToolTelemetryEventType.CALL_BLOCKED,
        ToolTelemetryEventType.CALL_TIMED_OUT,
        ToolTelemetryEventType.CALL_CANCELLED,
    }

    def __init__(self) -> None:
        self._statistics: dict[
            tuple[str, str | None, str | None],
            ToolUsageStatistics,
        ] = {}
        self._events: list[
            ToolTelemetryEvent
        ] = []

    def accepts(
        self,
        event: ToolTelemetryEvent,
    ) -> bool:
        return (
            event.tool_id is not None
            and event.event_type
            in self._TERMINAL_EVENTS
        )

    def clear(self) -> None:
        self._statistics.clear()
        self._events.clear()

    def event_count(self) -> int:
        return len(self._events)

    def record(
        self,
        event: ToolTelemetryEvent,
    ) -> bool:
        if not self.accepts(event):
            return False

        assert event.tool_id is not None

        key = ToolAnalyticsKey(
            tool_id=event.tool_id,
            project_id=event.project_id,
            agent_id=event.agent_id,
        )

        identity = key.identity

        statistics = self._statistics.get(
            identity
        )

        if statistics is None:
            statistics = ToolUsageStatistics(
                key=key
            )
            self._statistics[identity] = statistics

        statistics.total_calls += 1

        if event.event_type is (
            ToolTelemetryEventType.CALL_SUCCEEDED
        ):
            statistics.successful_calls += 1

        elif event.event_type is (
            ToolTelemetryEventType.CALL_BLOCKED
        ):
            statistics.blocked_calls += 1

        elif event.event_type is (
            ToolTelemetryEventType.CALL_TIMED_OUT
        ):
            statistics.timed_out_calls += 1

        else:
            statistics.failed_calls += 1

        statistics.retry_count += (
            event.retry_count
        )

        statistics.input_tokens += (
            event.input_tokens
        )
        statistics.output_tokens += (
            event.output_tokens
        )

        statistics.total_cost_usd += Decimal(
            str(event.cost_usd)
        )

        if event.duration_ms is not None:
            statistics.total_latency_ms += (
                event.duration_ms
            )

            if (
                statistics.minimum_latency_ms
                is None
                or event.duration_ms
                < statistics.minimum_latency_ms
            ):
                statistics.minimum_latency_ms = (
                    event.duration_ms
                )

            if (
                statistics.maximum_latency_ms
                is None
                or event.duration_ms
                > statistics.maximum_latency_ms
            ):
                statistics.maximum_latency_ms = (
                    event.duration_ms
                )

        if (
            statistics.first_event_at is None
            or event.occurred_at
            < statistics.first_event_at
        ):
            statistics.first_event_at = (
                event.occurred_at
            )

        if (
            statistics.last_event_at is None
            or event.occurred_at
            > statistics.last_event_at
        ):
            statistics.last_event_at = (
                event.occurred_at
            )

        self._events.append(
            event.model_copy(deep=True)
        )

        return True

    def get(
        self,
        *,
        tool_id: str,
        project_id: str | None = None,
        agent_id: str | None = None,
    ) -> ToolUsageStatistics | None:
        value = self._statistics.get(
            (
                tool_id,
                project_id,
                agent_id,
            )
        )

        if value is None:
            return None

        return value.model_copy(deep=True)

    def list_statistics(
        self,
        *,
        tool_id: str | None = None,
        project_id: str | None = None,
        agent_id: str | None = None,
    ) -> list[ToolUsageStatistics]:
        results: list[
            ToolUsageStatistics
        ] = []

        for statistics in (
            self._statistics.values()
        ):
            key = statistics.key

            if (
                tool_id is not None
                and key.tool_id != tool_id
            ):
                continue

            if (
                project_id is not None
                and key.project_id != project_id
            ):
                continue

            if (
                agent_id is not None
                and key.agent_id != agent_id
            ):
                continue

            results.append(
                statistics.model_copy(
                    deep=True
                )
            )

        return sorted(
            results,
            key=lambda item: (
                item.key.tool_id,
                item.key.project_id or "",
                item.key.agent_id or "",
            ),
        )

    def tool_statistics(
        self,
        tool_id: str,
    ) -> list[ToolUsageStatistics]:
        return self.list_statistics(
            tool_id=tool_id
        )

    def project_statistics(
        self,
        project_id: str,
    ) -> list[ToolUsageStatistics]:
        return self.list_statistics(
            project_id=project_id
        )

    def agent_statistics(
        self,
        agent_id: str,
    ) -> list[ToolUsageStatistics]:
        return self.list_statistics(
            agent_id=agent_id
        )

    def snapshot(
        self,
        *,
        tool_id: str | None = None,
        project_id: str | None = None,
        agent_id: str | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> ToolUsageSnapshot:
        if (
            window_start is None
            and window_end is None
        ):
            statistics = self.list_statistics(
                tool_id=tool_id,
                project_id=project_id,
                agent_id=agent_id,
            )

            return ToolUsageSnapshot(
                statistics=statistics,
                window_start=window_start,
                window_end=window_end,
            )

        temporary = ToolUsageAnalytics()

        for event in self._events:
            if (
                window_start is not None
                and event.occurred_at
                < window_start
            ):
                continue

            if (
                window_end is not None
                and event.occurred_at
                > window_end
            ):
                continue

            if (
                tool_id is not None
                and event.tool_id != tool_id
            ):
                continue

            if (
                project_id is not None
                and event.project_id
                != project_id
            ):
                continue

            if (
                agent_id is not None
                and event.agent_id != agent_id
            ):
                continue

            temporary.record(event)

        return ToolUsageSnapshot(
            statistics=(
                temporary.list_statistics()
            ),
            window_start=window_start,
            window_end=window_end,
        )

    def tool_snapshot(
        self,
        tool_id: str,
        *,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> ToolUsageSnapshot:
        return self.snapshot(
            tool_id=tool_id,
            window_start=window_start,
            window_end=window_end,
        )

    def project_snapshot(
        self,
        project_id: str,
        *,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> ToolUsageSnapshot:
        return self.snapshot(
            project_id=project_id,
            window_start=window_start,
            window_end=window_end,
        )

    def agent_snapshot(
        self,
        agent_id: str,
        *,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> ToolUsageSnapshot:
        return self.snapshot(
            agent_id=agent_id,
            window_start=window_start,
            window_end=window_end,
        )

    def _merge_statistics(
        self,
        values: list[ToolUsageStatistics],
        *,
        key: ToolAnalyticsKey,
    ) -> ToolUsageStatistics:
        merged = ToolUsageStatistics(
            key=key
        )

        for value in values:
            merged.total_calls += (
                value.total_calls
            )
            merged.successful_calls += (
                value.successful_calls
            )
            merged.failed_calls += (
                value.failed_calls
            )
            merged.blocked_calls += (
                value.blocked_calls
            )
            merged.timed_out_calls += (
                value.timed_out_calls
            )
            merged.retry_count += (
                value.retry_count
            )
            merged.total_latency_ms += (
                value.total_latency_ms
            )
            merged.input_tokens += (
                value.input_tokens
            )
            merged.output_tokens += (
                value.output_tokens
            )
            merged.total_cost_usd += (
                value.total_cost_usd
            )

            if value.minimum_latency_ms is not None:
                if (
                    merged.minimum_latency_ms
                    is None
                    or value.minimum_latency_ms
                    < merged.minimum_latency_ms
                ):
                    merged.minimum_latency_ms = (
                        value.minimum_latency_ms
                    )

            if value.maximum_latency_ms is not None:
                if (
                    merged.maximum_latency_ms
                    is None
                    or value.maximum_latency_ms
                    > merged.maximum_latency_ms
                ):
                    merged.maximum_latency_ms = (
                        value.maximum_latency_ms
                    )

            if value.first_event_at is not None:
                if (
                    merged.first_event_at is None
                    or value.first_event_at
                    < merged.first_event_at
                ):
                    merged.first_event_at = (
                        value.first_event_at
                    )

            if value.last_event_at is not None:
                if (
                    merged.last_event_at is None
                    or value.last_event_at
                    > merged.last_event_at
                ):
                    merged.last_event_at = (
                        value.last_event_at
                    )

        return merged

    def tool_rollups(
        self,
        snapshot: ToolUsageSnapshot | None = None,
    ) -> list[ToolUsageRollup]:
        source = (
            snapshot
            or self.snapshot()
        )

        grouped: dict[
            str,
            list[ToolUsageStatistics],
        ] = {}

        for value in source.statistics:
            grouped.setdefault(
                value.key.tool_id,
                [],
            ).append(value)

        return [
            ToolUsageRollup(
                group_by="tool",
                group_id=tool_id,
                statistics=self._merge_statistics(
                    values,
                    key=ToolAnalyticsKey(
                        tool_id=tool_id
                    ),
                ),
            )
            for tool_id, values in sorted(
                grouped.items()
            )
        ]

    def project_rollups(
        self,
        snapshot: ToolUsageSnapshot | None = None,
    ) -> list[ToolUsageRollup]:
        source = snapshot or self.snapshot()

        grouped: dict[
            str,
            list[ToolUsageStatistics],
        ] = {}

        for value in source.statistics:
            project_id = (
                value.key.project_id
                or "unassigned"
            )

            grouped.setdefault(
                project_id,
                [],
            ).append(value)

        return [
            ToolUsageRollup(
                group_by="project",
                group_id=project_id,
                statistics=self._merge_statistics(
                    values,
                    key=ToolAnalyticsKey(
                        tool_id="*",
                        project_id=(
                            None
                            if project_id
                            == "unassigned"
                            else project_id
                        ),
                    ),
                ),
            )
            for project_id, values in sorted(
                grouped.items()
            )
        ]

    def agent_rollups(
        self,
        snapshot: ToolUsageSnapshot | None = None,
    ) -> list[ToolUsageRollup]:
        source = snapshot or self.snapshot()

        grouped: dict[
            str,
            list[ToolUsageStatistics],
        ] = {}

        for value in source.statistics:
            agent_id = (
                value.key.agent_id
                or "unassigned"
            )

            grouped.setdefault(
                agent_id,
                [],
            ).append(value)

        return [
            ToolUsageRollup(
                group_by="agent",
                group_id=agent_id,
                statistics=self._merge_statistics(
                    values,
                    key=ToolAnalyticsKey(
                        tool_id="*",
                        agent_id=(
                            None
                            if agent_id
                            == "unassigned"
                            else agent_id
                        ),
                    ),
                ),
            )
            for agent_id, values in sorted(
                grouped.items()
            )
        ]

    def top_tools(
        self,
        *,
        metric: ToolRankingMetric,
        limit: int = 10,
        descending: bool | None = None,
        snapshot: ToolUsageSnapshot | None = None,
    ) -> list[ToolUsageRankingItem]:
        if limit <= 0:
            raise ValueError(
                "Ranking limit must be positive."
            )

        rollups = self.tool_rollups(snapshot)

        if descending is None:
            descending = metric is not (
                ToolRankingMetric
                .AVERAGE_LATENCY
            )

        scored: list[
            tuple[ToolUsageStatistics, float]
        ] = []

        for rollup in rollups:
            statistics = rollup.statistics

            if metric is (
                ToolRankingMetric.CALL_COUNT
            ):
                score = float(
                    statistics.total_calls
                )

            elif metric is (
                ToolRankingMetric.SUCCESS_RATE
            ):
                score = statistics.success_rate

            elif metric is (
                ToolRankingMetric
                .AVERAGE_LATENCY
            ):
                score = (
                    statistics.average_latency_ms
                )

            elif metric is (
                ToolRankingMetric.TOTAL_COST
            ):
                score = float(
                    statistics.total_cost_usd
                )

            elif metric is (
                ToolRankingMetric.RETRY_COUNT
            ):
                score = float(
                    statistics.retry_count
                )

            else:
                raise ValueError(
                    f"Unsupported ranking metric: "
                    f"{metric}"
                )

            scored.append(
                (
                    statistics,
                    score,
                )
            )

        scored.sort(
            key=lambda item: (
                item[1],
                item[0].key.tool_id,
            ),
            reverse=descending,
        )

        return [
            ToolUsageRankingItem(
                rank=index,
                metric=metric,
                statistics=statistics.model_copy(
                    deep=True
                ),
                score=score,
            )
            for index, (
                statistics,
                score,
            ) in enumerate(
                scored[:limit],
                start=1,
            )
        ]

    def compare_windows(
        self,
        *,
        current_start: datetime,
        current_end: datetime,
        previous_start: datetime,
        previous_end: datetime,
        tool_id: str | None = None,
        project_id: str | None = None,
        agent_id: str | None = None,
    ) -> ToolUsageWindowComparison:
        if current_start > current_end:
            raise ValueError(
                "Current window start must not "
                "be after its end."
            )

        if previous_start > previous_end:
            raise ValueError(
                "Previous window start must not "
                "be after its end."
            )

        current = self.snapshot(
            tool_id=tool_id,
            project_id=project_id,
            agent_id=agent_id,
            window_start=current_start,
            window_end=current_end,
        )

        previous = self.snapshot(
            tool_id=tool_id,
            project_id=project_id,
            agent_id=agent_id,
            window_start=previous_start,
            window_end=previous_end,
        )

        current_total = self._snapshot_total(
            current
        )
        previous_total = self._snapshot_total(
            previous
        )

        return ToolUsageWindowComparison(
            current=current,
            previous=previous,
            call_count_change=(
                current_total.total_calls
                - previous_total.total_calls
            ),
            success_rate_change=(
                current_total.success_rate
                - previous_total.success_rate
            ),
            average_latency_change_ms=(
                current_total.average_latency_ms
                - previous_total.average_latency_ms
            ),
            retry_count_change=(
                current_total.retry_count
                - previous_total.retry_count
            ),
            total_cost_change_usd=(
                current_total.total_cost_usd
                - previous_total.total_cost_usd
            ),
        )

    def _snapshot_total(
        self,
        snapshot: ToolUsageSnapshot,
    ) -> ToolUsageStatistics:
        return self._merge_statistics(
            snapshot.statistics,
            key=ToolAnalyticsKey(
                tool_id="*"
            ),
        )

    def report(
        self,
        *,
        tool_id: str | None = None,
        project_id: str | None = None,
        agent_id: str | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        ranking_limit: int = 10,
    ) -> ToolUsageAnalyticsReport:
        snapshot = self.snapshot(
            tool_id=tool_id,
            project_id=project_id,
            agent_id=agent_id,
            window_start=window_start,
            window_end=window_end,
        )

        rankings = {
            metric: self.top_tools(
                metric=metric,
                limit=ranking_limit,
                snapshot=snapshot,
            )
            for metric in ToolRankingMetric
        }

        return ToolUsageAnalyticsReport(
            snapshot=snapshot,
            tool_rollups=self.tool_rollups(
                snapshot
            ),
            project_rollups=(
                self.project_rollups(snapshot)
            ),
            agent_rollups=self.agent_rollups(
                snapshot
            ),
            rankings=rankings,
        )



from .tool_telemetry import (
    InMemoryToolTelemetryStream,
    ToolTelemetryStreamError,
)


class ToolUsageAnalyticsBindingError(RuntimeError):
    """Raised for invalid Analytics Stream bindings."""


class ToolUsageAnalyticsStreamBinding:
    def __init__(
        self,
        *,
        analytics: ToolUsageAnalytics,
        stream: InMemoryToolTelemetryStream,
        subscriber_id: str = (
            "tool-usage-analytics"
        ),
    ) -> None:
        subscriber_id = subscriber_id.strip()

        if not subscriber_id:
            raise ValueError(
                "subscriber_id is required."
            )

        self.analytics = analytics
        self.stream = stream
        self.subscriber_id = subscriber_id
        self._attached = False
        self._received_events = 0
        self._accepted_events = 0
        self._ignored_events = 0

    @property
    def attached(self) -> bool:
        return self._attached

    @property
    def received_events(self) -> int:
        return self._received_events

    @property
    def accepted_events(self) -> int:
        return self._accepted_events

    @property
    def ignored_events(self) -> int:
        return self._ignored_events

    def attach(self) -> None:
        if self._attached:
            raise ToolUsageAnalyticsBindingError(
                "Usage Analytics binding is "
                "already attached."
            )

        try:
            self.stream.subscribe(
                self.subscriber_id,
                self._on_event,
            )
        except ToolTelemetryStreamError as exc:
            raise ToolUsageAnalyticsBindingError(
                "Unable to attach Usage Analytics "
                f"subscriber {self.subscriber_id}: "
                f"{exc}"
            ) from exc

        self._attached = True

    def detach(self) -> None:
        if not self._attached:
            raise ToolUsageAnalyticsBindingError(
                "Usage Analytics binding is "
                "not attached."
            )

        try:
            self.stream.unsubscribe(
                self.subscriber_id
            )
        except ToolTelemetryStreamError as exc:
            raise ToolUsageAnalyticsBindingError(
                "Unable to detach Usage Analytics "
                f"subscriber {self.subscriber_id}: "
                f"{exc}"
            ) from exc

        self._attached = False

    def _on_event(
        self,
        event: ToolTelemetryEvent,
    ) -> None:
        self._received_events += 1

        accepted = self.analytics.record(event)

        if accepted:
            self._accepted_events += 1
        else:
            self._ignored_events += 1

    def __enter__(
        self,
    ) -> ToolUsageAnalyticsStreamBinding:
        self.attach()
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ) -> None:
        del exc_type, exc, traceback

        if self._attached:
            self.detach()

    def counters(self) -> dict[str, int]:
        return {
            "received_events": (
                self._received_events
            ),
            "accepted_events": (
                self._accepted_events
            ),
            "ignored_events": (
                self._ignored_events
            ),
        }


class ToolUsageRollup(BaseModel):
    group_by: str
    group_id: str
    statistics: ToolUsageStatistics


class ToolUsageWindowComparison(BaseModel):
    current: ToolUsageSnapshot
    previous: ToolUsageSnapshot

    call_count_change: int
    success_rate_change: float
    average_latency_change_ms: float
    retry_count_change: int
    total_cost_change_usd: Decimal


class ToolUsageAnalyticsReport(BaseModel):
    snapshot: ToolUsageSnapshot
    tool_rollups: list[
        ToolUsageRollup
    ] = Field(default_factory=list)
    project_rollups: list[
        ToolUsageRollup
    ] = Field(default_factory=list)
    agent_rollups: list[
        ToolUsageRollup
    ] = Field(default_factory=list)
    rankings: dict[
        ToolRankingMetric,
        list[ToolUsageRankingItem],
    ] = Field(default_factory=dict)
    generated_at: datetime = Field(
        default_factory=utc_now
    )



