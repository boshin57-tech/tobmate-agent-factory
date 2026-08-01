from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .model_registry import (
    ModelRegistry,
    ModelStatus,
    ModelTier,
    RegisteredModel,
)
from .provider_protocol import (
    ProviderCapability,
    ProviderHealth,
    ProviderHealthStatus,
)
from .provider_registry import ProviderRegistry


class RoutingStrategy(StrEnum):
    QUALITY_FIRST = "QUALITY_FIRST"
    COST_FIRST = "COST_FIRST"
    BALANCED = "BALANCED"
    LOCAL_FIRST = "LOCAL_FIRST"


class RoutingRequest(BaseModel):
    required_capabilities: set[
        ProviderCapability
    ] = Field(default_factory=set)
    preferred_tiers: list[ModelTier] = Field(
        default_factory=list
    )
    preferred_providers: list[str] = Field(
        default_factory=list
    )
    required_tags: set[str] = Field(
        default_factory=set
    )
    excluded_models: set[str] = Field(
        default_factory=set
    )
    excluded_providers: set[str] = Field(
        default_factory=set
    )
    strategy: RoutingStrategy = (
        RoutingStrategy.BALANCED
    )
    maximum_candidates: int = Field(
        default=5,
        ge=1,
        le=100,
    )
    allow_degraded_providers: bool = True


class RoutingCandidate(BaseModel):
    rank: int
    model: RegisteredModel
    provider_health: ProviderHealth
    score: float
    reasons: list[str] = Field(default_factory=list)


class RoutingResult(BaseModel):
    candidates: list[RoutingCandidate] = Field(
        default_factory=list
    )
    rejected_models: dict[str, list[str]] = Field(
        default_factory=dict
    )


