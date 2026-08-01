from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, Field


ResponseModel = TypeVar(
    "ResponseModel",
    bound=BaseModel,
)


class ProviderCapability(StrEnum):
    TEXT = "TEXT"
    STRUCTURED_OUTPUT = "STRUCTURED_OUTPUT"
    TOOL_CALLING = "TOOL_CALLING"
    VISION = "VISION"
    EMBEDDINGS = "EMBEDDINGS"
    REASONING = "REASONING"
    CACHED_INPUT = "CACHED_INPUT"


class ProviderHealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class ProviderMessage(BaseModel):
    role: str
    content: str


class NormalizedTokenUsage(BaseModel):
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class ProviderResponse(BaseModel):
    provider_id: str
    model_id: str
    content: str | None = None
    parsed: dict[str, Any] | None = None
    request_id: str | None = None
    usage: NormalizedTokenUsage = Field(
        default_factory=NormalizedTokenUsage
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderHealth(BaseModel):
    provider_id: str
    status: ProviderHealthStatus
    message: str = ""
    latency_ms: float | None = Field(
        default=None,
        ge=0,
    )


class ProviderAdapterError(RuntimeError):
    """Raised when a model provider operation fails."""


class ProviderAdapter(Protocol):
    @property
    def provider_id(self) -> str:
        """Stable provider identifier."""
        ...

    @property
    def capabilities(self) -> set[ProviderCapability]:
        """Capabilities supported by this provider."""
        ...

    async def complete(
        self,
        *,
        messages: Sequence[ProviderMessage],
        model_id: str,
        parameters: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        """Generate a text response."""
        ...

    async def structured(
        self,
        *,
        messages: Sequence[ProviderMessage],
        model_id: str,
        response_model: type[ResponseModel],
        parameters: dict[str, Any] | None = None,
    ) -> tuple[ResponseModel, ProviderResponse]:
        """Generate and validate a structured response."""
        ...

    async def health(self) -> ProviderHealth:
        """Return provider health information."""
        ...
