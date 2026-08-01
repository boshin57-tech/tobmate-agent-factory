from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .provider_protocol import ProviderCapability


class ModelTier(StrEnum):
    ECONOMY = "ECONOMY"
    STANDARD = "STANDARD"
    PREMIUM = "PREMIUM"
    LOCAL = "LOCAL"


class ModelStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    DEPRECATED = "DEPRECATED"
    EXPERIMENTAL = "EXPERIMENTAL"


class ModelPricing(BaseModel):
    input_usd_per_million_tokens: float = Field(
        default=0.0,
        ge=0.0,
    )
    cached_input_usd_per_million_tokens: float = Field(
        default=0.0,
        ge=0.0,
    )
    output_usd_per_million_tokens: float = Field(
        default=0.0,
        ge=0.0,
    )


class RegisteredModel(BaseModel):
    model_key: str
    provider_id: str
    provider_model_id: str
    display_name: str
    tier: ModelTier = ModelTier.STANDARD
    status: ModelStatus = ModelStatus.ACTIVE
    capabilities: set[ProviderCapability] = Field(
        default_factory=set
    )
    context_window_tokens: int | None = Field(
        default=None,
        ge=1,
    )
    maximum_output_tokens: int | None = Field(
        default=None,
        ge=1,
    )
    pricing: ModelPricing = Field(
        default_factory=ModelPricing
    )
    tags: set[str] = Field(default_factory=set)
    metadata: dict = Field(default_factory=dict)


class ModelRegistryError(RuntimeError):
    """Raised for invalid model registration or lookup."""


class ModelRegistry:
    def __init__(self) -> None:
        self._models: dict[str, RegisteredModel] = {}

    def register(
        self,
        model: RegisteredModel,
    ) -> None:
        key = model.model_key.strip()

        if not key:
            raise ModelRegistryError(
                "Model key is required."
            )

        if key in self._models:
            raise ModelRegistryError(
                f"Model already registered: {key}"
            )

        self._models[key] = model

    def update(
        self,
        model: RegisteredModel,
    ) -> None:
        if model.model_key not in self._models:
            raise ModelRegistryError(
                f"Model not registered: {model.model_key}"
            )

        self._models[model.model_key] = model

    def get(
        self,
        model_key: str,
    ) -> RegisteredModel:
        try:
            return self._models[model_key]
        except KeyError as exc:
            raise ModelRegistryError(
                f"Unknown model: {model_key}"
            ) from exc

    def list(
        self,
        *,
        provider_id: str | None = None,
        status: ModelStatus | None = None,
    ) -> list[RegisteredModel]:
        models = list(self._models.values())

        if provider_id is not None:
            models = [
                model
                for model in models
                if model.provider_id == provider_id
            ]

        if status is not None:
            models = [
                model
                for model in models
                if model.status is status
            ]

        return sorted(
            models,
            key=lambda model: model.model_key,
        )

    def find(
        self,
        *,
        required_capabilities: set[
            ProviderCapability
        ] | None = None,
        tier: ModelTier | None = None,
        tags: set[str] | None = None,
        active_only: bool = True,
    ) -> list[RegisteredModel]:
        required = required_capabilities or set()
        required_tags = tags or set()

        models = self.list()

        result: list[RegisteredModel] = []

        for model in models:
            if (
                active_only
                and model.status is not ModelStatus.ACTIVE
            ):
                continue

            if tier is not None and model.tier is not tier:
                continue

            if not required.issubset(
                model.capabilities
            ):
                continue

            if not required_tags.issubset(
                model.tags
            ):
                continue

            result.append(model)

        return result

    def disable(
        self,
        model_key: str,
    ) -> RegisteredModel:
        model = self.get(model_key)
        updated = model.model_copy(
            update={
                "status": ModelStatus.DISABLED,
            }
        )
        self._models[model_key] = updated
        return updated
