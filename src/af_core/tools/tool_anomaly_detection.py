from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from .tool_usage_analytics import (
    ToolAnalyticsKey,
    ToolUsageStatistics,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ToolAnomalyMetric(StrEnum):
    FAILURE_RATE = "FAILURE_RATE"
    LATENCY = "LATENCY"
    RETRY_RATE = "RETRY_RATE"
    COST = "COST"
    TIMEOUT_RATE = "TIMEOUT_RATE"
    BLOCK_RATE = "BLOCK_RATE"


class ToolAnomalySeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ToolAnomalyAction(StrEnum):
    OBSERVE = "OBSERVE"
    ALERT = "ALERT"
    QUARANTINE = "QUARANTINE"
    REVOKE = "REVOKE"


class ToolAnomalyBaseline(BaseModel):
    key: ToolAnalyticsKey

    sample_size: int = Field(
        default=0,
        ge=0,
    )

    failure_rate: float = Field(
        default=0,
        ge=0,
        le=1,
    )
    average_latency_ms: float = Field(
        default=0,
        ge=0,
    )
    retry_rate: float = Field(
        default=0,
        ge=0,
    )
    average_cost_usd: Decimal = Field(
        default=Decimal("0"),
        ge=0,
    )
    timeout_rate: float = Field(
        default=0,
        ge=0,
        le=1,
    )
    block_rate: float = Field(
        default=0,
        ge=0,
        le=1,
    )

    generated_at: datetime = Field(
        default_factory=utc_now
    )


class ToolAnomalyPolicy(BaseModel):
    policy_id: str
    name: str

    minimum_sample_size: int = Field(
        default=10,
        ge=1,
    )

    failure_rate_multiplier: float = Field(
        default=2.0,
        ge=1,
    )
    latency_multiplier: float = Field(
        default=2.0,
        ge=1,
    )
    retry_rate_multiplier: float = Field(
        default=2.0,
        ge=1,
    )
    cost_multiplier: float = Field(
        default=2.0,
        ge=1,
    )
    timeout_rate_multiplier: float = Field(
        default=2.0,
        ge=1,
    )
    block_rate_multiplier: float = Field(
        default=2.0,
        ge=1,
    )

    absolute_failure_rate: float | None = Field(
        default=None,
        ge=0,
        le=1,
    )
    absolute_latency_ms: float | None = Field(
        default=None,
        ge=0,
    )
    absolute_retry_rate: float | None = Field(
        default=None,
        ge=0,
    )
    absolute_average_cost_usd: (
        Decimal | None
    ) = Field(
        default=None,
        ge=0,
    )
    absolute_timeout_rate: float | None = Field(
        default=None,
        ge=0,
        le=1,
    )
    absolute_block_rate: float | None = Field(
        default=None,
        ge=0,
        le=1,
    )

    warning_score: float = Field(
        default=1.0,
        ge=0,
    )
    high_score: float = Field(
        default=2.0,
        ge=0,
    )
    critical_score: float = Field(
        default=3.0,
        ge=0,
    )

    quarantine_at: ToolAnomalySeverity = (
        ToolAnomalySeverity.CRITICAL
    )
    revoke_at: ToolAnomalySeverity | None = None

    auto_quarantine: bool = True
    auto_revoke: bool = False


class ToolAnomalySignal(BaseModel):
    metric: ToolAnomalyMetric

    actual_value: float | Decimal
    baseline_value: float | Decimal
    threshold_value: float | Decimal

    ratio: float = Field(
        ge=0,
    )
    score: float = Field(
        ge=0,
    )
    severity: ToolAnomalySeverity

    message: str


class ToolAnomalyEvaluation(BaseModel):
    policy_id: str
    key: ToolAnalyticsKey

    sample_size: int = Field(
        ge=0,
    )
    baseline_sample_size: int = Field(
        ge=0,
    )

    anomalous: bool
    severity: ToolAnomalySeverity
    recommended_action: ToolAnomalyAction

    signals: list[
        ToolAnomalySignal
    ] = Field(default_factory=list)

    evaluated_at: datetime = Field(
        default_factory=utc_now
    )

    @property
    def quarantine_required(self) -> bool:
        return self.recommended_action is (
            ToolAnomalyAction.QUARANTINE
        )

    @property
    def revocation_required(self) -> bool:
        return self.recommended_action is (
            ToolAnomalyAction.REVOKE
        )


class ToolAnomalyHistoryRecord(BaseModel):
    evaluation_id: str
    evaluation: ToolAnomalyEvaluation

    triggered_by_event_id: str | None = None
    quarantine_request_id: str | None = None

    successful: bool = True
    error: str | None = None

    recorded_at: datetime = Field(
        default_factory=utc_now
    )


class ToolAnomalyDetector:
    def baseline_from_statistics(
        self,
        statistics: ToolUsageStatistics,
    ) -> ToolAnomalyBaseline:
        total_calls = statistics.total_calls

        timeout_rate = (
            statistics.timed_out_calls
            / total_calls
            if total_calls
            else 0
        )

        block_rate = (
            statistics.blocked_calls
            / total_calls
            if total_calls
            else 0
        )

        retry_rate = (
            statistics.retry_count
            / total_calls
            if total_calls
            else 0
        )

        return ToolAnomalyBaseline(
            key=statistics.key.model_copy(
                deep=True
            ),
            sample_size=total_calls,
            failure_rate=(
                statistics.failure_rate
            ),
            average_latency_ms=(
                statistics.average_latency_ms
            ),
            retry_rate=retry_rate,
            average_cost_usd=(
                statistics.average_cost_usd
            ),
            timeout_rate=timeout_rate,
            block_rate=block_rate,
        )

    def evaluate(
        self,
        *,
        statistics: ToolUsageStatistics,
        baseline: ToolAnomalyBaseline,
        policy: ToolAnomalyPolicy,
    ) -> ToolAnomalyEvaluation:
        if (
            statistics.key.identity
            != baseline.key.identity
        ):
            raise ValueError(
                "Statistics and anomaly baseline "
                "must use the same Analytics key."
            )

        if (
            statistics.total_calls
            < policy.minimum_sample_size
        ):
            return ToolAnomalyEvaluation(
                policy_id=policy.policy_id,
                key=statistics.key.model_copy(
                    deep=True
                ),
                sample_size=statistics.total_calls,
                baseline_sample_size=(
                    baseline.sample_size
                ),
                anomalous=False,
                severity=ToolAnomalySeverity.INFO,
                recommended_action=(
                    ToolAnomalyAction.OBSERVE
                ),
            )

        signals: list[
            ToolAnomalySignal
        ] = []

        total_calls = statistics.total_calls

        retry_rate = (
            statistics.retry_count
            / total_calls
            if total_calls
            else 0
        )
        timeout_rate = (
            statistics.timed_out_calls
            / total_calls
            if total_calls
            else 0
        )
        block_rate = (
            statistics.blocked_calls
            / total_calls
            if total_calls
            else 0
        )

        self._detect_metric(
            signals=signals,
            metric=ToolAnomalyMetric.FAILURE_RATE,
            actual=statistics.failure_rate,
            baseline=baseline.failure_rate,
            multiplier=(
                policy.failure_rate_multiplier
            ),
            absolute_threshold=(
                policy.absolute_failure_rate
            ),
            policy=policy,
        )

        self._detect_metric(
            signals=signals,
            metric=ToolAnomalyMetric.LATENCY,
            actual=statistics.average_latency_ms,
            baseline=baseline.average_latency_ms,
            multiplier=policy.latency_multiplier,
            absolute_threshold=(
                policy.absolute_latency_ms
            ),
            policy=policy,
        )

        self._detect_metric(
            signals=signals,
            metric=ToolAnomalyMetric.RETRY_RATE,
            actual=retry_rate,
            baseline=baseline.retry_rate,
            multiplier=(
                policy.retry_rate_multiplier
            ),
            absolute_threshold=(
                policy.absolute_retry_rate
            ),
            policy=policy,
        )

        self._detect_metric(
            signals=signals,
            metric=ToolAnomalyMetric.COST,
            actual=statistics.average_cost_usd,
            baseline=baseline.average_cost_usd,
            multiplier=policy.cost_multiplier,
            absolute_threshold=(
                policy.absolute_average_cost_usd
            ),
            policy=policy,
        )

        self._detect_metric(
            signals=signals,
            metric=ToolAnomalyMetric.TIMEOUT_RATE,
            actual=timeout_rate,
            baseline=baseline.timeout_rate,
            multiplier=(
                policy.timeout_rate_multiplier
            ),
            absolute_threshold=(
                policy.absolute_timeout_rate
            ),
            policy=policy,
        )

        self._detect_metric(
            signals=signals,
            metric=ToolAnomalyMetric.BLOCK_RATE,
            actual=block_rate,
            baseline=baseline.block_rate,
            multiplier=(
                policy.block_rate_multiplier
            ),
            absolute_threshold=(
                policy.absolute_block_rate
            ),
            policy=policy,
        )

        severity = self._overall_severity(
            signals
        )
        action = self._recommended_action(
            severity=severity,
            policy=policy,
        )

        return ToolAnomalyEvaluation(
            policy_id=policy.policy_id,
            key=statistics.key.model_copy(
                deep=True
            ),
            sample_size=statistics.total_calls,
            baseline_sample_size=(
                baseline.sample_size
            ),
            anomalous=bool(signals),
            severity=severity,
            recommended_action=action,
            signals=signals,
        )

    def _detect_metric(
        self,
        *,
        signals: list[ToolAnomalySignal],
        metric: ToolAnomalyMetric,
        actual: float | Decimal,
        baseline: float | Decimal,
        multiplier: float,
        absolute_threshold: (
            float | Decimal | None
        ),
        policy: ToolAnomalyPolicy,
    ) -> None:
        actual_number = float(actual)
        baseline_number = float(baseline)

        relative_threshold = (
            baseline_number * multiplier
        )

        thresholds = [relative_threshold]

        if absolute_threshold is not None:
            thresholds.append(
                float(absolute_threshold)
            )

        # 두 기준 중 먼저 도달하는 기준을 사용합니다.
        threshold = min(thresholds)

        if actual_number <= threshold:
            return

        if threshold <= 0:
            ratio = (
                actual_number
                if actual_number > 0
                else 0
            )
        else:
            ratio = actual_number / threshold

        score = max(ratio - 1, 0)

        severity = self._signal_severity(
            score=score,
            policy=policy,
        )

        signals.append(
            ToolAnomalySignal(
                metric=metric,
                actual_value=actual,
                baseline_value=baseline,
                threshold_value=threshold,
                ratio=ratio,
                score=score,
                severity=severity,
                message=(
                    f"{metric.value} value {actual} "
                    f"exceeds anomaly threshold "
                    f"{threshold}."
                ),
            )
        )

    def _signal_severity(
        self,
        *,
        score: float,
        policy: ToolAnomalyPolicy,
    ) -> ToolAnomalySeverity:
        if score >= policy.critical_score:
            return ToolAnomalySeverity.CRITICAL

        if score >= policy.high_score:
            return ToolAnomalySeverity.HIGH

        if score >= policy.warning_score:
            return ToolAnomalySeverity.WARNING

        return ToolAnomalySeverity.INFO

    def _overall_severity(
        self,
        signals: list[ToolAnomalySignal],
    ) -> ToolAnomalySeverity:
        if not signals:
            return ToolAnomalySeverity.INFO

        order = {
            ToolAnomalySeverity.INFO: 0,
            ToolAnomalySeverity.WARNING: 1,
            ToolAnomalySeverity.HIGH: 2,
            ToolAnomalySeverity.CRITICAL: 3,
        }

        return max(
            (
                signal.severity
                for signal in signals
            ),
            key=order.__getitem__,
        )

    def _recommended_action(
        self,
        *,
        severity: ToolAnomalySeverity,
        policy: ToolAnomalyPolicy,
    ) -> ToolAnomalyAction:
        order = {
            ToolAnomalySeverity.INFO: 0,
            ToolAnomalySeverity.WARNING: 1,
            ToolAnomalySeverity.HIGH: 2,
            ToolAnomalySeverity.CRITICAL: 3,
        }

        if (
            policy.auto_revoke
            and policy.revoke_at is not None
            and order[severity]
            >= order[policy.revoke_at]
        ):
            return ToolAnomalyAction.REVOKE

        if (
            policy.auto_quarantine
            and order[severity]
            >= order[policy.quarantine_at]
        ):
            return ToolAnomalyAction.QUARANTINE

        if severity is not ToolAnomalySeverity.INFO:
            return ToolAnomalyAction.ALERT

        return ToolAnomalyAction.OBSERVE


class ToolAnomalyPolicyRegistryError(RuntimeError):
    """Raised for invalid anomaly policy registry operations."""


class ToolAnomalyPolicyRegistry:
    def __init__(
        self,
        *,
        default_policy_id: str | None = None,
    ) -> None:
        self._policies: dict[
            str,
            ToolAnomalyPolicy,
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
        policy: ToolAnomalyPolicy,
        *,
        make_default: bool = False,
    ) -> None:
        policy_id = policy.policy_id.strip()

        if not policy_id:
            raise ToolAnomalyPolicyRegistryError(
                "Anomaly policy ID is required."
            )

        if policy_id in self._policies:
            raise ToolAnomalyPolicyRegistryError(
                "Anomaly policy already registered: "
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
        policy: ToolAnomalyPolicy,
    ) -> None:
        policy_id = policy.policy_id.strip()

        if not policy_id:
            raise ToolAnomalyPolicyRegistryError(
                "Anomaly policy ID is required."
            )

        self._policies[policy_id] = (
            policy.model_copy(deep=True)
        )

        if self._default_policy_id is None:
            self._default_policy_id = policy_id

    def get(
        self,
        policy_id: str,
    ) -> ToolAnomalyPolicy:
        try:
            return self._policies[
                policy_id
            ].model_copy(deep=True)
        except KeyError as exc:
            raise ToolAnomalyPolicyRegistryError(
                "Unknown anomaly policy: "
                f"{policy_id}"
            ) from exc

    def bind_tool(
        self,
        *,
        tool_id: str,
        policy_id: str,
    ) -> None:
        tool_id = tool_id.strip()

        if not tool_id:
            raise ToolAnomalyPolicyRegistryError(
                "Tool ID is required."
            )

        if policy_id not in self._policies:
            raise ToolAnomalyPolicyRegistryError(
                "Unknown anomaly policy: "
                f"{policy_id}"
            )

        self._tool_bindings[tool_id] = policy_id

    def unbind_tool(
        self,
        tool_id: str,
    ) -> None:
        if tool_id not in self._tool_bindings:
            raise ToolAnomalyPolicyRegistryError(
                "Tool has no anomaly policy binding: "
                f"{tool_id}"
            )

        del self._tool_bindings[tool_id]

    def policy_for_tool(
        self,
        tool_id: str,
    ) -> ToolAnomalyPolicy:
        policy_id = self._tool_bindings.get(
            tool_id,
            self._default_policy_id,
        )

        if policy_id is None:
            raise ToolAnomalyPolicyRegistryError(
                "No default anomaly policy is "
                f"configured for Tool {tool_id}."
            )

        return self.get(policy_id)

    def set_default(
        self,
        policy_id: str,
    ) -> None:
        if policy_id not in self._policies:
            raise ToolAnomalyPolicyRegistryError(
                "Unknown anomaly policy: "
                f"{policy_id}"
            )

        self._default_policy_id = policy_id

    def list_policies(
        self,
    ) -> list[ToolAnomalyPolicy]:
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


class ToolAnomalyBaselineRegistryError(RuntimeError):
    """Raised for invalid anomaly baseline operations."""


class ToolAnomalyBaselineRegistry:
    def __init__(self) -> None:
        self._baselines: dict[
            tuple[str, str | None, str | None],
            ToolAnomalyBaseline,
        ] = {}

    def register(
        self,
        baseline: ToolAnomalyBaseline,
    ) -> None:
        identity = baseline.key.identity

        if identity in self._baselines:
            raise ToolAnomalyBaselineRegistryError(
                "Anomaly baseline already exists for "
                f"{identity}."
            )

        self._baselines[identity] = (
            baseline.model_copy(deep=True)
        )

    def upsert(
        self,
        baseline: ToolAnomalyBaseline,
    ) -> None:
        self._baselines[
            baseline.key.identity
        ] = baseline.model_copy(deep=True)

    def get(
        self,
        *,
        tool_id: str,
        project_id: str | None = None,
        agent_id: str | None = None,
    ) -> ToolAnomalyBaseline:
        identity = (
            tool_id,
            project_id,
            agent_id,
        )

        try:
            return self._baselines[
                identity
            ].model_copy(deep=True)
        except KeyError as exc:
            raise ToolAnomalyBaselineRegistryError(
                "No anomaly baseline exists for "
                f"{identity}."
            ) from exc

    def find(
        self,
        *,
        tool_id: str,
        project_id: str | None = None,
        agent_id: str | None = None,
    ) -> ToolAnomalyBaseline | None:
        value = self._baselines.get(
            (
                tool_id,
                project_id,
                agent_id,
            )
        )

        if value is None:
            return None

        return value.model_copy(deep=True)

    def remove(
        self,
        *,
        tool_id: str,
        project_id: str | None = None,
        agent_id: str | None = None,
    ) -> None:
        identity = (
            tool_id,
            project_id,
            agent_id,
        )

        if identity not in self._baselines:
            raise ToolAnomalyBaselineRegistryError(
                "No anomaly baseline exists for "
                f"{identity}."
            )

        del self._baselines[identity]

    def list_baselines(
        self,
        *,
        tool_id: str | None = None,
    ) -> list[ToolAnomalyBaseline]:
        values = []

        for baseline in self._baselines.values():
            if (
                tool_id is not None
                and baseline.key.tool_id != tool_id
            ):
                continue

            values.append(
                baseline.model_copy(deep=True)
            )

        return sorted(
            values,
            key=lambda item: (
                item.key.tool_id,
                item.key.project_id or "",
                item.key.agent_id or "",
            ),
        )

    def clear(self) -> None:
        self._baselines.clear()

    def count(self) -> int:
        return len(self._baselines)


class ToolAnomalyWindowComparison(BaseModel):
    baseline: ToolAnomalyBaseline
    current: ToolUsageStatistics
    evaluation: ToolAnomalyEvaluation

    baseline_window_start: datetime | None = None
    baseline_window_end: datetime | None = None
    current_window_start: datetime | None = None
    current_window_end: datetime | None = None

    failure_rate_change: float
    latency_change_ms: float
    retry_rate_change: float
    average_cost_change_usd: Decimal
    timeout_rate_change: float
    block_rate_change: float

    generated_at: datetime = Field(
        default_factory=utc_now
    )


class ToolAnomalyMonitorError(RuntimeError):
    """Raised when anomaly monitoring cannot proceed."""


class ToolAnomalyMonitor:
    def __init__(
        self,
        *,
        policies: ToolAnomalyPolicyRegistry,
        baselines: ToolAnomalyBaselineRegistry,
        detector: ToolAnomalyDetector | None = None,
        maximum_history: int = 10000,
    ) -> None:
        if maximum_history <= 0:
            raise ValueError(
                "maximum_history must be positive."
            )

        self.policies = policies
        self.baselines = baselines
        self.detector = (
            detector
            or ToolAnomalyDetector()
        )
        self.maximum_history = maximum_history

        self._evaluation_counter = 0
        self._latest: dict[
            tuple[str, str | None, str | None],
            ToolAnomalyEvaluation,
        ] = {}
        self._history: list[
            ToolAnomalyHistoryRecord
        ] = []

    def evaluate_statistics(
        self,
        statistics: ToolUsageStatistics,
        *,
        triggered_by_event_id: str | None = None,
    ) -> ToolAnomalyEvaluation:
        policy = self.policies.policy_for_tool(
            statistics.key.tool_id
        )

        baseline = self.baselines.find(
            tool_id=statistics.key.tool_id,
            project_id=statistics.key.project_id,
            agent_id=statistics.key.agent_id,
        )

        if baseline is None:
            raise ToolAnomalyMonitorError(
                "No anomaly baseline exists for "
                f"{statistics.key.identity}."
            )

        evaluation = self.detector.evaluate(
            statistics=statistics,
            baseline=baseline,
            policy=policy,
        )

        self._latest[
            statistics.key.identity
        ] = evaluation.model_copy(
            deep=True
        )

        self._record_history(
            evaluation=evaluation,
            triggered_by_event_id=(
                triggered_by_event_id
            ),
        )

        return evaluation.model_copy(
            deep=True
        )

    def _record_history(
        self,
        *,
        evaluation: ToolAnomalyEvaluation,
        triggered_by_event_id: str | None,
        quarantine_request_id: str | None = None,
        successful: bool = True,
        error: str | None = None,
    ) -> ToolAnomalyHistoryRecord:
        self._evaluation_counter += 1

        record = ToolAnomalyHistoryRecord(
            evaluation_id=(
                f"anomaly-evaluation-"
                f"{self._evaluation_counter}"
            ),
            evaluation=evaluation.model_copy(
                deep=True
            ),
            triggered_by_event_id=(
                triggered_by_event_id
            ),
            quarantine_request_id=(
                quarantine_request_id
            ),
            successful=successful,
            error=error,
        )

        self._history.append(record)

        overflow = (
            len(self._history)
            - self.maximum_history
        )

        if overflow > 0:
            del self._history[:overflow]

        return record.model_copy(deep=True)

    def latest(
        self,
        *,
        tool_id: str,
        project_id: str | None = None,
        agent_id: str | None = None,
    ) -> ToolAnomalyEvaluation | None:
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
    ) -> list[ToolAnomalyEvaluation]:
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

    def history(
        self,
        *,
        tool_id: str | None = None,
        metric: ToolAnomalyMetric | None = None,
        minimum_severity: (
            ToolAnomalySeverity | None
        ) = None,
        anomalous_only: bool = False,
    ) -> list[ToolAnomalyHistoryRecord]:
        severity_order = {
            ToolAnomalySeverity.INFO: 0,
            ToolAnomalySeverity.WARNING: 1,
            ToolAnomalySeverity.HIGH: 2,
            ToolAnomalySeverity.CRITICAL: 3,
        }

        results: list[
            ToolAnomalyHistoryRecord
        ] = []

        for record in self._history:
            evaluation = record.evaluation

            if (
                tool_id is not None
                and evaluation.key.tool_id
                != tool_id
            ):
                continue

            if (
                anomalous_only
                and not evaluation.anomalous
            ):
                continue

            if (
                minimum_severity is not None
                and severity_order[
                    evaluation.severity
                ]
                < severity_order[
                    minimum_severity
                ]
            ):
                continue

            if (
                metric is not None
                and all(
                    signal.metric is not metric
                    for signal in (
                        evaluation.signals
                    )
                )
            ):
                continue

            results.append(
                record.model_copy(deep=True)
            )

        return results

    def history_count(self) -> int:
        return len(self._history)

    def clear_history(self) -> None:
        self._history.clear()