class ModelRouter:
    def __init__(
        self,
        *,
        model_registry: ModelRegistry,
        provider_registry: ProviderRegistry,
    ) -> None:
        self.model_registry = model_registry
        self.provider_registry = provider_registry

    async def route(
        self,
        request: RoutingRequest,
    ) -> RoutingResult:
        candidates: list[
            tuple[float, RegisteredModel, ProviderHealth, list[str]]
        ] = []
        rejected: dict[str, list[str]] = {}
        health_cache: dict[str, ProviderHealth] = {}

        for model in self.model_registry.list():
            rejection_reasons = self._model_rejections(
                model=model,
                request=request,
            )

            if rejection_reasons:
                rejected[model.model_key] = rejection_reasons
                continue

            try:
                provider = self.provider_registry.get(
                    model.provider_id
                )
            except Exception as exc:
                rejected[model.model_key] = [
                    f"Provider is unavailable in registry: {exc}"
                ]
                continue

            if model.provider_id not in health_cache:
                try:
                    health_cache[
                        model.provider_id
                    ] = await provider.health()
                except Exception as exc:
                    health_cache[
                        model.provider_id
                    ] = ProviderHealth(
                        provider_id=model.provider_id,
                        status=(
                            ProviderHealthStatus.UNAVAILABLE
                        ),
                        message=str(exc),
                    )

            health = health_cache[model.provider_id]
            health_reasons = self._health_rejections(
                health=health,
                request=request,
            )

            if health_reasons:
                rejected[model.model_key] = health_reasons
                continue

            score, reasons = self._score(
                model=model,
                health=health,
                request=request,
            )

            candidates.append(
                (
                    score,
                    model,
                    health,
                    reasons,
                )
            )

        candidates.sort(
            key=lambda item: (
                -item[0],
                item[1].model_key,
            )
        )

        selected = [
            RoutingCandidate(
                rank=index,
                model=model,
                provider_health=health,
                score=score,
                reasons=reasons,
            )
            for index, (
                score,
                model,
                health,
                reasons,
            ) in enumerate(
                candidates[: request.maximum_candidates],
                start=1,
            )
        ]

        return RoutingResult(
            candidates=selected,
            rejected_models=rejected,
        )

    def _model_rejections(
        self,
        *,
        model: RegisteredModel,
        request: RoutingRequest,
    ) -> list[str]:
        reasons: list[str] = []

        if model.status is not ModelStatus.ACTIVE:
            reasons.append(
                f"Model status is {model.status.value}."
            )

        if model.model_key in request.excluded_models:
            reasons.append("Model is explicitly excluded.")

        if model.provider_id in request.excluded_providers:
            reasons.append("Provider is explicitly excluded.")

        if not request.required_capabilities.issubset(
            model.capabilities
        ):
            reasons.append(
                "Required capabilities are not supported."
            )

        if not request.required_tags.issubset(
            model.tags
        ):
            reasons.append(
                "Required model tags are missing."
            )

        return reasons

    def _health_rejections(
        self,
        *,
        health: ProviderHealth,
        request: RoutingRequest,
    ) -> list[str]:
        if (
            health.status
            is ProviderHealthStatus.UNAVAILABLE
        ):
            return ["Provider health is UNAVAILABLE."]

        if (
            health.status
            is ProviderHealthStatus.DEGRADED
            and not request.allow_degraded_providers
        ):
            return [
                "Provider is DEGRADED and degraded providers "
                "are not permitted."
            ]

        return []

    def _score(
        self,
        *,
        model: RegisteredModel,
        health: ProviderHealth,
        request: RoutingRequest,
    ) -> tuple[float, list[str]]:
        score = 0.0
        reasons: list[str] = []

        health_score = {
            ProviderHealthStatus.HEALTHY: 40.0,
            ProviderHealthStatus.UNKNOWN: 20.0,
            ProviderHealthStatus.DEGRADED: 10.0,
            ProviderHealthStatus.UNAVAILABLE: 0.0,
        }[health.status]

        score += health_score
        reasons.append(
            f"Provider health contributed {health_score:.1f}."
        )

        tier_score = self._tier_score(
            model=model,
            request=request,
        )
        score += tier_score
        reasons.append(
            f"Model tier contributed {tier_score:.1f}."
        )

        provider_score = self._provider_preference_score(
            model=model,
            request=request,
        )
        score += provider_score

        if provider_score:
            reasons.append(
                f"Provider preference contributed "
                f"{provider_score:.1f}."
            )

        cost_score = self._cost_score(
            model=model,
            strategy=request.strategy,
        )
        score += cost_score
        reasons.append(
            f"Cost profile contributed {cost_score:.1f}."
        )

        if (
            request.strategy
            is RoutingStrategy.LOCAL_FIRST
            and model.tier is ModelTier.LOCAL
        ):
            score += 35.0
            reasons.append(
                "Local-first strategy added 35.0."
            )

        if request.required_tags:
            tag_score = min(
                len(
                    request.required_tags.intersection(
                        model.tags
                    )
                )
                * 2.0,
                10.0,
            )
            score += tag_score

            if tag_score:
                reasons.append(
                    f"Required tags contributed {tag_score:.1f}."
                )

        return score, reasons

    def _tier_score(
        self,
        *,
        model: RegisteredModel,
        request: RoutingRequest,
    ) -> float:
        if request.preferred_tiers:
            try:
                index = request.preferred_tiers.index(
                    model.tier
                )
            except ValueError:
                return 0.0

            return max(
                30.0 - index * 10.0,
                5.0,
            )

        quality_scores = {
            ModelTier.PREMIUM: 30.0,
            ModelTier.STANDARD: 22.0,
            ModelTier.ECONOMY: 14.0,
            ModelTier.LOCAL: 10.0,
        }

        if (
            request.strategy
            is RoutingStrategy.COST_FIRST
        ):
            return {
                ModelTier.ECONOMY: 30.0,
                ModelTier.LOCAL: 28.0,
                ModelTier.STANDARD: 16.0,
                ModelTier.PREMIUM: 8.0,
            }[model.tier]

        return quality_scores[model.tier]

    def _provider_preference_score(
        self,
        *,
        model: RegisteredModel,
        request: RoutingRequest,
    ) -> float:
        if not request.preferred_providers:
            return 0.0

        try:
            index = request.preferred_providers.index(
                model.provider_id
            )
        except ValueError:
            return 0.0

        return max(
            20.0 - index * 5.0,
            5.0,
        )

    def _cost_score(
        self,
        *,
        model: RegisteredModel,
        strategy: RoutingStrategy,
    ) -> float:
        estimated = (
            model.pricing.input_usd_per_million_tokens
            + model.pricing.output_usd_per_million_tokens
        )

        if estimated <= 0:
            base = 25.0
        elif estimated <= 1:
            base = 22.0
        elif estimated <= 5:
            base = 17.0
        elif estimated <= 20:
            base = 10.0
        else:
            base = 3.0

        if strategy is RoutingStrategy.COST_FIRST:
            return min(base * 1.5, 35.0)

        if strategy is RoutingStrategy.QUALITY_FIRST:
            return base * 0.4

        return base
