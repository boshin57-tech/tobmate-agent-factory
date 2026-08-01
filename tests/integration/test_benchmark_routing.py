from __future__ import annotations

import asyncio
from decimal import Decimal

from af_core.runtime.benchmark_models import (
    BenchmarkExecutionMetrics,
    BenchmarkResult,
    BenchmarkStatus,
    BenchmarkTaskType,
    QualityMetrics,
)
from af_core.runtime.benchmark_routing import (
    BenchmarkAwareExecutionService,
    BenchmarkAwareModelRouter,
    BenchmarkRoutingPolicy,
)
from af_core.runtime.benchmark_store import (
    BenchmarkStore,
)
from af_core.runtime.failover import (
    FailoverOutcome,
)
from af_core.runtime.model_registry import (
    ModelPricing,
    ModelRegistry,
    ModelTier,
    RegisteredModel,
)
from af_core.runtime.provider_protocol import (
    ProviderCapability,
    ProviderHealth,
    ProviderHealthStatus,
)
from af_core.runtime.provider_registry import (
    ProviderRegistry,
)
from af_core.runtime.routing import (
    ModelRouter,
    RoutingRequest,
    RoutingStrategy,
)


class MockProvider:
    def __init__(
        self,
        provider_id: str,
        status: ProviderHealthStatus = (
            ProviderHealthStatus.HEALTHY
        ),
    ) -> None:
        self._provider_id = provider_id
        self._status = status

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def capabilities(self):
        return {
            ProviderCapability.TEXT,
            ProviderCapability.STRUCTURED_OUTPUT,
        }

    async def complete(self, **kwargs):
        raise NotImplementedError

    async def structured(self, **kwargs):
        raise NotImplementedError

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider_id=self.provider_id,
            status=self._status,
        )


def registered_model(
    *,
    key: str,
    provider: str,
    tier: ModelTier,
    input_price: float,
    output_price: float,
) -> RegisteredModel:
    return RegisteredModel(
        model_key=key,
        provider_id=provider,
        provider_model_id=f"{provider}/{key}",
        display_name=key,
        tier=tier,
        capabilities={
            ProviderCapability.TEXT,
            ProviderCapability.STRUCTURED_OUTPUT,
        },
        pricing=ModelPricing(
            input_usd_per_million_tokens=input_price,
            output_usd_per_million_tokens=output_price,
        ),
        tags={"coding"},
    )


def benchmark_result(
    *,
    benchmark_id: str,
    provider: str,
    model: str,
    quality: float,
    latency: float,
    cost: str,
    status: BenchmarkStatus = BenchmarkStatus.PASSED,
) -> BenchmarkResult:
    return BenchmarkResult(
        benchmark_id=benchmark_id,
        scenario_id="coding-scenario",
        task_type=BenchmarkTaskType.CODING,
        provider_id=provider,
        model_key=model,
        provider_model_id=f"{provider}/{model}",
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
            input_tokens=100,
            output_tokens=50,
            cost_usd=Decimal(cost),
        ),
    )


def build_router(
    *,
    store: BenchmarkStore,
    require_benchmark_data: bool = False,
) -> BenchmarkAwareModelRouter:
    providers = ProviderRegistry()
    providers.register(
        MockProvider("premium-provider")
    )
    providers.register(
        MockProvider("flash-provider")
    )

    models = ModelRegistry()
    models.register(
        registered_model(
            key="premium-model",
            provider="premium-provider",
            tier=ModelTier.PREMIUM,
            input_price=10,
            output_price=30,
        )
    )
    models.register(
        registered_model(
            key="flash-model",
            provider="flash-provider",
            tier=ModelTier.ECONOMY,
            input_price=0.2,
            output_price=0.8,
        )
    )

    return BenchmarkAwareModelRouter(
        router=ModelRouter(
            model_registry=models,
            provider_registry=providers,
        ),
        benchmark_store=store,
        policy=BenchmarkRoutingPolicy(
            recommendation_bonus=100,
            recommendation_rank_decay=20,
            require_benchmark_data=(
                require_benchmark_data
            ),
        ),
    )


def routing_request() -> RoutingRequest:
    return RoutingRequest(
        required_capabilities={
            ProviderCapability.STRUCTURED_OUTPUT,
        },
        required_tags={"coding"},
        strategy=RoutingStrategy.QUALITY_FIRST,
    )


