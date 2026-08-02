from __future__ import annotations

from ..llm_provider import (
    LLMProvider,
)

from ..llm_models import (
    LLMRequest,
    LLMResponse,
)



class LocalLLMProvider(
    LLMProvider
):
    """
    Local/private model adapter.
    """


    def __init__(
        self,
        model: str = "local-model",
    ) -> None:

        self.model = model



    def generate(
        self,
        request:
        LLMRequest,
    ) -> LLMResponse:


        return LLMResponse(

            provider="local",

            model=self.model,

            content=(
                "Generated response "
                "through local model"
            ),
        )
