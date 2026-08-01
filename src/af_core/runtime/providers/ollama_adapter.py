from __future__ import annotations

import json
import time
from collections.abc import Sequence
from typing import Any, TypeVar

from pydantic import BaseModel

from af_core.runtime.provider_config import (
    ProviderEndpointConfig,
)
from af_core.runtime.provider_protocol import (
    NormalizedTokenUsage,
    ProviderAdapterError,
    ProviderCapability,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderMessage,
    ProviderResponse,
)

from .http_client import (
    AsyncJSONHTTPClient,
    ProviderHTTPError,
)


ResponseModel = TypeVar(
    "ResponseModel",
    bound=BaseModel,
)


class OllamaAdapter:
    def __init__(
        self,
        config: ProviderEndpointConfig,
        *,
        client: AsyncJSONHTTPClient | None = None,
    ) -> None:
        self.config = config
        self.client = client or AsyncJSONHTTPClient()

    @property
    def provider_id(self) -> str:
        return self.config.provider_id

    @property
    def capabilities(self) -> set[ProviderCapability]:
        return {
            ProviderCapability.TEXT,
            ProviderCapability.STRUCTURED_OUTPUT,
            ProviderCapability.TOOL_CALLING,
            ProviderCapability.REASONING,
        }

    async def complete(
        self,
        *,
        messages: Sequence[ProviderMessage],
        model_id: str,
        parameters: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        payload = self._base_payload(
            messages=messages,
            model_id=model_id,
            parameters=parameters,
        )

        response = await self._post_chat(payload)
        return self._normalize_response(
            model_id=model_id,
            payload=response,
        )

    async def structured(
        self,
        *,
        messages: Sequence[ProviderMessage],
        model_id: str,
        response_model: type[ResponseModel],
        parameters: dict[str, Any] | None = None,
    ) -> tuple[ResponseModel, ProviderResponse]:
        payload = self._base_payload(
            messages=messages,
            model_id=model_id,
            parameters=parameters,
        )
        payload["format"] = response_model.model_json_schema()

        raw = await self._post_chat(payload)
        normalized = self._normalize_response(
            model_id=model_id,
            payload=raw,
        )

        if normalized.content is None:
            raise ProviderAdapterError(
                "Ollama returned no structured content."
            )

        try:
            parsed = response_model.model_validate_json(
                normalized.content
            )
        except Exception as exc:
            raise ProviderAdapterError(
                f"Ollama structured output validation failed: {exc}"
            ) from exc

        normalized.parsed = parsed.model_dump(
            mode="json"
        )

        return parsed, normalized

    async def health(self) -> ProviderHealth:
        started = time.perf_counter()

        try:
            await self.client.request(
                method="GET",
                url=self._url("/api/tags"),
                headers=self.config.resolved_headers(),
                timeout_seconds=self.config.timeout_seconds,
            )
        except ProviderHTTPError as exc:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.UNAVAILABLE,
                message=str(exc),
                latency_ms=(
                    time.perf_counter() - started
                )
                * 1000,
            )

        return ProviderHealth(
            provider_id=self.provider_id,
            status=ProviderHealthStatus.HEALTHY,
            message="Ollama API is reachable.",
            latency_ms=(
                time.perf_counter() - started
            )
            * 1000,
        )

    def _base_payload(
        self,
        *,
        messages: Sequence[ProviderMessage],
        model_id: str,
        parameters: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model_id,
            "messages": [
                message.model_dump(mode="json")
                for message in messages
            ],
            "stream": False,
        }

        options = dict(
            self.config.options.get(
                "generation_options",
                {},
            )
        )
        options.update(
            (parameters or {}).get(
                "options",
                {},
            )
        )

        if options:
            payload["options"] = options

        if "think" in (parameters or {}):
            payload["think"] = parameters["think"]

        return payload

    async def _post_chat(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            response = await self.client.request(
                method="POST",
                url=self._url("/api/chat"),
                headers=self.config.resolved_headers(),
                payload=payload,
                timeout_seconds=self.config.timeout_seconds,
            )
        except ProviderHTTPError as exc:
            raise ProviderAdapterError(str(exc)) from exc

        return response.payload

    def _normalize_response(
        self,
        *,
        model_id: str,
        payload: dict[str, Any],
    ) -> ProviderResponse:
        message = payload.get("message") or {}

        if not isinstance(message, dict):
            raise ProviderAdapterError(
                "Ollama response message is invalid."
            )

        content = message.get("content")

        if content is not None and not isinstance(
            content,
            str,
        ):
            raise ProviderAdapterError(
                "Ollama response content is invalid."
            )

        usage = NormalizedTokenUsage(
            input_tokens=int(
                payload.get("prompt_eval_count") or 0
            ),
            output_tokens=int(
                payload.get("eval_count") or 0
            ),
        )

        return ProviderResponse(
            provider_id=self.provider_id,
            model_id=model_id,
            content=content,
            request_id=None,
            usage=usage,
            metadata={
                "done": payload.get("done"),
                "done_reason": payload.get(
                    "done_reason"
                ),
                "total_duration": payload.get(
                    "total_duration"
                ),
                "load_duration": payload.get(
                    "load_duration"
                ),
                "prompt_eval_duration": payload.get(
                    "prompt_eval_duration"
                ),
                "eval_duration": payload.get(
                    "eval_duration"
                ),
                "thinking": message.get("thinking"),
            },
        )

    def _url(self, path: str) -> str:
        return (
            self.config.base_url.rstrip("/")
            + "/"
            + path.lstrip("/")
        )
