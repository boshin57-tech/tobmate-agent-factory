from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from .tool_usage_analytics import (
    ToolAnalyticsKey,
    ToolUsageSnapshot,
    ToolUsageStatistics,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ToolSLAStatus(StrEnum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    BREACHED = "BREACHED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ToolSLABreachType(StrEnum):
    AVAILABILITY = "AVAILABILITY"
    SUCCESS_RATE = "SUCCESS_RATE"
    LATENCY = "LATENCY"
    ERROR_BUDGET = "ERROR_BUDGET"
    TIMEOUT_RATE = "TIMEOUT_RATE"
    RETRY_RATE = "RETRY_RATE"
    COST = "COST"


class ToolSLAPolicy(BaseModel):
    policy_id: str
    name: str

    minimum_sample_size: int = Field(
        default=1,
        ge=1,
    )

    minimum_availability: float = Field(
        default=0.99,
        ge=0,
        le=1,
    )
    minimum_success_rate: float = Field(
        default=0.99,
        ge=0,
        le=1,
    )

    maximum_average_latency_ms: (
        float | None
    ) = Field(
        default=None,
        ge=0,
    )
    maximum_latency_ms: float | None = Field(
        default=None,
        ge=0,
    )

    maximum_timeout_rate: float | None = Field(
        default=None,
        ge=0,
        le=1,
    )
    maximum_retry_rate: float | None = Field(
        default=None,
        ge=0,
    )

    maximum_average_cost_usd: (
        Decimal | None
    ) = Field(
        default=None,
        ge=0,
    )

    error_budget_ratio: float = Field(
        default=0.01,
        ge=0,
        le=1,
    )

    warning_threshold_ratio: float = Field(
        default=0.80,
        ge=0,
        le=1,
    )


class ToolSLABreach(BaseModel):
    breach_type: ToolSLABreachType
    message: str

    actual_value: float | Decimal
    threshold_value: float | Decimal

    warning: bool = False
    detected_at: datetime = Field(
        default_factory=utc_now
    )


class ToolErrorBudgetStatus(BaseModel):
    allowed_errors: float = Field(
        ge=0,
    )
    consumed_errors: int = Field(
        ge=0,
    )
    remaining_errors: float
    consumption_ratio: float = Field(
        ge=0,
    )
    exhausted: bool
    warning: bool


class ToolSLAEvaluation(BaseModel):
    policy_id: str
    key: ToolAnalyticsKey
    status: ToolSLAStatus

    sample_size: int = Field(
        ge=0,
    )

    availability: float = Field(
        ge=0,
        le=1,
    )
    success_rate: float = Field(
        ge=0,
        le=1,
    )
    timeout_rate: float = Field(
        ge=0,
        le=1,
    )
    retry_rate: float = Field(
        ge=0,
    )

    average_latency_ms: float = Field(
        ge=0,
    )
    maximum_latency_ms: float | None = Field(
        default=None,
        ge=0,
    )

    average_cost_usd: Decimal = Field(
        ge=0,
    )

    error_budget: ToolErrorBudgetStatus
    breaches: list[ToolSLABreach] = Field(
        default_factory=list
    )

    evaluated_at: datetime = Field(
        default_factory=utc_now
    )

    @property
    def breached(self) -> bool:
        return self.status is (
            ToolSLAStatus.BREACHED
        )

    @property
    def healthy(self) -> bool:
        return self.status is (
            ToolSLAStatus.HEALTHY
        )


class ToolSLASnapshotReport(BaseModel):
    policy_id: str
    evaluations: list[
        ToolSLAEvaluation
    ] = Field(default_factory=list)

    generated_at: datetime = Field(
        default_factory=utc_now
    )
    window_start: datetime | None = None
    window_end: datetime | None = None

    @property
    def breached_count(self) -> int:
        return sum(
            1
            for item in self.evaluations
            if item.breached
        )

    @property
    def warning_count(self) -> int:
        return sum(
            1
            for item in self.evaluations
            if item.status is (
                ToolSLAStatus.WARNING
            )
        )

    @property
    def healthy_count(self) -> int:
        return sum(
            1
            for item in self.evaluations
            if item.healthy
        )


class ToolSLAEvaluator:
    def evaluate(
        self,
        *,
        statistics: ToolUsageStatistics,
        policy: ToolSLAPolicy,
    ) -> ToolSLAEvaluation:
        sample_size = statistics.total_calls

        availability = self._availability(
            statistics
        )
        success_rate = statistics.success_rate
        timeout_rate = self._timeout_rate(
            statistics
        )
        retry_rate = self._retry_rate(
            statistics
        )

        error_budget = self._error_budget(
            statistics=statistics,
            policy=policy,
        )

        if sample_size < policy.minimum_sample_size:
            return ToolSLAEvaluation(
                policy_id=policy.policy_id,
                key=statistics.key.model_copy(
                    deep=True
                ),
                status=(
                    ToolSLAStatus
                    .INSUFFICIENT_DATA
                ),
                sample_size=sample_size,
                availability=availability,
                success_rate=success_rate,
                timeout_rate=timeout_rate,
                retry_rate=retry_rate,
                average_latency_ms=(
                    statistics
                    .average_latency_ms
                ),
                maximum_latency_ms=(
                    statistics
                    .maximum_latency_ms
                ),
                average_cost_usd=(
                    statistics
                    .average_cost_usd
                ),
                error_budget=error_budget,
            )

        breaches: list[ToolSLABreach] = []

        self._evaluate_minimum_metric(
            breaches=breaches,
            breach_type=(
                ToolSLABreachType.AVAILABILITY
            ),
            label="Availability",
            actual=availability,
            threshold=(
                policy.minimum_availability
            ),
            warning_ratio=(
                policy.warning_threshold_ratio
            ),
        )

        self._evaluate_minimum_metric(
            breaches=breaches,
            breach_type=(
                ToolSLABreachType.SUCCESS_RATE
            ),
            label="Success rate",
            actual=success_rate,
            threshold=(
                policy.minimum_success_rate
            ),
            warning_ratio=(
                policy.warning_threshold_ratio
            ),
        )

        if (
            policy.maximum_average_latency_ms
            is not None
        ):
            self._evaluate_maximum_metric(
                breaches=breaches,
                breach_type=(
                    ToolSLABreachType.LATENCY
                ),
                label="Average latency",
                actual=(
                    statistics
                    .average_latency_ms
                ),
                threshold=(
                    policy
                    .maximum_average_latency_ms
                ),
                warning_ratio=(
                    policy.warning_threshold_ratio
                ),
            )

        if (
            policy.maximum_latency_ms
            is not None
            and statistics.maximum_latency_ms
            is not None
        ):
            self._evaluate_maximum_metric(
                breaches=breaches,
                breach_type=(
                    ToolSLABreachType.LATENCY
                ),
                label="Maximum latency",
                actual=(
                    statistics.maximum_latency_ms
                ),
                threshold=(
                    policy.maximum_latency_ms
                ),
                warning_ratio=(
                    policy.warning_threshold_ratio
                ),
            )

        if (
            policy.maximum_timeout_rate
            is not None
        ):
            self._evaluate_maximum_metric(
                breaches=breaches,
                breach_type=(
                    ToolSLABreachType.TIMEOUT_RATE
                ),
                label="Timeout rate",
                actual=timeout_rate,
                threshold=(
                    policy.maximum_timeout_rate
                ),
                warning_ratio=(
                    policy.warning_threshold_ratio
                ),
            )

        if (
            policy.maximum_retry_rate
            is not None
        ):
            self._evaluate_maximum_metric(
                breaches=breaches,
                breach_type=(
                    ToolSLABreachType.RETRY_RATE
                ),
                label="Retry rate",
                actual=retry_rate,
                threshold=(
                    policy.maximum_retry_rate
                ),
                warning_ratio=(
                    policy.warning_threshold_ratio
                ),
            )

        if (
            policy.maximum_average_cost_usd
            is not None
        ):
            self._evaluate_maximum_metric(
                breaches=breaches,
                breach_type=(
                    ToolSLABreachType.COST
                ),
                label="Average cost",
                actual=(
                    statistics.average_cost_usd
                ),
                threshold=(
                    policy
                    .maximum_average_cost_usd
                ),
                warning_ratio=(
                    policy.warning_threshold_ratio
                ),
            )

        self._append_error_budget_breach(
            breaches=breaches,
            error_budget=error_budget,
        )

        status = self._status(
            breaches=breaches,
        )

        return ToolSLAEvaluation(
            policy_id=policy.policy_id,
            key=statistics.key.model_copy(
                deep=True
            ),
            status=status,
            sample_size=sample_size,
            availability=availability,
            success_rate=success_rate,
            timeout_rate=timeout_rate,
            retry_rate=retry_rate,
            average_latency_ms=(
                statistics.average_latency_ms
            ),
            maximum_latency_ms=(
                statistics.maximum_latency_ms
            ),
            average_cost_usd=(
                statistics.average_cost_usd
            ),
            error_budget=error_budget,
            breaches=breaches,
        )

    def _availability(
        self,
        statistics: ToolUsageStatistics,
    ) -> float:
        if statistics.total_calls == 0:
            return 0

        unavailable_calls = (
            statistics.blocked_calls
            + statistics.timed_out_calls
        )

        return max(
            0,
            1
            - (
                unavailable_calls
                / statistics.total_calls
            ),
        )

    def _timeout_rate(
        self,
        statistics: ToolUsageStatistics,
    ) -> float:
        if statistics.total_calls == 0:
            return 0

        return (
            statistics.timed_out_calls
            / statistics.total_calls
        )

    def _retry_rate(
        self,
        statistics: ToolUsageStatistics,
    ) -> float:
        if statistics.total_calls == 0:
            return 0

        return (
            statistics.retry_count
            / statistics.total_calls
        )

    def _error_budget(
        self,
        *,
        statistics: ToolUsageStatistics,
        policy: ToolSLAPolicy,
    ) -> ToolErrorBudgetStatus:
        allowed_errors = (
            statistics.total_calls
            * policy.error_budget_ratio
        )

        consumed_errors = (
            statistics.unsuccessful_calls
        )

        remaining_errors = (
            allowed_errors
            - consumed_errors
        )

        if allowed_errors == 0:
            consumption_ratio = (
                0
                if consumed_errors == 0
                else float("inf")
            )
        else:
            consumption_ratio = (
                consumed_errors
                / allowed_errors
            )

        exhausted = (
            consumed_errors > allowed_errors
        )

        warning = (
            not exhausted
            and allowed_errors > 0
            and consumption_ratio
            >= policy.warning_threshold_ratio
        )

        return ToolErrorBudgetStatus(
            allowed_errors=allowed_errors,
            consumed_errors=consumed_errors,
            remaining_errors=remaining_errors,
            consumption_ratio=(
                consumption_ratio
            ),
            exhausted=exhausted,
            warning=warning,
        )

    def _evaluate_minimum_metric(
        self,
        *,
        breaches: list[ToolSLABreach],
        breach_type: ToolSLABreachType,
        label: str,
        actual: float | Decimal,
        threshold: float | Decimal,
        warning_ratio: float,
    ) -> None:
        if actual < threshold:
            breaches.append(
                ToolSLABreach(
                    breach_type=breach_type,
                    message=(
                        f"{label} {actual} is below "
                        f"minimum {threshold}."
                    ),
                    actual_value=actual,
                    threshold_value=threshold,
                    warning=False,
                )
            )
            return

        # 최소 목표와 완전한 1.0 사이의 여유 중
        # warning_ratio 이상을 소비하면 경고합니다.
        numeric_actual = float(actual)
        numeric_threshold = float(threshold)

        warning_boundary = (
            numeric_threshold
            + (
                1 - numeric_threshold
            )
            * (
                1 - warning_ratio
            )
        )

        if numeric_actual < warning_boundary:
            breaches.append(
                ToolSLABreach(
                    breach_type=breach_type,
                    message=(
                        f"{label} {actual} is near "
                        f"minimum {threshold}."
                    ),
                    actual_value=actual,
                    threshold_value=threshold,
                    warning=True,
                )
            )

    def _evaluate_maximum_metric(
        self,
        *,
        breaches: list[ToolSLABreach],
        breach_type: ToolSLABreachType,
        label: str,
        actual: float | Decimal,
        threshold: float | Decimal,
        warning_ratio: float,
    ) -> None:
        if actual > threshold:
            breaches.append(
                ToolSLABreach(
                    breach_type=breach_type,
                    message=(
                        f"{label} {actual} exceeds "
                        f"maximum {threshold}."
                    ),
                    actual_value=actual,
                    threshold_value=threshold,
                    warning=False,
                )
            )
            return

        warning_boundary = (
            float(threshold)
            * warning_ratio
        )

        if float(actual) >= warning_boundary:
            breaches.append(
                ToolSLABreach(
                    breach_type=breach_type,
                    message=(
                        f"{label} {actual} is near "
                        f"maximum {threshold}."
                    ),
                    actual_value=actual,
                    threshold_value=threshold,
                    warning=True,
                )
            )

    def _append_error_budget_breach(
        self,
        *,
        breaches: list[ToolSLABreach],
        error_budget: ToolErrorBudgetStatus,
    ) -> None:
        if error_budget.exhausted:
            breaches.append(
                ToolSLABreach(
                    breach_type=(
                        ToolSLABreachType
                        .ERROR_BUDGET
                    ),
                    message=(
                        "Error budget is exhausted: "
                        f"{error_budget.consumed_errors} "
                        "errors consumed from "
                        f"{error_budget.allowed_errors} "
                        "allowed."
                    ),
                    actual_value=(
                        error_budget.consumed_errors
                    ),
                    threshold_value=(
                        error_budget.allowed_errors
                    ),
                    warning=False,
                )
            )

        elif error_budget.warning:
            breaches.append(
                ToolSLABreach(
                    breach_type=(
                        ToolSLABreachType
                        .ERROR_BUDGET
                    ),
                    message=(
                        "Error budget consumption is "
                        "near its allowed limit."
                    ),
                    actual_value=(
                        error_budget
                        .consumption_ratio
                    ),
                    threshold_value=1.0,
                    warning=True,
                )
            )

    def _status(
        self,
        *,
        breaches: list[ToolSLABreach],
    ) -> ToolSLAStatus:
        if any(
            not breach.warning
            for breach in breaches
        ):
            return ToolSLAStatus.BREACHED

        if breaches:
            return ToolSLAStatus.WARNING

        return ToolSLAStatus.HEALTHY


class ToolSLAPolicyRegistryError(RuntimeError):
    """Raised for invalid SLA policy registry operations."""


class ToolSLAPolicyRegistry:
    def __init__(
        self,
        *,
        default_policy_id: str | None = None,
    ) -> None:
        self._policies: dict[
            str,
            ToolSLAPolicy,
        ] = {}
        self._tool_bindings: dict[
            str,
            str,
        ] = {}
        self._default_policy_id = (
            default_policy_id
        )

    @property
    def default_policy_id(
        self,
    ) -> str | None:
        return self._default_policy_id

    def register(
        self,
        policy: ToolSLAPolicy,
        *,
        make_default: bool = False,
    ) -> None:
        policy_id = policy.policy_id.strip()

        if not policy_id:
            raise ToolSLAPolicyRegistryError(
                "SLA policy ID is required."
            )

        if policy_id in self._policies:
            raise ToolSLAPolicyRegistryError(
                "SLA policy already registered: "
                f"{policy_id}"
            )

        self._policies[policy_id] = (
            policy.model_copy(deep=True)
        )

        if (
            make_default
            or self._default_policy_id is None
        ):
            self._default_policy_id = policy_id

    def upsert(
        self,
        policy: ToolSLAPolicy,
    ) -> None:
        policy_id = policy.policy_id.strip()

        if not policy_id:
            raise ToolSLAPolicyRegistryError(
                "SLA policy ID is required."
            )

        self._policies[policy_id] = (
            policy.model_copy(deep=True)
        )

        if self._default_policy_id is None:
            self._default_policy_id = policy_id

    def unregister(
        self,
        policy_id: str,
    ) -> None:
        if policy_id not in self._policies:
            raise ToolSLAPolicyRegistryError(
                "Unknown SLA policy: "
                f"{policy_id}"
            )

        bound_tools = [
            tool_id
            for tool_id, bound_policy_id
            in self._tool_bindings.items()
            if bound_policy_id == policy_id
        ]

        if bound_tools:
            raise ToolSLAPolicyRegistryError(
                "Cannot unregister SLA policy "
                f"{policy_id}; it is bound to: "
                + ", ".join(sorted(bound_tools))
            )

        del self._policies[policy_id]

        if self._default_policy_id == policy_id:
            self._default_policy_id = (
                sorted(self._policies)[0]
                if self._policies
                else None
            )

    def bind_tool(
        self,
        *,
        tool_id: str,
        policy_id: str,
    ) -> None:
        tool_id = tool_id.strip()

        if not tool_id:
            raise ToolSLAPolicyRegistryError(
                "Tool ID is required."
            )

        if policy_id not in self._policies:
            raise ToolSLAPolicyRegistryError(
                "Unknown SLA policy: "
                f"{policy_id}"
            )

        self._tool_bindings[tool_id] = policy_id

    def unbind_tool(
        self,
        tool_id: str,
    ) -> None:
        if tool_id not in self._tool_bindings:
            raise ToolSLAPolicyRegistryError(
                "Tool has no SLA policy binding: "
                f"{tool_id}"
            )

        del self._tool_bindings[tool_id]

    def set_default(
        self,
        policy_id: str,
    ) -> None:
        if policy_id not in self._policies:
            raise ToolSLAPolicyRegistryError(
                "Unknown SLA policy: "
                f"{policy_id}"
            )

        self._default_policy_id = policy_id

    def get(
        self,
        policy_id: str,
    ) -> ToolSLAPolicy:
        try:
            return self._policies[
                policy_id
            ].model_copy(deep=True)
        except KeyError as exc:
            raise ToolSLAPolicyRegistryError(
                "Unknown SLA policy: "
                f"{policy_id}"
            ) from exc

    def policy_for_tool(
        self,
        tool_id: str,
    ) -> ToolSLAPolicy:
        policy_id = self._tool_bindings.get(
            tool_id,
            self._default_policy_id,
        )

        if policy_id is None:
            raise ToolSLAPolicyRegistryError(
                "No default SLA policy is configured "
                f"for Tool {tool_id}."
            )

        return self.get(policy_id)

    def list_policies(
        self,
    ) -> list[ToolSLAPolicy]:
        return [
            self._policies[key].model_copy(
                deep=True
            )
            for key in sorted(self._policies)
        ]

    def tool_bindings(
        self,
    ) -> dict[str, str]:
        return dict(
            sorted(
                self._tool_bindings.items()
            )
        )


class ToolSLABreachHistoryRecord(BaseModel):
    evaluation_id: str
    policy_id: str
    key: ToolAnalyticsKey
    status: ToolSLAStatus
    breaches: list[ToolSLABreach] = Field(
        default_factory=list
    )
    sample_size: int = Field(
        ge=0,
    )
    window_start: datetime | None = None
    window_end: datetime | None = None
    recorded_at: datetime = Field(
        default_factory=utc_now
    )


class ToolSLAMonitorError(RuntimeError):
    """Raised when SLA monitoring cannot proceed."""


class ToolSLAMonitor:
    def __init__(
        self,
        *,
        policies: ToolSLAPolicyRegistry,
        evaluator: ToolSLAEvaluator | None = None,
        maximum_history: int = 10000,
    ) -> None:
        if maximum_history <= 0:
            raise ValueError(
                "maximum_history must be positive."
            )

        self.policies = policies
        self.evaluator = (
            evaluator
            or ToolSLAEvaluator()
        )
        self.maximum_history = maximum_history

        self._evaluation_counter = 0
        self._latest: dict[
            tuple[str, str | None, str | None],
            ToolSLAEvaluation,
        ] = {}
        self._history: list[
            ToolSLABreachHistoryRecord
        ] = []

    def evaluate_statistics(
        self,
        statistics: ToolUsageStatistics,
        *,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> ToolSLAEvaluation:
        policy = self.policies.policy_for_tool(
            statistics.key.tool_id
        )

        evaluation = self.evaluator.evaluate(
            statistics=statistics,
            policy=policy,
        )

        self._latest[
            statistics.key.identity
        ] = evaluation.model_copy(
            deep=True
        )

        self._record_history(
            evaluation=evaluation,
            window_start=window_start,
            window_end=window_end,
        )

        return evaluation.model_copy(
            deep=True
        )

    def evaluate_snapshot(
        self,
        snapshot: ToolUsageSnapshot,
    ) -> ToolSLASnapshotReport:
        evaluations = [
            self.evaluate_statistics(
                statistics,
                window_start=(
                    snapshot.window_start
                ),
                window_end=(
                    snapshot.window_end
                ),
            )
            for statistics in (
                snapshot.statistics
            )
        ]

        evaluations.sort(
            key=lambda item: (
                item.key.tool_id,
                item.key.project_id or "",
                item.key.agent_id or "",
            )
        )

        policy_ids = {
            item.policy_id
            for item in evaluations
        }

        report_policy_id = (
            next(iter(policy_ids))
            if len(policy_ids) == 1
            else "MULTIPLE"
        )

        return ToolSLASnapshotReport(
            policy_id=report_policy_id,
            evaluations=evaluations,
            window_start=snapshot.window_start,
            window_end=snapshot.window_end,
        )

    def latest(
        self,
        *,
        tool_id: str,
        project_id: str | None = None,
        agent_id: str | None = None,
    ) -> ToolSLAEvaluation | None:
        value = self._latest.get(
            (
                tool_id,
                project_id,
                agent_id,
            )
        )

        if value is None:
            return None

        return value.model_copy(deep=True)

    def latest_all(
        self,
    ) -> list[ToolSLAEvaluation]:
        return [
            self._latest[key].model_copy(
                deep=True
            )
            for key in sorted(
                self._latest,
                key=lambda item: (
                    item[0],
                    item[1] or "",
                    item[2] or "",
                ),
            )
        ]

    def _record_history(
        self,
        *,
        evaluation: ToolSLAEvaluation,
        window_start: datetime | None,
        window_end: datetime | None,
    ) -> None:
        self._evaluation_counter += 1

        record = ToolSLABreachHistoryRecord(
            evaluation_id=(
                f"sla-evaluation-"
                f"{self._evaluation_counter}"
            ),
            policy_id=evaluation.policy_id,
            key=evaluation.key.model_copy(
                deep=True
            ),
            status=evaluation.status,
            breaches=[
                item.model_copy(deep=True)
                for item in evaluation.breaches
            ],
            sample_size=evaluation.sample_size,
            window_start=window_start,
            window_end=window_end,
        )

        self._history.append(record)

        overflow = (
            len(self._history)
            - self.maximum_history
        )

        if overflow > 0:
            del self._history[:overflow]

    def history(
        self,
        *,
        tool_id: str | None = None,
        project_id: str | None = None,
        agent_id: str | None = None,
        status: ToolSLAStatus | None = None,
        breached_only: bool = False,
    ) -> list[ToolSLABreachHistoryRecord]:
        results: list[
            ToolSLABreachHistoryRecord
        ] = []

        for record in self._history:
            if (
                tool_id is not None
                and record.key.tool_id
                != tool_id
            ):
                continue

            if (
                project_id is not None
                and record.key.project_id
                != project_id
            ):
                continue

            if (
                agent_id is not None
                and record.key.agent_id
                != agent_id
            ):
                continue

            if (
                status is not None
                and record.status is not status
            ):
                continue

            if (
                breached_only
                and record.status is not (
                    ToolSLAStatus.BREACHED
                )
            ):
                continue

            results.append(
                record.model_copy(deep=True)
            )

        return results

    def clear_history(self) -> None:
        self._history.clear()

    def history_count(self) -> int:
        return len(self._history)


from collections.abc import (
    Awaitable,
    Callable,
)
import inspect

from .tool_telemetry import (
    InMemoryToolTelemetryStream,
    ToolTelemetryEvent,
)
from .tool_usage_analytics import (
    ToolUsageAnalytics,
)


class ToolSLAChangeType(StrEnum):
    INITIAL = "INITIAL"
    STATUS_CHANGED = "STATUS_CHANGED"
    BREACH_UPDATED = "BREACH_UPDATED"
    UNCHANGED = "UNCHANGED"


class ToolSLAAlert(BaseModel):
    alert_id: str
    change_type: ToolSLAChangeType

    previous_status: ToolSLAStatus | None = None
    current_status: ToolSLAStatus

    evaluation: ToolSLAEvaluation
    triggered_by_event_id: str | None = None

    created_at: datetime = Field(
        default_factory=utc_now
    )


ToolSLAAlertSubscriber = Callable[
    [ToolSLAAlert],
    None | Awaitable[None],
]


class ToolSLARealtimeBindingError(RuntimeError):
    """Raised for invalid real-time SLA bindings."""


class ToolSLARealtimeBinding:
    def __init__(
        self,
        *,
        analytics: ToolUsageAnalytics,
        monitor: ToolSLAMonitor,
        stream: InMemoryToolTelemetryStream,
        subscriber_id: str = (
            "tool-sla-monitor"
        ),
        notify_on_healthy: bool = False,
        suppress_unchanged: bool = True,
    ) -> None:
        subscriber_id = subscriber_id.strip()

        if not subscriber_id:
            raise ValueError(
                "subscriber_id is required."
            )

        self.analytics = analytics
        self.monitor = monitor
        self.stream = stream
        self.subscriber_id = subscriber_id
        self.notify_on_healthy = notify_on_healthy
        self.suppress_unchanged = (
            suppress_unchanged
        )

        self._attached = False
        self._alert_counter = 0
        self._subscribers: dict[
            str,
            ToolSLAAlertSubscriber,
        ] = {}

        self._last_status: dict[
            tuple[str, str | None, str | None],
            ToolSLAStatus,
        ] = {}

        self._last_breach_signature: dict[
            tuple[str, str | None, str | None],
            tuple[
                tuple[str, bool, str],
                ...,
            ],
        ] = {}

        self._received_events = 0
        self._evaluated_events = 0
        self._ignored_events = 0
        self._alerts_emitted = 0

    @property
    def attached(self) -> bool:
        return self._attached

    def counters(self) -> dict[str, int]:
        return {
            "received_events": (
                self._received_events
            ),
            "evaluated_events": (
                self._evaluated_events
            ),
            "ignored_events": (
                self._ignored_events
            ),
            "alerts_emitted": (
                self._alerts_emitted
            ),
        }

    def attach(self) -> None:
        if self._attached:
            raise ToolSLARealtimeBindingError(
                "SLA real-time binding is "
                "already attached."
            )

        try:
            self.stream.subscribe(
                self.subscriber_id,
                self._on_event,
            )
        except Exception as exc:
            raise ToolSLARealtimeBindingError(
                "Unable to attach SLA real-time "
                f"binding: {exc}"
            ) from exc

        self._attached = True

    def detach(self) -> None:
        if not self._attached:
            raise ToolSLARealtimeBindingError(
                "SLA real-time binding is "
                "not attached."
            )

        try:
            self.stream.unsubscribe(
                self.subscriber_id
            )
        except Exception as exc:
            raise ToolSLARealtimeBindingError(
                "Unable to detach SLA real-time "
                f"binding: {exc}"
            ) from exc

        self._attached = False

    def subscribe(
        self,
        subscriber_id: str,
        handler: ToolSLAAlertSubscriber,
    ) -> None:
        subscriber_id = subscriber_id.strip()

        if not subscriber_id:
            raise ToolSLARealtimeBindingError(
                "Alert subscriber ID is required."
            )

        if subscriber_id in self._subscribers:
            raise ToolSLARealtimeBindingError(
                "SLA alert subscriber already "
                f"exists: {subscriber_id}"
            )

        self._subscribers[
            subscriber_id
        ] = handler

    def unsubscribe(
        self,
        subscriber_id: str,
    ) -> None:
        if subscriber_id not in self._subscribers:
            raise ToolSLARealtimeBindingError(
                "Unknown SLA alert subscriber: "
                f"{subscriber_id}"
            )

        del self._subscribers[subscriber_id]

    def subscriber_ids(self) -> list[str]:
        return sorted(self._subscribers)

    async def _on_event(
        self,
        event: ToolTelemetryEvent,
    ) -> None:
        self._received_events += 1

        if not self.analytics.accepts(event):
            self._ignored_events += 1
            return

        if event.tool_id is None:
            self._ignored_events += 1
            return

        statistics = self.analytics.get(
            tool_id=event.tool_id,
            project_id=event.project_id,
            agent_id=event.agent_id,
        )

        if statistics is None:
            self._ignored_events += 1
            return

        self._evaluated_events += 1

        evaluation = (
            self.monitor.evaluate_statistics(
                statistics
            )
        )

        alert = self._build_alert(
            evaluation=evaluation,
            event=event,
        )

        if alert is None:
            return

        await self._publish_alert(alert)

    def _breach_signature(
        self,
        evaluation: ToolSLAEvaluation,
    ) -> tuple[
        tuple[str, bool, str],
        ...,
    ]:
        return tuple(
            sorted(
                (
                    breach.breach_type.value,
                    breach.warning,
                    breach.message,
                )
                for breach in (
                    evaluation.breaches
                )
            )
        )

    def _build_alert(
        self,
        *,
        evaluation: ToolSLAEvaluation,
        event: ToolTelemetryEvent,
    ) -> ToolSLAAlert | None:
        identity = evaluation.key.identity

        previous_status = (
            self._last_status.get(identity)
        )
        current_signature = (
            self._breach_signature(
                evaluation
            )
        )
        previous_signature = (
            self._last_breach_signature.get(
                identity
            )
        )

        if previous_status is None:
            change_type = (
                ToolSLAChangeType.INITIAL
            )

        elif previous_status is not (
            evaluation.status
        ):
            change_type = (
                ToolSLAChangeType
                .STATUS_CHANGED
            )

        elif previous_signature != (
            current_signature
        ):
            change_type = (
                ToolSLAChangeType
                .BREACH_UPDATED
            )

        else:
            change_type = (
                ToolSLAChangeType.UNCHANGED
            )

        self._last_status[
            identity
        ] = evaluation.status

        self._last_breach_signature[
            identity
        ] = current_signature

        if (
            self.suppress_unchanged
            and change_type is (
                ToolSLAChangeType.UNCHANGED
            )
        ):
            return None

        if (
            not self.notify_on_healthy
            and evaluation.status is (
                ToolSLAStatus.HEALTHY
            )
            and change_type is not (
                ToolSLAChangeType
                .STATUS_CHANGED
            )
        ):
            return None

        self._alert_counter += 1

        return ToolSLAAlert(
            alert_id=(
                f"sla-alert-"
                f"{self._alert_counter}"
            ),
            change_type=change_type,
            previous_status=previous_status,
            current_status=(
                evaluation.status
            ),
            evaluation=(
                evaluation.model_copy(
                    deep=True
                )
            ),
            triggered_by_event_id=(
                event.event_id
            ),
        )

    async def _publish_alert(
        self,
        alert: ToolSLAAlert,
    ) -> None:
        self._alerts_emitted += 1

        for subscriber_id in sorted(
            self._subscribers
        ):
            handler = self._subscribers[
                subscriber_id
            ]

            result = handler(
                alert.model_copy(deep=True)
            )

            if inspect.isawaitable(result):
                await result

    def __enter__(
        self,
    ) -> ToolSLARealtimeBinding:
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
