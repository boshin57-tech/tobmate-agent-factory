from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from .benchmark_models import (
    BenchmarkTaskType,
    ModelRecommendation,
)
from .benchmark_store import BenchmarkStore
from .failover import (
    FailoverResult,
    ProviderFailoverExecutor,
)
from .provider_protocol import (
    ProviderHealthStatus,
)
from .recommendation import (
    ModelRecommendationEngine,
)
from .routing import (
    ModelRouter,
    RoutingCandidate,
    RoutingRequest,
    RoutingResult,
)


T = TypeVar("T")


class BenchmarkRoutingPolicy(BaseModel):
    recommendation_bonus: float = Field(
        default=100.0,
        ge=0.0,
    )
    recommendation_rank_decay: float = Field(
        default=20.0,
        ge=0.0,
    )
    require_benchmark_data: bool = False
    maximum_recommended_candidates: int = Field(
        default=5,
        ge=1,
        le=100,
    )


class BenchmarkRoutingResult(BaseModel):
    routing: RoutingResult
    recommendation: ModelRecommendation
    benchmark_applied: bool
    reasons: list[str] = Field(default_factory=list)


CandidateOperation = Callable[
    [RoutingCandidate],
    Awaitable[T],
]


class BenchmarkAwareModelRouter:
    def __init__(
        self,
        *,
        router: ModelRouter,
        benchmark_store: BenchmarkStore,
        recommendation_engine: (
            ModelRecommendationEngine | None
        ) = None,
        policy: BenchmarkRoutingPolicy | None = None,
    ) -> None:
        self.router = router
        self.benchmark_store = benchmark_store
        self.recommendation_engine = (
            recommendation_engine
            or ModelRecommendationEngine()
        )
        self.policy = policy or BenchmarkRoutingPolicy()

    async def route(
        self,
        *,
        task_type: BenchmarkTaskType,
        request: RoutingRequest,
    ) -> BenchmarkRoutingResult:
        base_routing = await self.router.route(request)

        health_by_provider = {
            candidate.model.provider_id: (
                candidate.provider_health.status
            )
            for candidate in base_routing.candidates
        }

        recommendation = (
            self.recommendation_engine.recommend(
                task_type=task_type,
                aggregates=self.benchmark_store.aggregate(
                    task_type=task_type
                ),
                health_by_provider=health_by_provider,
                maximum_candidates=(
                    self.policy
                    .maximum_recommended_candidates
                ),
            )
        )

        if not recommendation.candidates:
            if self.policy.require_benchmark_data:
                return BenchmarkRoutingResult(
                    routing=RoutingResult(
                        candidates=[],
                        rejected_models={
                            **base_routing.rejected_models,
                            "__benchmark__": [
                                "No benchmark recommendation "
                                "is available for the task type."
                            ],
                        },
                    ),
                    recommendation=recommendation,
                    benchmark_applied=False,
                    reasons=[
                        "Routing blocked because benchmark "
                        "data is required."
                    ],
                )

            return BenchmarkRoutingResult(
                routing=base_routing,
                recommendation=recommendation,
                benchmark_applied=False,
                reasons=[
                    "No benchmark recommendation was "
                    "available; base routing was retained."
                ],
            )

        recommendation_rank = {
            candidate.model_key: candidate.rank
            for candidate in recommendation.candidates
        }
        recommendation_score = {
            candidate.model_key: candidate.final_score
            for candidate in recommendation.candidates
        }

        rescored: list[RoutingCandidate] = []

        for candidate in base_routing.candidates:
            model_key = candidate.model.model_key
            benchmark_rank = recommendation_rank.get(
                model_key
            )

            if benchmark_rank is None:
                rescored.append(candidate)
                continue

            bonus = max(
                self.policy.recommendation_bonus
                - (
                    benchmark_rank - 1
                )
                * self.policy.recommendation_rank_decay,
                0.0,
            )

            benchmark_score = recommendation_score[
                model_key
            ]

            rescored.append(
                candidate.model_copy(
                    update={
                        "score": (
                            candidate.score
                            + bonus
                            + benchmark_score
                        ),
                        "reasons": [
                            *candidate.reasons,
                            (
                                "Benchmark recommendation "
                                f"rank {benchmark_rank} added "
                                f"{bonus:.1f} priority points."
                            ),
                            (
                                "Benchmark final score "
                                f"{benchmark_score:.2f} added "
                                "to routing score."
                            ),
                        ],
                    }
                )
            )

        rescored.sort(
            key=lambda candidate: (
                -candidate.score,
                candidate.model.model_key,
            )
        )

        ranked = [
            candidate.model_copy(
                update={
                    "rank": index,
                }
            )
            for index, candidate in enumerate(
                rescored,
                start=1,
            )
        ]

        return BenchmarkRoutingResult(
            routing=RoutingResult(
                candidates=ranked,
                rejected_models=(
                    base_routing.rejected_models
                ),
            ),
            recommendation=recommendation,
            benchmark_applied=True,
            reasons=[
                "Benchmark recommendation was applied "
                "to the base routing candidates."
            ],
        )


class BenchmarkAwareExecutionService(Generic[T]):
    def __init__(
        self,
        *,
        router: BenchmarkAwareModelRouter,
        failover: ProviderFailoverExecutor[T] | None = None,
    ) -> None:
        self.router = router
        self.failover = (
            failover
            or ProviderFailoverExecutor[T]()
        )

    async def execute(
        self,
        *,
        task_type: BenchmarkTaskType,
        routing_request: RoutingRequest,
        operation: CandidateOperation[T],
        raise_on_exhaustion: bool = False,
    ) -> tuple[
        BenchmarkRoutingResult,
        FailoverResult[T],
    ]:
        benchmark_routing = await self.router.route(
            task_type=task_type,
            request=routing_request,
        )

        execution = await self.failover.execute(
            routing=benchmark_routing.routing,
            operation=operation,
            raise_on_exhaustion=raise_on_exhaustion,
        )

        return benchmark_routing, execution
