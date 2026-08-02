from __future__ import annotations

from ..llm_provider import (
    LLMProvider,
)

from ..llm_models import (
    LLMRequest,
    LLMResponse,
)



class OpenAIProvider(
    LLMProvider
):
    """
    OpenAI compatible adapter.
    """


    def __init__(
        self,
        model: str = "gpt-5.5-mini",
    ) -> None:

        self.model = model



    def generate(
        self,
        request:
        LLMRequest,
    ) -> LLMResponse:


        return LLMResponse(
            provider="openai",

            model=self.model,

            content=(
                "Generated response "
                "through OpenAI adapter"
            ),
        )
