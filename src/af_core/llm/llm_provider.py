from __future__ import annotations

from abc import ABC, abstractmethod

from .llm_models import (
    LLMRequest,
    LLMResponse,
)



class LLMProvider(ABC):
    """
    Common interface for all LLM providers.
    """


    @abstractmethod
    def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        ...
