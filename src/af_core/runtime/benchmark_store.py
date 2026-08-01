from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from .benchmark_models import (
    BenchmarkAggregate,
    BenchmarkResult,
    BenchmarkStatus,
    BenchmarkTaskType,
)


class BenchmarkStoreError(RuntimeError):
    """Raised when benchmark persistence fails."""


class BenchmarkStore:
    def __init__(
        self,
        path: str | Path | None = None,
    ) -> None:
        self.path = (
            Path(path).expanduser().resolve()
            if path is not None
            else None
        )
        self._results: list[BenchmarkResult] = []

        if self.path is not None and self.path.is_file():
            self.load()

    def add(
        self,
        result: BenchmarkResult,
    ) -> None:
        self._results.append(result)

    def extend(
        self,
        results: list[BenchmarkResult],
    ) -> None:
        self._results.extend(results)

    def results(
        self,
        *,
        provider_id: str | None = None,
        model_key: str | None = None,
        task_type: BenchmarkTaskType | None = None,
    ) -> list[BenchmarkResult]:
        selected: list[BenchmarkResult] = []

        for result in self._results:
            if (
                provider_id is not None
                and result.provider_id != provider_id
            ):
                continue

            if (
                model_key is not None
                and result.model_key != model_key
            ):
                continue

            if (
                task_type is not None
                and result.task_type is not task_type
            ):
                continue

            selected.append(result)

        return list(selected)

    def aggregate(
        self,
        *,
        task_type: BenchmarkTaskType | None = None,
    ) -> list[BenchmarkAggregate]:
        grouped: dict[
            tuple[str, str, BenchmarkTaskType],
            list[BenchmarkResult],
        ] = defaultdict(list)

        for result in self._results:
            if (
                task_type is not None
                and result.task_type is not task_type
            ):
                continue

            grouped[
                (
                    result.provider_id,
                    result.model_key,
                    result.task_type,
                )
            ].append(result)

        aggregates: list[BenchmarkAggregate] = []

        for (
            provider_id,
            model_key,
            grouped_task_type,
        ), results in grouped.items():
            count = len(results)
            successes = sum(
                result.status is BenchmarkStatus.PASSED
                for result in results
            )

            average_cost = (
                sum(
                    (
                        result.execution.cost_usd
                        for result in results
                    ),
                    Decimal("0"),
                )
                / Decimal(count)
            )

            aggregates.append(
                BenchmarkAggregate(
                    provider_id=provider_id,
                    model_key=model_key,
                    task_type=grouped_task_type,
                    sample_count=count,
                    success_count=successes,
                    failure_count=count - successes,
                    success_rate=round(
                        successes / count * 100.0,
                        4,
                    ),
                    average_quality_score=round(
                        sum(
                            result.quality.aggregate()
                            for result in results
                        )
                        / count,
                        4,
                    ),
                    average_latency_ms=round(
                        sum(
                            result.execution.latency_ms
                            for result in results
                        )
                        / count,
                        4,
                    ),
                    average_cost_usd=average_cost,
                    average_retry_count=round(
                        sum(
                            result.execution.retry_count
                            for result in results
                        )
                        / count,
                        4,
                    ),
                    average_tokens_per_second=round(
                        sum(
                            result.execution.tokens_per_second
                            for result in results
                        )
                        / count,
                        4,
                    ),
                )
            )

        return sorted(
            aggregates,
            key=lambda item: (
                item.task_type.value,
                item.model_key,
            ),
        )

    def save(self) -> Path:
        if self.path is None:
            raise BenchmarkStoreError(
                "Benchmark store path is not configured."
            )

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary = self.path.with_suffix(
            self.path.suffix + ".tmp"
        )
        temporary.write_text(
            json.dumps(
                [
                    result.model_dump(mode="json")
                    for result in self._results
                ],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)

        return self.path

    def load(self) -> None:
        if self.path is None:
            raise BenchmarkStoreError(
                "Benchmark store path is not configured."
            )

        try:
            payload = json.loads(
                self.path.read_text(encoding="utf-8")
            )
        except (
            OSError,
            json.JSONDecodeError,
        ) as exc:
            raise BenchmarkStoreError(
                f"Unable to load benchmark store: {exc}"
            ) from exc

        if not isinstance(payload, list):
            raise BenchmarkStoreError(
                "Benchmark store payload must be a list."
            )

        self._results = [
            BenchmarkResult.model_validate(item)
            for item in payload
        ]
