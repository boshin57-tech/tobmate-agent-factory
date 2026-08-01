from decimal import Decimal

from af_core.runtime.benchmark_models import (
    BenchmarkAggregate,
    BenchmarkTaskType,
)
from af_core.runtime.provider_protocol import (
    ProviderHealthStatus,
)
from af_core.runtime.recommendation import (
    ModelRecommendationEngine,
)


def aggregate(
    *,
    provider: str,
    model: str,
    quality: float,
    latency: float,
    cost: str,
    success: float,
) -> BenchmarkAggregate:
    return BenchmarkAggregate(
        provider_id=provider,
        model_key=model,
        task_type=BenchmarkTaskType.CODING,
        sample_count=10,
        success_count=10,
        success_rate=success,
        average_quality_score=quality,
        average_latency_ms=latency,
        average_cost_usd=Decimal(cost),
    )


def test_recommendation_balances_quality_cost_and_latency() -> None:
    recommendation = ModelRecommendationEngine().recommend(
        task_type=BenchmarkTaskType.CODING,
        aggregates=[
            aggregate(
                provider="premium",
                model="premium-model",
                quality=98,
                latency=2000,
                cost="0.10",
                success=100,
            ),
            aggregate(
                provider="flash",
                model="flash-model",
                quality=92,
                latency=300,
                cost="0.005",
                success=99,
            ),
        ],
        health_by_provider={
            "premium": ProviderHealthStatus.HEALTHY,
            "flash": ProviderHealthStatus.HEALTHY,
        },
    )

    assert (
        recommendation.recommended_model_key
        == "flash-model"
    )
    assert recommendation.candidates[0].rank == 1


def test_unavailable_provider_is_excluded() -> None:
    recommendation = ModelRecommendationEngine().recommend(
        task_type=BenchmarkTaskType.CODING,
        aggregates=[
            aggregate(
                provider="down",
                model="best-model",
                quality=100,
                latency=100,
                cost="0",
                success=100,
            ),
            aggregate(
                provider="up",
                model="available-model",
                quality=80,
                latency=500,
                cost="0.01",
                success=90,
            ),
        ],
        health_by_provider={
            "down": ProviderHealthStatus.UNAVAILABLE,
            "up": ProviderHealthStatus.HEALTHY,
        },
    )

    assert (
        recommendation.recommended_model_key
        == "available-model"
    )
    assert len(recommendation.candidates) == 1


def test_empty_benchmark_returns_empty_recommendation() -> None:
    recommendation = ModelRecommendationEngine().recommend(
        task_type=BenchmarkTaskType.TESTING,
        aggregates=[],
    )

    assert recommendation.recommended_model_key is None
    assert recommendation.candidates == []
