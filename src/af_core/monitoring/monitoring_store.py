from __future__ import annotations

from .monitoring_models import (
    ExecutionMetric,
)



class MonitoringStore:
    """
    Stores collected monitoring data.
    """


    def __init__(self) -> None:

        self._records: list[
            ExecutionMetric
        ] = []



    def save(
        self,
        metric:
        ExecutionMetric,
    ) -> None:

        self._records.append(
            metric
        )



    def query(
        self,
        project_id: str,
    ) -> tuple[
        ExecutionMetric,
        ...
    ]:

        return tuple(
            record
            for record
            in self._records
            if record.project_id
            == project_id
        )
