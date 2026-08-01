from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel


ResponseModel = TypeVar(
    "ResponseModel",
    bound=BaseModel,
)


class LLMMessage(BaseModel):
    role: str
    content: str


class LLMUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class LLMProvider(Protocol):
    async def generate(
        self,
        *,
        messages: Sequence[LLMMessage],
        response_model: type[ResponseModel],
        model: str | None = None,
    ) -> ResponseModel:
        """Return one validated structured response."""
        ...


class LLMProviderError(RuntimeError):
    """Raised when a model response is invalid or unavailable."""


class StaticLLMProvider:
    """Deterministic provider used by runtime tests."""

    def __init__(
        self,
        responses: Sequence[
            BaseModel | dict[str, Any]
        ],
    ) -> None:
        self._responses = list(responses)
        self.calls: list[list[LLMMessage]] = []

    async def generate(
        self,
        *,
        messages: Sequence[LLMMessage],
        response_model: type[ResponseModel],
        model: str | None = None,
    ) -> ResponseModel:
        del model

        self.calls.append(list(messages))

        if not self._responses:
            raise LLMProviderError(
                "Static provider has no remaining responses."
            )

        response = self._responses.pop(0)

        try:
            if isinstance(response, BaseModel):
                payload = response.model_dump(
                    mode="python"
                )
            else:
                payload = response

            return response_model.model_validate(
                payload
            )
        except Exception as exc:
            raise LLMProviderError(
                f"Invalid structured response: {exc}"
            ) from exc
