from __future__ import annotations

from decimal import Decimal

from .benchmark_models import (
    BenchmarkAggregate,
    BenchmarkTaskType,
    ModelRecommendation,
    RecommendationCandidate,
    RecommendationWeights,
)
from .provider_protocol import (
    ProviderHealthStatus,
)


class RecommendationError(RuntimeError):
    """Raised when model recommendation cannot be produced."""


class ModelRecommendationEngine:
    def __init__(
        self,
        *,
        weights: RecommendationWeights | None = None,
    ) -> None:
        self.weights = weights or RecommendationWeights()
        self.weights.validate_total()

    def recommend(
        self,
        *,
        task_type: BenchmarkTaskType,
        aggregates: list[BenchmarkAggregate],
        health_by_provider: dict[
            str,
            ProviderHealthStatus,
        ] | None = None,
        maximum_candidates: int = 5,
    ) -> ModelRecommendation:
        if maximum_candidates < 1:
            raise ValueError(
                "maximum_candidates must be at least 1"
            )

        health = health_by_provider or {}

        matching = [
            item
            for item in aggregates
            if (
                item.task_type is task_type
                and item.sample_count > 0
            )
        ]

        if not matching:
            return ModelRecommendation(
                task_type=task_type,
            )

        maximum_cost = max(
            (
                item.average_cost_usd
                for item in matching
            ),
            default=Decimal("0"),
        )
        maximum_latency = max(
            (
                item.average_latency_ms
                for item in matching
            ),
            default=0.0,
        )

        candidates: list[
            tuple[float, RecommendationCandidate]
        ] = []

        for aggregate in matching:
            provider_health = health.get(
                aggregate.provider_id,
                ProviderHealthStatus.UNKNOWN,
            )

            if (
                provider_health
                is ProviderHealthStatus.UNAVAILABLE
            ):
                continue

            quality_score = self._bounded(
                aggregate.average_quality_score
            )
            success_score = self._bounded(
                aggregate.success_rate
            )
            cost_score = self._inverse_decimal_score(
                value=aggregate.average_cost_usd,
                maximum=maximum_cost,
            )
            latency_score = self._inverse_float_score(
                value=aggregate.average_latency_ms,
                maximum=maximum_latency,
            )
            health_score = self._health_score(
                provider_health
            )

            final_score = (
                quality_score * self.weights.quality
                + cost_score * self.weights.cost
                + latency_score * self.weights.latency
                + health_score * self.weights.health
                + success_score
                * self.weights.success_rate
            )

            reasons = [
                (
                    "Quality "
                    f"{quality_score:.2f}/100"
                ),
                (
                    "Cost efficiency "
                    f"{cost_score:.2f}/100"
                ),
                (
                    "Latency efficiency "
                    f"{latency_score:.2f}/100"
                ),
                (
                    "Provider health "
                    f"{health_score:.2f}/100"
                ),
                (
                    "Success rate "
                    f"{success_score:.2f}/100"
                ),
            ]

            candidate = RecommendationCandidate(
                rank=0,
                provider_id=aggregate.provider_id,
                model_key=aggregate.model_key,
                task_type=task_type,
                final_score=round(
                    self._bounded(final_score),
                    4,
                ),
                quality_score=round(
                    quality_score,
                    4,
                ),
                cost_score=round(
                    cost_score,
                    4,
                ),
                latency_score=round(
                    latency_score,
                    4,
                ),
                health_score=round(
                    health_score,
                    4,
                ),
                success_rate_score=round(
                    success_score,
                    4,
                ),
                reasons=reasons,
            )

            candidates.append(
                (
                    candidate.final_score,
                    candidate,
                )
            )

        candidates.sort(
            key=lambda item: (
                -item[0],
                item[1].model_key,
            )
        )

        ranked: list[RecommendationCandidate] = []

        for index, (_, candidate) in enumerate(
            candidates[:maximum_candidates],
            start=1,
        ):
            ranked.append(
                candidate.model_copy(
                    update={
                        "rank": index,
                    }
                )
            )

        selected = ranked[0] if ranked else None

        return ModelRecommendation(
            task_type=task_type,
            recommended_model_key=(
                selected.model_key
                if selected
                else None
            ),
            recommended_provider_id=(
                selected.provider_id
                if selected
                else None
            ),
            candidates=ranked,
        )

    def _inverse_decimal_score(
        self,
        *,
        value: Decimal,
        maximum: Decimal,
    ) -> float:
        if value <= 0:
            return 100.0

        if maximum <= 0:
            return 100.0

        ratio = float(
            value / maximum
        )

        return self._bounded(
            (1.0 - ratio) * 100.0
        )

    def _inverse_float_score(
        self,
        *,
        value: float,
        maximum: float,
    ) -> float:
        if value <= 0:
            return 100.0

        if maximum <= 0:
            return 100.0

        return self._bounded(
            (1.0 - value / maximum)
            * 100.0
        )

    def _health_score(
        self,
        status: ProviderHealthStatus,
    ) -> float:
        return {
            ProviderHealthStatus.HEALTHY: 100.0,
            ProviderHealthStatus.UNKNOWN: 60.0,
            ProviderHealthStatus.DEGRADED: 35.0,
            ProviderHealthStatus.UNAVAILABLE: 0.0,
        }[status]

    def _bounded(
        self,
        value: float,
    ) -> float:
        return max(
            min(float(value), 100.0),
            0.0,
        )
