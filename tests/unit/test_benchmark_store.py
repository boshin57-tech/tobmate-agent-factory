from decimal import Decimal
from pathlib import Path

from af_core.runtime.benchmark_models import (
    BenchmarkExecutionMetrics,
    BenchmarkResult,
    BenchmarkStatus,
    BenchmarkTaskType,
    QualityMetrics,
)
from af_core.runtime.benchmark_store import BenchmarkStore


def result(
    *,
    benchmark_id: str,
    provider_id: str,
    model_key: str,
    status: BenchmarkStatus,
    quality: float,
    latency: float,
    cost: str,
) -> BenchmarkResult:
    return BenchmarkResult(
        benchmark_id=benchmark_id,
        scenario_id="scenario-1",
        task_type=BenchmarkTaskType.CODING,
        provider_id=provider_id,
        model_key=model_key,
        provider_model_id=model_key,
        status=status,
        quality=QualityMetrics(
            correctness_score=quality,
            structure_score=quality,
            tool_success_score=quality,
            test_pass_score=quality,
            review_score=quality,
        ),
        execution=BenchmarkExecutionMetrics(
            latency_ms=latency,
            output_tokens=100,
            cost_usd=Decimal(cost),
        ),
    )


def test_store_filters_and_aggregates() -> None:
    store = BenchmarkStore()

    store.extend(
        [
            result(
                benchmark_id="b1",
                provider_id="p1",
                model_key="m1",
                status=BenchmarkStatus.PASSED,
                quality=100,
                latency=100,
                cost="0.01",
            ),
            result(
                benchmark_id="b2",
                provider_id="p1",
                model_key="m1",
                status=BenchmarkStatus.FAILED,
                quality=50,
                latency=300,
                cost="0.03",
            ),
        ]
    )

    assert len(
        store.results(provider_id="p1")
    ) == 2

    aggregate = store.aggregate()[0]

    assert aggregate.sample_count == 2
    assert aggregate.success_count == 1
    assert aggregate.failure_count == 1
    assert aggregate.success_rate == 50.0
    assert aggregate.average_quality_score == 75.0
    assert aggregate.average_latency_ms == 200.0
    assert aggregate.average_cost_usd == Decimal("0.02")


def test_store_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "benchmarks.json"
    store = BenchmarkStore(path)

    store.add(
        result(
            benchmark_id="b1",
            provider_id="p1",
            model_key="m1",
            status=BenchmarkStatus.PASSED,
            quality=100,
            latency=100,
            cost="0.01",
        )
    )
    store.save()

    restored = BenchmarkStore(path)

    assert len(restored.results()) == 1
    assert restored.results()[0].benchmark_id == "b1"


def test_results_returns_copy() -> None:
    store = BenchmarkStore()
    store.add(
        result(
            benchmark_id="b1",
            provider_id="p1",
            model_key="m1",
            status=BenchmarkStatus.PASSED,
            quality=100,
            latency=100,
            cost="0.01",
        )
    )

    returned = store.results()
    returned.clear()

    assert len(store.results()) == 1
