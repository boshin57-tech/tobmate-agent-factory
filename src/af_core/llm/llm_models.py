from __future__ import annotations

from pydantic import BaseModel, Field


class LLMRequest(BaseModel):

    prompt: str

    system: str | None = None

    temperature: float = 0.2



class LLMResponse(BaseModel):

    provider: str

    model: str

    content: str

    tokens_used: int = 0



class LLMProviderInfo(BaseModel):

    provider_id: str

    name: str

    model: str

    capabilities: list[str] = Field(
        default_factory=list
    )
