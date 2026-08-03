from __future__ import annotations

from .agent_runtime_metrics import (
    AgentRuntimeMetrics,
)


class AgentRuntimeMetricsRepository:
    """
    In-memory repository for current Agent operational metrics.

    Production adapters may later load these metrics from monitoring,
    Redis, a database, or an external observability system.
    """

    def __init__(self) -> None:
        self._metrics: dict[
            str,
            AgentRuntimeMetrics,
        ] = {}

    def upsert(
        self,
        metrics: AgentRuntimeMetrics,
    ) -> AgentRuntimeMetrics:
        self._metrics[
            metrics.agent_id
        ] = metrics

        return metrics

    def get(
        self,
        agent_id: str,
    ) -> AgentRuntimeMetrics | None:
        return self._metrics.get(
            agent_id
        )

    def remove(
        self,
        agent_id: str,
    ) -> bool:
        return (
            self._metrics.pop(
                agent_id,
                None,
            )
            is not None
        )

    def all(
        self,
    ) -> tuple[
        AgentRuntimeMetrics,
        ...
    ]:
        return tuple(
            self._metrics.values()
        )

    @property
    def count(self) -> int:
        return len(
            self._metrics
        )