def test_benchmark_recommendation_reorders_base_routing() -> None:
    store = BenchmarkStore()
    store.extend(
        [
            benchmark_result(
                benchmark_id="premium-1",
                provider="premium-provider",
                model="premium-model",
                quality=98,
                latency=2000,
                cost="0.10",
            ),
            benchmark_result(
                benchmark_id="flash-1",
                provider="flash-provider",
                model="flash-model",
                quality=92,
                latency=250,
                cost="0.005",
            ),
        ]
    )

    result = asyncio.run(
        build_router(store=store).route(
            task_type=BenchmarkTaskType.CODING,
            request=routing_request(),
        )
    )

    assert result.benchmark_applied is True
    assert (
        result.recommendation.recommended_model_key
        == "flash-model"
    )
    assert (
        result.routing.candidates[0].model.model_key
        == "flash-model"
    )
    assert result.routing.candidates[0].rank == 1
    assert any(
        "Benchmark recommendation rank 1"
        in reason
        for reason in result.routing.candidates[
            0
        ].reasons
    )


def test_no_benchmark_data_preserves_base_routing() -> None:
    result = asyncio.run(
        build_router(
            store=BenchmarkStore()
        ).route(
            task_type=BenchmarkTaskType.CODING,
            request=routing_request(),
        )
    )

    assert result.benchmark_applied is False
    assert (
        result.routing.candidates[0].model.model_key
        == "premium-model"
    )


def test_required_benchmark_data_blocks_routing() -> None:
    result = asyncio.run(
        build_router(
            store=BenchmarkStore(),
            require_benchmark_data=True,
        ).route(
            task_type=BenchmarkTaskType.CODING,
            request=routing_request(),
        )
    )

    assert result.benchmark_applied is False
    assert result.routing.candidates == []
    assert "__benchmark__" in (
        result.routing.rejected_models
    )


def test_recommended_model_failure_uses_next_candidate() -> None:
    store = BenchmarkStore()
    store.extend(
        [
            benchmark_result(
                benchmark_id="premium-1",
                provider="premium-provider",
                model="premium-model",
                quality=95,
                latency=1500,
                cost="0.08",
            ),
            benchmark_result(
                benchmark_id="flash-1",
                provider="flash-provider",
                model="flash-model",
                quality=93,
                latency=200,
                cost="0.003",
            ),
        ]
    )

    calls: list[str] = []

    async def operation(candidate):
        model_key = candidate.model.model_key
        calls.append(model_key)

        if model_key == "flash-model":
            raise RuntimeError(
                "temporary flash provider failure"
            )

        return f"completed:{model_key}"

    routing_result, execution = asyncio.run(
        BenchmarkAwareExecutionService[str](
            router=build_router(store=store),
        ).execute(
            task_type=BenchmarkTaskType.CODING,
            routing_request=routing_request(),
            operation=operation,
        )
    )

    assert routing_result.benchmark_applied is True
    assert execution.outcome is FailoverOutcome.SUCCEEDED
    assert execution.value == "completed:premium-model"
    assert execution.selected_model_key == "premium-model"
    assert calls == [
        "flash-model",
        "premium-model",
    ]
    assert [
        attempt.successful
        for attempt in execution.attempts
    ] == [
        False,
        True,
    ]


def test_non_retryable_failure_stops_failover() -> None:
    store = BenchmarkStore()
    store.extend(
        [
            benchmark_result(
                benchmark_id="flash-1",
                provider="flash-provider",
                model="flash-model",
                quality=95,
                latency=100,
                cost="0.001",
            ),
            benchmark_result(
                benchmark_id="premium-1",
                provider="premium-provider",
                model="premium-model",
                quality=90,
                latency=1000,
                cost="0.05",
            ),
        ]
    )

    calls: list[str] = []

    async def operation(candidate):
        calls.append(candidate.model.model_key)
        raise ValueError("invalid model request")

    _, execution = asyncio.run(
        BenchmarkAwareExecutionService[str](
            router=build_router(store=store),
        ).execute(
            task_type=BenchmarkTaskType.CODING,
            routing_request=routing_request(),
            operation=operation,
        )
    )

    assert execution.outcome is FailoverOutcome.BLOCKED
    assert calls == ["flash-model"]
    assert len(execution.attempts) == 1
