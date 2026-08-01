from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any, TypeVar
from urllib.parse import quote

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
    ProviderToolCall,
)

from .http_client import (
    AsyncJSONHTTPClient,
    ProviderHTTPError,
)


ResponseModel = TypeVar(
    "ResponseModel",
    bound=BaseModel,
)


class GeminiAdapter:
    """Native Google Gemini generateContent API adapter."""

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
            ProviderCapability.VISION,
            ProviderCapability.REASONING,
            ProviderCapability.CACHED_INPUT,
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
            parameters=parameters,
        )

        raw, headers = await self._generate(
            model_id=model_id,
            payload=payload,
        )

        return self._normalize_response(
            requested_model_id=model_id,
            payload=raw,
            headers=headers,
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
            parameters=parameters,
        )

        generation_config = dict(
            payload.get("generationConfig") or {}
        )
        generation_config.update(
            {
                "responseMimeType": "application/json",
                "responseJsonSchema": (
                    response_model.model_json_schema()
                ),
            }
        )
        payload["generationConfig"] = generation_config

        raw, headers = await self._generate(
            model_id=model_id,
            payload=payload,
        )

        normalized = self._normalize_response(
            requested_model_id=model_id,
            payload=raw,
            headers=headers,
        )

        if normalized.content is None:
            raise ProviderAdapterError(
                "Gemini returned no structured content."
            )

        try:
            parsed = response_model.model_validate_json(
                normalized.content
            )
        except Exception as exc:
            raise ProviderAdapterError(
                "Gemini structured response validation "
                f"failed: {exc}"
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
                url=self._models_url(),
                headers=self._headers(),
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
            message="Gemini API is reachable.",
            latency_ms=(
                time.perf_counter() - started
            )
            * 1000,
        )

    def _base_payload(
        self,
        *,
        messages: Sequence[ProviderMessage],
        parameters: dict[str, Any] | None,
    ) -> dict[str, Any]:
        system_parts: list[str] = []
        contents: list[dict[str, Any]] = []

        for message in messages:
            if message.role == "system":
                system_parts.append(message.content)
                continue

            role = {
                "user": "user",
                "assistant": "model",
                "tool": "user",
            }.get(message.role)

            if role is None:
                raise ProviderAdapterError(
                    f"Unsupported Gemini message role: "
                    f"{message.role}"
                )

            contents.append(
                {
                    "role": role,
                    "parts": [
                        {
                            "text": message.content,
                        }
                    ],
                }
            )

        if not contents:
            raise ProviderAdapterError(
                "Gemini requires at least one conversation message."
            )

        payload: dict[str, Any] = {
            "contents": contents,
        }

        if system_parts:
            payload["systemInstruction"] = {
                "parts": [
                    {
                        "text": "\n\n".join(system_parts),
                    }
                ]
            }

        defaults = dict(
            self.config.options.get(
                "generation_config",
                {},
            )
        )
        request_parameters = dict(parameters or {})

        generation_overrides = request_parameters.pop(
            "generation_config",
            {},
        )

        if not isinstance(generation_overrides, dict):
            raise ProviderAdapterError(
                "generation_config must be an object."
            )

        defaults.update(generation_overrides)

        direct_generation_keys = {
            "temperature",
            "topP",
            "topK",
            "candidateCount",
            "maxOutputTokens",
            "stopSequences",
            "presencePenalty",
            "frequencyPenalty",
            "seed",
            "thinkingConfig",
        }

        for key in list(request_parameters):
            if key in direct_generation_keys:
                defaults[key] = request_parameters.pop(
                    key
                )

        if defaults:
            payload["generationConfig"] = defaults

        allowed_top_level = {
            "tools",
            "toolConfig",
            "safetySettings",
            "cachedContent",
        }

        for key, value in request_parameters.items():
            if key not in allowed_top_level:
                raise ProviderAdapterError(
                    f"Unsupported Gemini parameter: {key}"
                )

            payload[key] = value

        return payload

    async def _generate(
        self,
        *,
        model_id: str,
        payload: dict[str, Any],
    ) -> tuple[
        dict[str, Any],
        dict[str, str],
    ]:
        try:
            response = await self.client.request(
                method="POST",
                url=self._generate_url(model_id),
                headers=self._headers(),
                payload=payload,
                timeout_seconds=self.config.timeout_seconds,
            )
        except ProviderHTTPError as exc:
            raise ProviderAdapterError(
                str(exc)
            ) from exc

        return response.payload, response.headers

    def _headers(self) -> dict[str, str]:
        headers = dict(self.config.headers)
        api_key = self.config.api_key()

        if api_key:
            headers.setdefault(
                "x-goog-api-key",
                api_key,
            )

        headers.setdefault(
            "Content-Type",
            "application/json",
        )

        return headers

    def _normalize_function_calls(
        self,
        function_calls: list[dict[str, Any]],
    ) -> list[ProviderToolCall]:
        normalized: list[ProviderToolCall] = []

        for index, item in enumerate(function_calls):
            function = item.get(
                "functionCall",
                item,
            )

            if not isinstance(function, dict):
                continue

            name = function.get("name")

            if not isinstance(name, str) or not name:
                continue

            arguments = function.get(
                "args",
                {},
            )

            if not isinstance(arguments, dict):
                arguments = {
                    "__value__": arguments,
                }

            call_id = (
                item.get("id")
                or function.get("id")
                or f"gemini_call_{index + 1}"
            )

            normalized.append(
                ProviderToolCall(
                    call_id=str(call_id),
                    tool_name=name,
                    arguments=dict(arguments),
                    provider_format="GEMINI",
                    raw=dict(item),
                )
            )

        return normalized

    def _normalize_response(
        self,
        *,
        requested_model_id: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> ProviderResponse:
        candidates = payload.get("candidates")

        if not isinstance(candidates, list) or not candidates:
            prompt_feedback = payload.get(
                "promptFeedback"
            )

            raise ProviderAdapterError(
                "Gemini response has no candidates. "
                f"promptFeedback={prompt_feedback!r}"
            )

        first = candidates[0]

        if not isinstance(first, dict):
            raise ProviderAdapterError(
                "Gemini response candidate is invalid."
            )

        content_payload = first.get("content") or {}

        if not isinstance(content_payload, dict):
            raise ProviderAdapterError(
                "Gemini candidate content is invalid."
            )

        parts = content_payload.get("parts") or []

        if not isinstance(parts, list):
            raise ProviderAdapterError(
                "Gemini content parts are invalid."
            )

        text_parts: list[str] = []
        function_calls: list[dict[str, Any]] = []
        thought_parts: list[dict[str, Any]] = []

        for part in parts:
            if not isinstance(part, dict):
                continue

            text = part.get("text")

            if isinstance(text, str):
                text_parts.append(text)

            function_call = part.get("functionCall")

            if isinstance(function_call, dict):
                function_calls.append(
                    function_call
                )

            if part.get("thought") is True:
                thought_parts.append(part)

        usage_payload = payload.get(
            "usageMetadata"
        ) or {}

        if not isinstance(usage_payload, dict):
            usage_payload = {}

        usage = NormalizedTokenUsage(
            input_tokens=int(
                usage_payload.get(
                    "promptTokenCount"
                )
                or 0
            ),
            cached_input_tokens=int(
                usage_payload.get(
                    "cachedContentTokenCount"
                )
                or 0
            ),
            output_tokens=int(
                usage_payload.get(
                    "candidatesTokenCount"
                )
                or 0
            ),
            reasoning_tokens=int(
                usage_payload.get(
                    "thoughtsTokenCount"
                )
                or 0
            ),
        )

        request_id = (
            headers.get("x-request-id")
            or headers.get("X-Request-Id")
            or headers.get("x-goog-request-id")
            or headers.get("X-Goog-Request-Id")
        )

        content = (
            "\n".join(text_parts)
            if text_parts
            else None
        )

        return ProviderResponse(
            provider_id=self.provider_id,
            model_id=requested_model_id,
            content=content,
            request_id=request_id,
            usage=usage,
            tool_calls=self._normalize_function_calls(
                function_calls
            ),
            metadata={
                "finish_reason": first.get(
                    "finishReason"
                ),
                "finish_message": first.get(
                    "finishMessage"
                ),
                "safety_ratings": first.get(
                    "safetyRatings"
                ),
                "citation_metadata": first.get(
                    "citationMetadata"
                ),
                "grounding_metadata": first.get(
                    "groundingMetadata"
                ),
                "function_calls": function_calls,
                "thought_parts": thought_parts,
                "model_version": payload.get(
                    "modelVersion"
                ),
                "response_id": payload.get(
                    "responseId"
                ),
                "total_token_count": (
                    usage_payload.get(
                        "totalTokenCount"
                    )
                    or 0
                ),
            },
        )

    def _generate_url(
        self,
        model_id: str,
    ) -> str:
        api_version = str(
            self.config.options.get(
                "api_version",
                "v1beta",
            )
        ).strip("/")

        encoded_model = quote(
            model_id,
            safe="-._",
        )

        return (
            self.config.base_url.rstrip("/")
            + f"/{api_version}/models/"
            + encoded_model
            + ":generateContent"
        )

    def _models_url(self) -> str:
        api_version = str(
            self.config.options.get(
                "api_version",
                "v1beta",
            )
        ).strip("/")

        return (
            self.config.base_url.rstrip("/")
            + f"/{api_version}/models"
        )
