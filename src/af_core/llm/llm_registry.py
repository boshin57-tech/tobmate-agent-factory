from __future__ import annotations

from .llm_provider import (
    LLMProvider,
)



class LLMProviderRegistry:
    """
    Manages available LLM providers.
    """


    def __init__(self) -> None:

        self._providers: dict[
            str,
            LLMProvider
        ] = {}



    def register(
        self,
        name: str,
        provider:
        LLMProvider,
    ) -> None:

        self._providers[
            name
        ] = provider



    def get(
        self,
        name: str,
    ) -> LLMProvider | None:

        return self._providers.get(
            name
        )



    def providers(
        self,
    ) -> tuple[str, ...]:

        return tuple(
            self._providers.keys()
        )
