from __future__ import annotations

from .monitoring_models import (
    ExecutionMetric,
)


class MetricsCollector:
    """
    Collects runtime metrics from
    Agent Factory execution.
    """


    def __init__(self) -> None:

        self._metrics: list[
            ExecutionMetric
        ] = []



    def record(
        self,
        metric:
        ExecutionMetric,
    ) -> ExecutionMetric:

        self._metrics.append(
            metric
        )

        return metric



    def all(
        self,
    ) -> tuple[
        ExecutionMetric,
        ...
    ]:

        return tuple(
            self._metrics
        )



    def count(
        self,
    ) -> int:

        return len(
            self._metrics
        )