from .tool_usage_analytics import (
    ToolUsageAnalytics,
    ToolUsageSnapshot,
)


class ToolAnomalyWindowAnalyzer:
    def __init__(
        self,
        *,
        analytics: ToolUsageAnalytics,
        detector: ToolAnomalyDetector | None = None,
    ) -> None:
        self.analytics = analytics
        self.detector = (
            detector
            or ToolAnomalyDetector()
        )

    def compare(
        self,
        *,
        tool_id: str,
        project_id: str | None,
        agent_id: str | None,
        baseline_start: datetime,
        baseline_end: datetime,
        current_start: datetime,
        current_end: datetime,
        policy: ToolAnomalyPolicy,
    ) -> ToolAnomalyWindowComparison:
        if baseline_start > baseline_end:
            raise ValueError(
                "Baseline window start must not "
                "be after its end."
            )

        if current_start > current_end:
            raise ValueError(
                "Current window start must not "
                "be after its end."
            )

        baseline_snapshot = self.analytics.snapshot(
            tool_id=tool_id,
            project_id=project_id,
            agent_id=agent_id,
            window_start=baseline_start,
            window_end=baseline_end,
        )

        current_snapshot = self.analytics.snapshot(
            tool_id=tool_id,
            project_id=project_id,
            agent_id=agent_id,
            window_start=current_start,
            window_end=current_end,
        )

        baseline_statistics = (
            self._single_statistics(
                baseline_snapshot,
                label="Baseline",
            )
        )
        current_statistics = (
            self._single_statistics(
                current_snapshot,
                label="Current",
            )
        )

        baseline = (
            self.detector
            .baseline_from_statistics(
                baseline_statistics
            )
        )

        evaluation = self.detector.evaluate(
            statistics=current_statistics,
            baseline=baseline,
            policy=policy,
        )

        baseline_timeout_rate = (
            baseline_statistics.timed_out_calls
            / baseline_statistics.total_calls
            if baseline_statistics.total_calls
            else 0
        )
        current_timeout_rate = (
            current_statistics.timed_out_calls
            / current_statistics.total_calls
            if current_statistics.total_calls
            else 0
        )

        baseline_block_rate = (
            baseline_statistics.blocked_calls
            / baseline_statistics.total_calls
            if baseline_statistics.total_calls
            else 0
        )
        current_block_rate = (
            current_statistics.blocked_calls
            / current_statistics.total_calls
            if current_statistics.total_calls
            else 0
        )

        baseline_retry_rate = (
            baseline_statistics.retry_count
            / baseline_statistics.total_calls
            if baseline_statistics.total_calls
            else 0
        )
        current_retry_rate = (
            current_statistics.retry_count
            / current_statistics.total_calls
            if current_statistics.total_calls
            else 0
        )

        return ToolAnomalyWindowComparison(
            baseline=baseline,
            current=(
                current_statistics.model_copy(
                    deep=True
                )
            ),
            evaluation=evaluation,
            baseline_window_start=baseline_start,
            baseline_window_end=baseline_end,
            current_window_start=current_start,
            current_window_end=current_end,
            failure_rate_change=(
                current_statistics.failure_rate
                - baseline.failure_rate
            ),
            latency_change_ms=(
                current_statistics
                .average_latency_ms
                - baseline.average_latency_ms
            ),
            retry_rate_change=(
                current_retry_rate
                - baseline_retry_rate
            ),
            average_cost_change_usd=(
                current_statistics
                .average_cost_usd
                - baseline.average_cost_usd
            ),
            timeout_rate_change=(
                current_timeout_rate
                - baseline_timeout_rate
            ),
            block_rate_change=(
                current_block_rate
                - baseline_block_rate
            ),
        )

    def _single_statistics(
        self,
        snapshot: ToolUsageSnapshot,
        *,
        label: str,
    ) -> ToolUsageStatistics:
        if not snapshot.statistics:
            raise ToolAnomalyMonitorError(
                f"{label} window has no usage data."
            )

        if len(snapshot.statistics) != 1:
            raise ToolAnomalyMonitorError(
                f"{label} window must resolve to "
                "one Tool/Project/Agent statistic."
            )

        return snapshot.statistics[
            0
        ].model_copy(deep=True)


