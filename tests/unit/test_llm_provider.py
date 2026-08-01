import asyncio

import pytest

from af_core.runtime.agent import AgentAction
from af_core.runtime.llm_provider import (
    LLMMessage,
    LLMProviderError,
    StaticLLMProvider,
)


def test_static_provider_returns_validated_response() -> None:
    provider = StaticLLMProvider(
        [
            {
                "action_type": "complete",
                "summary": "done",
            }
        ]
    )

    result = asyncio.run(
        provider.generate(
            messages=[
                LLMMessage(
                    role="user",
                    content="complete",
                )
            ],
            response_model=AgentAction,
        )
    )

    assert result.action_type == "complete"
    assert result.summary == "done"
    assert len(provider.calls) == 1


def test_static_provider_rejects_invalid_response() -> None:
    provider = StaticLLMProvider(
        [
            {
                "action_type": "complete",
            }
        ]
    )

    with pytest.raises(LLMProviderError):
        asyncio.run(
            provider.generate(
                messages=[],
                response_model=AgentAction,
            )
        )


def test_static_provider_rejects_exhaustion() -> None:
    provider = StaticLLMProvider([])

    with pytest.raises(LLMProviderError):
        asyncio.run(
            provider.generate(
                messages=[],
                response_model=AgentAction,
            )
        )
