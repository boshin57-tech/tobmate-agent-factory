"""Bounded thread-safe production service metrics."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from threading import RLock
from typing import Mapping

from .service_runtime import (
    ServiceRuntime,
    ServiceState,
)


PROMETHEUS_CONTENT_TYPE = (
    "text/plain; version=0.0.4; charset=utf-8"
)

_METRIC_NAME = re.compile(
    r"^[a-zA-Z_:][a-zA-Z0-9_:]*$"
)
_LABEL_NAME = re.compile(
    r"^[a-zA-Z_][a-zA-Z0-9_]*$"
)


class MetricsRegistryError(RuntimeError):
    """Raised for invalid metric definitions or operations."""


class MetricType(StrEnum):
    """Supported production metric types."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


@dataclass(frozen=True, slots=True)
class MetricPoint:
    """Counter or gauge point."""

    labels: tuple[tuple[str, str], ...]
    value: float


@dataclass(frozen=True, slots=True)
class HistogramPoint:
    """Cumulative histogram point."""

    labels: tuple[tuple[str, str], ...]
    count: int
    total: float
    buckets: tuple[tuple[float, int], ...]


@dataclass(frozen=True, slots=True)
class MetricSnapshot:
    """Immutable snapshot for one metric."""

    name: str
    metric_type: MetricType
    help_text: str
    label_names: tuple[str, ...]
    points: tuple[
        MetricPoint | HistogramPoint,
        ...,
    ]


class _MetricBase:
    def __init__(
        self,
        *,
        name: str,
        help_text: str,
        label_names: tuple[str, ...],
        maximum_series: int,
    ) -> None:
        self.name = name
        self.help_text = help_text
        self.label_names = label_names
        self.maximum_series = maximum_series
        self._lock = RLock()

    def _key(
        self,
        labels: Mapping[str, str] | None,
        *,
        existing_keys: set[tuple[str, ...]],
    ) -> tuple[str, ...]:
        supplied = dict(labels or {})

        if set(supplied) != set(self.label_names):
            expected = ", ".join(
                self.label_names
            )

            raise MetricsRegistryError(
                "metric labels must exactly match: "
                f"{expected}"
            )

        values: list[str] = []

        for name in self.label_names:
            value = str(supplied[name])

            if (
                len(value) > 256
                or "\0" in value
                or "\r" in value
            ):
                raise MetricsRegistryError(
                    "invalid metric label value: "
                    f"{name}"
                )

            values.append(value)

        key = tuple(values)

        if (
            key not in existing_keys
            and len(existing_keys)
            >= self.maximum_series
        ):
            raise MetricsRegistryError(
                "metric series cardinality "
                "limit exceeded"
            )

        return key

    def _label_pairs(
        self,
        key: tuple[str, ...],
    ) -> tuple[tuple[str, str], ...]:
        return tuple(
            zip(
                self.label_names,
                key,
                strict=True,
            )
        )