from collections.abc import (
    Awaitable,
    Callable,
)
import inspect
from typing import Protocol

from .tool_telemetry import (
    InMemoryToolTelemetryStream,
    ToolTelemetryEvent,
)
from .tool_usage_analytics import (
    ToolUsageAnalytics,
)


class ToolQuarantineResult(BaseModel):
    tool_id: str
    requested: bool
    successful: bool

    request_id: str | None = None
    lifecycle_state: str | None = None
    error: str | None = None

    executed_at: datetime = Field(
        default_factory=utc_now
    )


class ToolQuarantineAdapter(Protocol):
    async def quarantine(
        self,
        *,
        tool_id: str,
        reason: str,
        evaluation: ToolAnomalyEvaluation,
    ) -> ToolQuarantineResult:
        """Quarantine a Tool due to an anomaly."""


class ToolAnomalyRealtimeBindingError(RuntimeError):
    """Raised for invalid anomaly real-time bindings."""


class ToolAnomalyAlert(BaseModel):
    alert_id: str
    evaluation: ToolAnomalyEvaluation
    triggered_by_event_id: str | None = None

    quarantine_result: (
        ToolQuarantineResult | None
    ) = None

    created_at: datetime = Field(
        default_factory=utc_now
    )


ToolAnomalyAlertSubscriber = Callable[
    [ToolAnomalyAlert],
    None | Awaitable[None],
]


