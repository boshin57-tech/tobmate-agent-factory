import asyncio

from af_core.runtime.model_registry import (
    ModelPricing,
    ModelRegistry,
    ModelStatus,
    ModelTier,
    RegisteredModel,
)
from af_core.runtime.provider_protocol import (
    ProviderCapability,
    ProviderHealth,
    ProviderHealthStatus,
)
from af_core.runtime.provider_registry import ProviderRegistry
from af_core.runtime.routing import (
    ModelRouter,
    RoutingRequest,
    RoutingStrategy,
)


class MockProvider:
    def __init__(
        self,
        provider_id: str,
        status: ProviderHealthStatus,
    ) -> None:
        self._provider_id = provider_id
        self._status = status
        self.health_calls = 0

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def capabilities(self) -> set[ProviderCapability]:
        return {
            ProviderCapability.TEXT,
            ProviderCapability.STRUCTURED_OUTPUT,
        }

    async def complete(self, **kwargs):
        raise NotImplementedError

    async def structured(self, **kwargs):
        raise NotImplementedError

    async def health(self) -> ProviderHealth:
        self.health_calls += 1

        return ProviderHealth(
            provider_id=self.provider_id,
            status=self._status,
            message=self._status.value,
            latency_ms=10,
        )


def model(
    *,
    key: str,
    provider_id: str,
    tier: ModelTier,
    input_price: float,
    output_price: float,
    status: ModelStatus = ModelStatus.ACTIVE,
    tags: set[str] | None = None,
) -> RegisteredModel:
    return RegisteredModel(
        model_key=key,
        provider_id=provider_id,
        provider_model_id=f"{provider_id}/{key}",
        display_name=key,
        tier=tier,
        status=status,
        capabilities={
            ProviderCapability.TEXT,
            ProviderCapability.STRUCTURED_OUTPUT,
        },
        pricing=ModelPricing(
            input_usd_per_million_tokens=input_price,
            output_usd_per_million_tokens=output_price,
        ),
        tags=tags or set(),
    )


def build_registries():
    providers = ProviderRegistry()
    providers.register(
        MockProvider(
            "provider-premium",
            ProviderHealthStatus.HEALTHY,
        )
    )
    providers.register(
        MockProvider(
            "provider-economy",
            ProviderHealthStatus.HEALTHY,
        )
    )
    providers.register(
        MockProvider(
            "provider-degraded",
            ProviderHealthStatus.DEGRADED,
        )
    )
    providers.register(
        MockProvider(
            "provider-down",
            ProviderHealthStatus.UNAVAILABLE,
        )
    )

    models = ModelRegistry()
    models.register(
        model(
            key="premium-model",
            provider_id="provider-premium",
            tier=ModelTier.PREMIUM,
            input_price=10,
            output_price=30,
            tags={"coding", "reasoning"},
        )
    )
    models.register(
        model(
            key="economy-model",
            provider_id="provider-economy",
            tier=ModelTier.ECONOMY,
            input_price=0.2,
            output_price=0.8,
            tags={"coding"},
        )
    )
    models.register(
        model(
            key="degraded-model",
            provider_id="provider-degraded",
            tier=ModelTier.STANDARD,
            input_price=1,
            output_price=4,
            tags={"coding"},
        )
    )
    models.register(
        model(
            key="down-model",
            provider_id="provider-down",
            tier=ModelTier.PREMIUM,
            input_price=1,
            output_price=2,
            tags={"coding"},
        )
    )
    models.register(
        model(
            key="disabled-model",
            provider_id="provider-economy",
            tier=ModelTier.ECONOMY,
            input_price=0,
            output_price=0,
            status=ModelStatus.DISABLED,
            tags={"coding"},
        )
    )

    return providers, models


def test_quality_first_prefers_premium_healthy_model() -> None:
    providers, models = build_registries()

    result = asyncio.run(
        ModelRouter(
            model_registry=models,
            provider_registry=providers,
        ).route(
            RoutingRequest(
                required_capabilities={
                    ProviderCapability.STRUCTURED_OUTPUT,
                },
                required_tags={"coding"},
                strategy=RoutingStrategy.QUALITY_FIRST,
            )
        )
    )

    assert result.candidates
    assert (
        result.candidates[0].model.model_key
        == "premium-model"
    )
    assert "down-model" in result.rejected_models
    assert "disabled-model" in result.rejected_models


def test_cost_first_prefers_economy_model() -> None:
    providers, models = build_registries()

    result = asyncio.run(
        ModelRouter(
            model_registry=models,
            provider_registry=providers,
        ).route(
            RoutingRequest(
                required_tags={"coding"},
                strategy=RoutingStrategy.COST_FIRST,
            )
        )
    )

    assert (
        result.candidates[0].model.model_key
        == "economy-model"
    )


def test_degraded_provider_can_be_excluded() -> None:
    providers, models = build_registries()

    result = asyncio.run(
        ModelRouter(
            model_registry=models,
            provider_registry=providers,
        ).route(
            RoutingRequest(
                required_tags={"coding"},
                allow_degraded_providers=False,
            )
        )
    )

    assert "degraded-model" in result.rejected_models
    assert all(
        candidate.model.model_key != "degraded-model"
        for candidate in result.candidates
    )


def test_required_capability_and_tag_filtering() -> None:
    providers, models = build_registries()

    result = asyncio.run(
        ModelRouter(
            model_registry=models,
            provider_registry=providers,
        ).route(
            RoutingRequest(
                required_capabilities={
                    ProviderCapability.VISION,
                },
                required_tags={"coding"},
            )
        )
    )

    assert result.candidates == []
    assert all(
        "Required capabilities" in " ".join(reasons)
        for reasons in result.rejected_models.values()
        if "disabled-model" not in reasons
    )


def test_provider_health_is_cached_per_route_call() -> None:
    providers, models = build_registries()
    provider = providers.get("provider-economy")

    asyncio.run(
        ModelRouter(
            model_registry=models,
            provider_registry=providers,
        ).route(
            RoutingRequest(
                required_tags={"coding"},
            )
        )
    )

    assert provider.health_calls == 1


def test_explicit_exclusions_and_candidate_limit() -> None:
    providers, models = build_registries()

    result = asyncio.run(
        ModelRouter(
            model_registry=models,
            provider_registry=providers,
        ).route(
            RoutingRequest(
                required_tags={"coding"},
                excluded_models={"premium-model"},
                excluded_providers={"provider-degraded"},
                maximum_candidates=1,
            )
        )
    )

    assert len(result.candidates) == 1
    assert result.candidates[0].model.model_key == "economy-model"
    assert "premium-model" in result.rejected_models
    assert "degraded-model" in result.rejected_models