class Counter(_MetricBase):
    """Monotonically increasing numeric counter."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._values: dict[
            tuple[str, ...],
            float,
        ] = {}

    def inc(
        self,
        amount: float = 1.0,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        value = float(amount)

        if (
            not math.isfinite(value)
            or value < 0
        ):
            raise MetricsRegistryError(
                "counter increment must be finite "
                "and non-negative"
            )

        with self._lock:
            key = self._key(
                labels,
                existing_keys=set(self._values),
            )

            self._values[key] = (
                self._values.get(key, 0.0)
                + value
            )

    def value(
        self,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> float:
        with self._lock:
            key = self._key(
                labels,
                existing_keys=set(self._values),
            )

            return self._values.get(
                key,
                0.0,
            )

    def snapshot(self) -> MetricSnapshot:
        with self._lock:
            points = tuple(
                MetricPoint(
                    labels=self._label_pairs(key),
                    value=value,
                )
                for key, value in sorted(
                    self._values.items()
                )
            )

        return MetricSnapshot(
            name=self.name,
            metric_type=MetricType.COUNTER,
            help_text=self.help_text,
            label_names=self.label_names,
            points=points,
        )


class Gauge(_MetricBase):
    """Numeric gauge supporting set, increment and decrement."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._values: dict[
            tuple[str, ...],
            float,
        ] = {}

    def set(
        self,
        value: float,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        number = float(value)

        if not math.isfinite(number):
            raise MetricsRegistryError(
                "gauge value must be finite"
            )

        with self._lock:
            key = self._key(
                labels,
                existing_keys=set(self._values),
            )
            self._values[key] = number

    def inc(
        self,
        amount: float = 1.0,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        value = float(amount)

        if not math.isfinite(value):
            raise MetricsRegistryError(
                "gauge increment must be finite"
            )

        with self._lock:
            key = self._key(
                labels,
                existing_keys=set(self._values),
            )

            self._values[key] = (
                self._values.get(key, 0.0)
                + value
            )

    def dec(
        self,
        amount: float = 1.0,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        self.inc(
            -float(amount),
            labels=labels,
        )

    def value(
        self,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> float:
        with self._lock:
            key = self._key(
                labels,
                existing_keys=set(self._values),
            )

            return self._values.get(
                key,
                0.0,
            )

    def snapshot(self) -> MetricSnapshot:
        with self._lock:
            points = tuple(
                MetricPoint(
                    labels=self._label_pairs(key),
                    value=value,
                )
                for key, value in sorted(
                    self._values.items()
                )
            )

        return MetricSnapshot(
            name=self.name,
            metric_type=MetricType.GAUGE,
            help_text=self.help_text,
            label_names=self.label_names,
            points=points,
        )


class Histogram(_MetricBase):
    """Cumulative fixed-bucket histogram."""

    def __init__(
        self,
        *,
        buckets: tuple[float, ...],
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)

        normalized = tuple(
            sorted(
                {
                    float(bucket)
                    for bucket in buckets
                }
            )
        )

        if (
            not normalized
            or any(
                not math.isfinite(bucket)
                for bucket in normalized
            )
        ):
            raise MetricsRegistryError(
                "histogram buckets must be "
                "non-empty and finite"
            )

        self.buckets = normalized
        self._values: dict[
            tuple[str, ...],
            tuple[int, float, list[int]],
        ] = {}

    def observe(
        self,
        value: float,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        number = float(value)

        if not math.isfinite(number):
            raise MetricsRegistryError(
                "histogram observation "
                "must be finite"
            )

        with self._lock:
            key = self._key(
                labels,
                existing_keys=set(self._values),
            )

            count, total, counts = (
                self._values.get(
                    key,
                    (
                        0,
                        0.0,
                        [
                            0
                            for _ in self.buckets
                        ],
                    ),
                )
            )

            updated = list(counts)

            for index, bucket in enumerate(
                self.buckets
            ):
                if number <= bucket:
                    updated[index] += 1

            self._values[key] = (
                count + 1,
                total + number,
                updated,
            )

    def snapshot(self) -> MetricSnapshot:
        with self._lock:
            points = tuple(
                HistogramPoint(
                    labels=self._label_pairs(key),
                    count=count,
                    total=total,
                    buckets=tuple(
                        zip(
                            self.buckets,
                            counts,
                            strict=True,
                        )
                    ),
                )
                for key, (
                    count,
                    total,
                    counts,
                ) in sorted(
                    self._values.items()
                )
            )

        return MetricSnapshot(
            name=self.name,
            metric_type=MetricType.HISTOGRAM,
            help_text=self.help_text,
            label_names=self.label_names,
            points=points,
        )


class MetricsRegistry:
    """Register bounded metrics and render Prometheus text."""

    def __init__(
        self,
        *,
        maximum_labels: int = 8,
        maximum_series_per_metric: int = 1000,
    ) -> None:
        if maximum_labels < 0:
            raise ValueError(
                "maximum_labels must not be negative"
            )

        if maximum_series_per_metric <= 0:
            raise ValueError(
                "maximum_series_per_metric "
                "must be positive"
            )

        self.maximum_labels = maximum_labels
        self.maximum_series_per_metric = (
            maximum_series_per_metric
        )
        self._metrics: dict[
            str,
            Counter | Gauge | Histogram,
        ] = {}
        self._lock = RLock()

    def counter(
        self,
        name: str,
        help_text: str,
        *,
        label_names: tuple[str, ...] = (),
    ) -> Counter:
        metric = Counter(
            **self._common(
                name,
                help_text,
                label_names,
            )
        )
        return self._register(metric)

    def gauge(
        self,
        name: str,
        help_text: str,
        *,
        label_names: tuple[str, ...] = (),
    ) -> Gauge:
        metric = Gauge(
            **self._common(
                name,
                help_text,
                label_names,
            )
        )
        return self._register(metric)

    def histogram(
        self,
        name: str,
        help_text: str,
        *,
        buckets: tuple[float, ...],
        label_names: tuple[str, ...] = (),
    ) -> Histogram:
        metric = Histogram(
            buckets=buckets,
            **self._common(
                name,
                help_text,
                label_names,
            ),
        )
        return self._register(metric)

    def collect(
        self,
    ) -> tuple[MetricSnapshot, ...]:
        with self._lock:
            metrics = tuple(
                self._metrics[name]
                for name in sorted(
                    self._metrics
                )
            )

        return tuple(
            metric.snapshot()
            for metric in metrics
        )

    def render_prometheus(self) -> str:
        lines: list[str] = []

        for snapshot in self.collect():
            lines.append(
                f"# HELP {snapshot.name} "
                f"{self._escape_help(snapshot.help_text)}"
            )
            lines.append(
                f"# TYPE {snapshot.name} "
                f"{snapshot.metric_type.value}"
            )

            for point in snapshot.points:
                if isinstance(
                    point,
                    MetricPoint,
                ):
                    lines.append(
                        f"{snapshot.name}"
                        f"{self._render_labels(point.labels)} "
                        f"{self._number(point.value)}"
                    )
                    continue

                for bucket, count in point.buckets:
                    labels = (
                        point.labels
                        + (
                            (
                                "le",
                                self._number(bucket),
                            ),
                        )
                    )

                    lines.append(
                        f"{snapshot.name}_bucket"
                        f"{self._render_labels(labels)} "
                        f"{count}"
                    )

                infinite_labels = (
                    point.labels
                    + (("le", "+Inf"),)
                )

                lines.append(
                    f"{snapshot.name}_bucket"
                    f"{self._render_labels(infinite_labels)} "
                    f"{point.count}"
                )
                lines.append(
                    f"{snapshot.name}_sum"
                    f"{self._render_labels(point.labels)} "
                    f"{self._number(point.total)}"
                )
                lines.append(
                    f"{snapshot.name}_count"
                    f"{self._render_labels(point.labels)} "
                    f"{point.count}"
                )

        return "\n".join(lines) + (
            "\n" if lines else ""
        )

    def _common(
        self,
        name: str,
        help_text: str,
        label_names: tuple[str, ...],
    ) -> dict[str, object]:
        normalized_name = name.strip()
        normalized_help = help_text.strip()

        if not _METRIC_NAME.fullmatch(
            normalized_name
        ):
            raise MetricsRegistryError(
                f"invalid metric name: {name}"
            )

        if not normalized_help:
            raise MetricsRegistryError(
                "metric help text must not be empty"
            )

        labels = tuple(label_names)

        if len(labels) > self.maximum_labels:
            raise MetricsRegistryError(
                "metric label limit exceeded"
            )

        if len(labels) != len(set(labels)):
            raise MetricsRegistryError(
                "metric label names must be unique"
            )

        for label in labels:
            if not _LABEL_NAME.fullmatch(label):
                raise MetricsRegistryError(
                    "invalid metric label name: "
                    f"{label}"
                )

        return {
            "name": normalized_name,
            "help_text": normalized_help,
            "label_names": labels,
            "maximum_series": (
                self.maximum_series_per_metric
            ),
        }

    def _register(self, metric):
        with self._lock:
            if metric.name in self._metrics:
                raise MetricsRegistryError(
                    f"duplicate metric: {metric.name}"
                )

            self._metrics[metric.name] = metric

        return metric

    @staticmethod
    def _render_labels(
        labels: tuple[tuple[str, str], ...],
    ) -> str:
        if not labels:
            return ""

        content = ",".join(
            f'{name}="'
            f'{MetricsRegistry._escape_label(value)}"'
            for name, value in labels
        )

        return "{" + content + "}"

    @staticmethod
    def _escape_label(value: str) -> str:
        return (
            value.replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace('"', '\\"')
        )

    @staticmethod
    def _escape_help(value: str) -> str:
        return (
            value.replace("\\", "\\\\")
            .replace("\n", "\\n")
        )

    @staticmethod
    def _number(value: float) -> str:
        if value.is_integer():
            return str(int(value))

        return format(
            value,
            ".15g",
        )


class ServiceRuntimeMetricsAdapter:
    """Record credential-free ServiceRuntime lifecycle metrics."""

    def __init__(
        self,
        runtime: ServiceRuntime,
        registry: MetricsRegistry,
    ) -> None:
        self.runtime = runtime
        self.registry = registry
        self._last_state: ServiceState | None = None

        self.state = registry.gauge(
            "af_core_service_state",
            "Current AF-Core service lifecycle state.",
            label_names=("state",),
        )
        self.registered_resources = registry.gauge(
            "af_core_service_registered_resources",
            "Number of registered service resources.",
        )
        self.started_resources = registry.gauge(
            "af_core_service_started_resources",
            "Number of started service resources.",
        )
        self.shutdown_requested = registry.gauge(
            "af_core_service_shutdown_requested",
            "Whether graceful shutdown was requested.",
        )
        self.state_transitions = registry.counter(
            "af_core_service_state_transitions_total",
            "Observed AF-Core service state transitions.",
            label_names=("state",),
        )

    def observe(self) -> None:
        snapshot = self.runtime.snapshot()

        for state in ServiceState:
            self.state.set(
                1.0
                if snapshot.state is state
                else 0.0,
                labels={
                    "state": state.value,
                },
            )

        self.registered_resources.set(
            float(
                len(
                    snapshot.registered_resources
                )
            )
        )
        self.started_resources.set(
            float(
                len(
                    snapshot.started_resources
                )
            )
        )
        self.shutdown_requested.set(
            1.0
            if snapshot.shutdown_requested
            else 0.0
        )

        if snapshot.state is not self._last_state:
            self.state_transitions.inc(
                labels={
                    "state": snapshot.state.value,
                }
            )
            self._last_state = snapshot.state