ToolQuarantineHandler = Callable[
    [
        str,
        str,
        ToolAnomalyEvaluation,
    ],
    (
        ToolQuarantineResult
        | Awaitable[ToolQuarantineResult]
    ),
]


class CallbackToolQuarantineAdapter:
    def __init__(
        self,
        handler: ToolQuarantineHandler,
    ) -> None:
        self.handler = handler

    async def quarantine(
        self,
        *,
        tool_id: str,
        reason: str,
        evaluation: ToolAnomalyEvaluation,
    ) -> ToolQuarantineResult:
        result = self.handler(
            tool_id,
            reason,
            evaluation.model_copy(deep=True),
        )

        if inspect.isawaitable(result):
            result = await result

        if not isinstance(
            result,
            ToolQuarantineResult,
        ):
            raise TypeError(
                "Quarantine handler must return "
                "ToolQuarantineResult."
            )

        return result.model_copy(deep=True)


class ToolAnomalyRealtimeBinding:
    def __init__(
        self,
        *,
        analytics: ToolUsageAnalytics,
        monitor: ToolAnomalyMonitor,
        stream: InMemoryToolTelemetryStream,
        quarantine_adapter: (
            ToolQuarantineAdapter | None
        ) = None,
        subscriber_id: str = (
            "tool-anomaly-monitor"
        ),
        suppress_non_anomalous: bool = True,
        suppress_duplicate_action: bool = True,
    ) -> None:
        subscriber_id = subscriber_id.strip()

        if not subscriber_id:
            raise ValueError(
                "subscriber_id is required."
            )

        self.analytics = analytics
        self.monitor = monitor
        self.stream = stream
        self.quarantine_adapter = (
            quarantine_adapter
        )
        self.subscriber_id = subscriber_id
        self.suppress_non_anomalous = (
            suppress_non_anomalous
        )
        self.suppress_duplicate_action = (
            suppress_duplicate_action
        )

        self._attached = False
        self._alert_counter = 0

        self._subscribers: dict[
            str,
            ToolAnomalyAlertSubscriber,
        ] = {}

        self._acted_identities: set[
            tuple[str, str | None, str | None]
        ] = set()

        self._received_events = 0
        self._evaluated_events = 0
        self._ignored_events = 0
        self._alerts_emitted = 0
        self._quarantine_attempts = 0
        self._quarantine_successes = 0
        self._quarantine_failures = 0

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
            "quarantine_attempts": (
                self._quarantine_attempts
            ),
            "quarantine_successes": (
                self._quarantine_successes
            ),
            "quarantine_failures": (
                self._quarantine_failures
            ),
        }

    def attach(self) -> None:
        if self._attached:
            raise ToolAnomalyRealtimeBindingError(
                "Anomaly real-time binding is "
                "already attached."
            )

        try:
            self.stream.subscribe(
                self.subscriber_id,
                self._on_event,
            )
        except Exception as exc:
            raise ToolAnomalyRealtimeBindingError(
                "Unable to attach anomaly "
                f"real-time binding: {exc}"
            ) from exc

        self._attached = True

    def detach(self) -> None:
        if not self._attached:
            raise ToolAnomalyRealtimeBindingError(
                "Anomaly real-time binding is "
                "not attached."
            )

        try:
            self.stream.unsubscribe(
                self.subscriber_id
            )
        except Exception as exc:
            raise ToolAnomalyRealtimeBindingError(
                "Unable to detach anomaly "
                f"real-time binding: {exc}"
            ) from exc

        self._attached = False

    def subscribe(
        self,
        subscriber_id: str,
        handler: ToolAnomalyAlertSubscriber,
    ) -> None:
        subscriber_id = subscriber_id.strip()

        if not subscriber_id:
            raise ToolAnomalyRealtimeBindingError(
                "Anomaly alert subscriber ID "
                "is required."
            )

        if subscriber_id in self._subscribers:
            raise ToolAnomalyRealtimeBindingError(
                "Anomaly alert subscriber already "
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
            raise ToolAnomalyRealtimeBindingError(
                "Unknown anomaly alert subscriber: "
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

        baseline = self.monitor.baselines.find(
            tool_id=event.tool_id,
            project_id=event.project_id,
            agent_id=event.agent_id,
        )

        if baseline is None:
            self._ignored_events += 1
            return

        self._evaluated_events += 1

        evaluation = (
            self.monitor.evaluate_statistics(
                statistics,
                triggered_by_event_id=(
                    event.event_id
                ),
            )
        )

        if (
            self.suppress_non_anomalous
            and not evaluation.anomalous
        ):
            return

        quarantine_result = (
            await self._apply_action(
                evaluation=evaluation,
            )
        )

        alert = self._build_alert(
            evaluation=evaluation,
            event=event,
            quarantine_result=(
                quarantine_result
            ),
        )

        await self._publish_alert(alert)

    async def _apply_action(
        self,
        *,
        evaluation: ToolAnomalyEvaluation,
    ) -> ToolQuarantineResult | None:
        if not evaluation.quarantine_required:
            return None

        identity = evaluation.key.identity

        if (
            self.suppress_duplicate_action
            and identity in self._acted_identities
        ):
            return ToolQuarantineResult(
                tool_id=evaluation.key.tool_id,
                requested=False,
                successful=True,
                lifecycle_state="ALREADY_QUARANTINED",
            )

        if self.quarantine_adapter is None:
            return ToolQuarantineResult(
                tool_id=evaluation.key.tool_id,
                requested=False,
                successful=False,
                error=(
                    "No quarantine adapter is "
                    "configured."
                ),
            )

        self._quarantine_attempts += 1

        reason = self._quarantine_reason(
            evaluation
        )

        try:
            result = await (
                self.quarantine_adapter
                .quarantine(
                    tool_id=(
                        evaluation.key.tool_id
                    ),
                    reason=reason,
                    evaluation=evaluation,
                )
            )
        except Exception as exc:
            self._quarantine_failures += 1

            return ToolQuarantineResult(
                tool_id=evaluation.key.tool_id,
                requested=True,
                successful=False,
                error=str(exc),
            )

        if result.successful:
            self._quarantine_successes += 1
            self._acted_identities.add(
                identity
            )
        else:
            self._quarantine_failures += 1

        return result

    def _quarantine_reason(
        self,
        evaluation: ToolAnomalyEvaluation,
    ) -> str:
        metrics = ", ".join(
            sorted(
                signal.metric.value
                for signal in (
                    evaluation.signals
                )
            )
        )

        return (
            "Automatic quarantine triggered by "
            f"{evaluation.severity.value} anomaly"
            + (
                f": {metrics}"
                if metrics
                else "."
            )
        )

    def _build_alert(
        self,
        *,
        evaluation: ToolAnomalyEvaluation,
        event: ToolTelemetryEvent,
        quarantine_result: (
            ToolQuarantineResult | None
        ),
    ) -> ToolAnomalyAlert:
        self._alert_counter += 1

        if quarantine_result is not None:
            self.monitor._record_history(
                evaluation=evaluation,
                triggered_by_event_id=(
                    event.event_id
                ),
                quarantine_request_id=(
                    quarantine_result.request_id
                ),
                successful=(
                    quarantine_result.successful
                ),
                error=quarantine_result.error,
            )

        return ToolAnomalyAlert(
            alert_id=(
                f"anomaly-alert-"
                f"{self._alert_counter}"
            ),
            evaluation=(
                evaluation.model_copy(
                    deep=True
                )
            ),
            triggered_by_event_id=(
                event.event_id
            ),
            quarantine_result=(
                quarantine_result.model_copy(
                    deep=True
                )
                if quarantine_result
                is not None
                else None
            ),
        )

    async def _publish_alert(
        self,
        alert: ToolAnomalyAlert,
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

    def reset_action(
        self,
        *,
        tool_id: str,
        project_id: str | None = None,
        agent_id: str | None = None,
    ) -> None:
        self._acted_identities.discard(
            (
                tool_id,
                project_id,
                agent_id,
            )
        )

    def __enter__(
        self,
    ) -> ToolAnomalyRealtimeBinding:
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


class ToolInstallationRequestResolver(Protocol):
    def resolve_request_id(
        self,
        *,
        tool_id: str,
    ) -> str | None | Awaitable[str | None]:
        """Resolve the active installation request for a Tool."""


ToolInstallationRequestHandler = Callable[
    [str],
    str | None | Awaitable[str | None],
]


class CallbackInstallationRequestResolver:
    def __init__(
        self,
        handler: ToolInstallationRequestHandler,
    ) -> None:
        self.handler = handler

    async def resolve_request_id(
        self,
        *,
        tool_id: str,
    ) -> str | None:
        result = self.handler(tool_id)

        if inspect.isawaitable(result):
            result = await result

        if result is None:
            return None

        request_id = str(result).strip()

        return request_id or None


class LifecycleToolQuarantineAdapter:
    def __init__(
        self,
        *,
        orchestrator,
        request_resolver: (
            ToolInstallationRequestResolver
        ),
        actor: str = "anomaly-monitor",
    ) -> None:
        self.orchestrator = orchestrator
        self.request_resolver = request_resolver
        self.actor = actor

    async def quarantine(
        self,
        *,
        tool_id: str,
        reason: str,
        evaluation: ToolAnomalyEvaluation,
    ) -> ToolQuarantineResult:
        request_id = await (
            self.request_resolver
            .resolve_request_id(
                tool_id=tool_id
            )
        )

        if request_id is None:
            return ToolQuarantineResult(
                tool_id=tool_id,
                requested=False,
                successful=False,
                error=(
                    "No active installation request "
                    f"was found for Tool {tool_id}."
                ),
            )

        quarantine_method = getattr(
            self.orchestrator,
            "quarantine",
            None,
        )

        if quarantine_method is None:
            return ToolQuarantineResult(
                tool_id=tool_id,
                requested=False,
                successful=False,
                request_id=request_id,
                error=(
                    "Installation orchestrator has no "
                    "quarantine() method."
                ),
            )

        kwargs = self._supported_kwargs(
            method=quarantine_method,
            tool_id=tool_id,
            request_id=request_id,
            reason=reason,
            evaluation=evaluation,
        )

        try:
            result = quarantine_method(**kwargs)

            if inspect.isawaitable(result):
                result = await result

        except Exception as exc:
            return ToolQuarantineResult(
                tool_id=tool_id,
                requested=True,
                successful=False,
                request_id=request_id,
                error=str(exc),
            )

        lifecycle_state = self._extract_state(
            result
        )

        if lifecycle_state is None:
            lifecycle_state = await (
                self._resolve_lifecycle_state(
                    request_id=request_id
                )
            )

        successful = (
            lifecycle_state == "QUARANTINED"
            or self._result_successful(result)
        )

        return ToolQuarantineResult(
            tool_id=tool_id,
            requested=True,
            successful=successful,
            request_id=request_id,
            lifecycle_state=lifecycle_state,
            error=(
                None
                if successful
                else (
                    "Lifecycle quarantine did not "
                    "reach QUARANTINED state."
                )
            ),
        )

    async def _resolve_lifecycle_state(
        self,
        *,
        request_id: str,
    ) -> str | None:
        for source in (
            self.orchestrator,
            getattr(
                self.orchestrator,
                "lifecycle",
                None,
            ),
        ):
            if source is None:
                continue

            for method_name in (
                "get",
                "get_case",
                "case",
                "find",
            ):
                method = getattr(
                    source,
                    method_name,
                    None,
                )

                if not callable(method):
                    continue

                try:
                    result = method(request_id)
                except TypeError:
                    try:
                        result = method(
                            request_id=request_id
                        )
                    except TypeError:
                        continue
                except Exception:
                    continue

                if inspect.isawaitable(result):
                    result = await result

                state = self._extract_state(
                    result
                )

                if state is not None:
                    return state

        return None

    def _supported_kwargs(
        self,
        *,
        method,
        tool_id: str,
        request_id: str,
        reason: str,
        evaluation: ToolAnomalyEvaluation,
    ) -> dict:
        signature = inspect.signature(method)
        parameters = signature.parameters

        candidates = {
            "tool_id": tool_id,
            "ecosystem_id": tool_id,
            "request_id": request_id,
            "installation_request_id": request_id,
            "case_id": request_id,
            "reason": reason,
            "quarantined_reason": reason,
            "actor": self.actor,
            "requested_by": self.actor,
            "evaluation": evaluation.model_copy(
                deep=True
            ),
            "metadata": {
                "source": "tool-anomaly-monitor",
                "policy_id": evaluation.policy_id,
                "severity": evaluation.severity.value,
                "metrics": [
                    signal.metric.value
                    for signal in evaluation.signals
                ],
            },
        }

        accepts_var_kwargs = any(
            parameter.kind
            is inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )

        if accepts_var_kwargs:
            return candidates

        return {
            name: value
            for name, value in candidates.items()
            if name in parameters
        }

    def _extract_state(
        self,
        result,
    ) -> str | None:
        if result is None:
            return self._lookup_state()

        for attribute in (
            "state",
            "lifecycle_state",
            "installation_state",
            "status",
        ):
            value = getattr(
                result,
                attribute,
                None,
            )

            if value is not None:
                return self._normalize_state(
                    value
                )

        if isinstance(result, dict):
            for key in (
                "state",
                "lifecycle_state",
                "installation_state",
                "status",
            ):
                if key in result:
                    return self._normalize_state(
                        result[key]
                    )

        return self._lookup_state()

    def _lookup_state(
        self,
    ) -> str | None:
        return None

    def _normalize_state(
        self,
        value,
    ) -> str:
        enum_value = getattr(
            value,
            "value",
            value,
        )

        return str(enum_value).upper()

    def _result_successful(
        self,
        result,
    ) -> bool:
        if result is None:
            return False

        for attribute in (
            "successful",
            "success",
            "quarantined",
        ):
            value = getattr(
                result,
                attribute,
                None,
            )

            if value is not None:
                return bool(value)

        if isinstance(result, dict):
            for key in (
                "successful",
                "success",
                "quarantined",
            ):
                if key in result:
                    return bool(result[key])

        return False


class LifecycleRegistryInstallationRequestResolver:
    def __init__(
        self,
        *,
        lifecycle,
    ) -> None:
        self.lifecycle = lifecycle

    async def resolve_request_id(
        self,
        *,
        tool_id: str,
    ) -> str | None:
        cases = await self._list_cases()

        matches = [
            case
            for case in cases
            if self._case_tool_id(case) == tool_id
        ]

        if not matches:
            return None

        active = [
            case
            for case in matches
            if not self._is_terminal_removed(case)
        ]

        candidates = active or matches

        candidates.sort(
            key=self._case_timestamp,
            reverse=True,
        )

        return self._case_request_id(
            candidates[0]
        )

    async def _list_cases(self) -> list:
        for method_name in (
            "list_cases",
            "cases",
            "list",
            "all_cases",
        ):
            method = getattr(
                self.lifecycle,
                method_name,
                None,
            )

            if not callable(method):
                continue

            try:
                result = method()
            except TypeError:
                continue

            if inspect.isawaitable(result):
                result = await result

            values = self._normalize_collection(
                result
            )

            if values is not None:
                return values

        for attribute_name in (
            "_cases",
            "cases",
            "_installation_cases",
            "installation_cases",
        ):
            value = getattr(
                self.lifecycle,
                attribute_name,
                None,
            )

            values = self._normalize_collection(
                value
            )

            if values is not None:
                return values

        raise ToolAnomalyRealtimeBindingError(
            "Unable to enumerate installation "
            "Lifecycle cases."
        )

    def _normalize_collection(
        self,
        value,
    ) -> list | None:
        if value is None:
            return None

        if isinstance(value, dict):
            return list(value.values())

        if isinstance(
            value,
            (list, tuple, set),
        ):
            return list(value)

        return None

    def _case_tool_id(
        self,
        case,
    ) -> str | None:
        request = getattr(
            case,
            "request",
            None,
        )

        for source in (
            request,
            case,
        ):
            if source is None:
                continue

            for attribute in (
                "ecosystem_id",
                "tool_id",
                "manifest_id",
            ):
                value = getattr(
                    source,
                    attribute,
                    None,
                )

                if value:
                    return str(value)

            if isinstance(source, dict):
                for key in (
                    "ecosystem_id",
                    "tool_id",
                    "manifest_id",
                ):
                    if source.get(key):
                        return str(source[key])

        return None

    def _case_request_id(
        self,
        case,
    ) -> str | None:
        request = getattr(
            case,
            "request",
            None,
        )

        for source in (
            request,
            case,
        ):
            if source is None:
                continue

            for attribute in (
                "request_id",
                "case_id",
                "installation_request_id",
                "id",
            ):
                value = getattr(
                    source,
                    attribute,
                    None,
                )

                if value:
                    return str(value)

            if isinstance(source, dict):
                for key in (
                    "request_id",
                    "case_id",
                    "installation_request_id",
                    "id",
                ):
                    if source.get(key):
                        return str(source[key])

        return None

    def _case_state(
        self,
        case,
    ) -> str | None:
        for attribute in (
            "state",
            "lifecycle_state",
            "installation_state",
            "status",
        ):
            value = getattr(
                case,
                attribute,
                None,
            )

            if value is not None:
                return str(
                    getattr(value, "value", value)
                ).upper()

        if isinstance(case, dict):
            for key in (
                "state",
                "lifecycle_state",
                "installation_state",
                "status",
            ):
                if key in case:
                    value = case[key]
                    return str(
                        getattr(
                            value,
                            "value",
                            value,
                        )
                    ).upper()

        return None

    def _is_terminal_removed(
        self,
        case,
    ) -> bool:
        return self._case_state(case) in {
            "REMOVED",
            "REVOKED",
        }

    def _case_timestamp(
        self,
        case,
    ) -> datetime:
        for attribute in (
            "updated_at",
            "created_at",
            "requested_at",
        ):
            value = getattr(
                case,
                attribute,
                None,
            )

            if isinstance(value, datetime):
                return value

        return datetime.min.replace(
            tzinfo=timezone.utc
        )
