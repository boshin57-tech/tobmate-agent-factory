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


class OpenAICompatibleAdapter:
    """
    Adapter for servers implementing OpenAI-compatible
    Chat Completions endpoints.

    Compatible targets commonly include:
    - vLLM
    - LM Studio
    - LocalAI
    - other /v1/chat/completions servers
    """

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
        capabilities = {
            ProviderCapability.TEXT,
            ProviderCapability.STRUCTURED_OUTPUT,
            ProviderCapability.TOOL_CALLING,
        }

        configured = self.config.options.get(
            "capabilities",
            [],
        )

        for value in configured:
            try:
                capabilities.add(
                    ProviderCapability(value)
                )
            except ValueError:
                continue

        return capabilities

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

        raw, headers = await self._post(
            payload
        )

        return self._normalize_response(
            model_id=model_id,
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
            model_id=model_id,
            parameters=parameters,
        )

        schema_name = (
            response_model.__name__
            .replace(" ", "_")
            .lower()
        )

        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": response_model.model_json_schema(),
            },
        }

        raw, headers = await self._post(
            payload
        )

        normalized = self._normalize_response(
            model_id=model_id,
            payload=raw,
            headers=headers,
        )

        if normalized.content is None:
            raise ProviderAdapterError(
                "OpenAI-compatible provider returned "
                "no structured content."
            )

        try:
            parsed = response_model.model_validate_json(
                normalized.content
            )
        except Exception as exc:
            raise ProviderAdapterError(
                "OpenAI-compatible structured response "
                f"validation failed: {exc}"
            ) from exc

        normalized.parsed = parsed.model_dump(
            mode="json"
        )

        return parsed, normalized

    async def health(self) -> ProviderHealth:
        started = time.perf_counter()

        health_path = self.config.options.get(
            "health_path",
            "/v1/models",
        )

        try:
            await self.client.request(
                method="GET",
                url=self._url(health_path),
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
            message=(
                "OpenAI-compatible API is reachable."
            ),
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

        defaults = dict(
            self.config.options.get(
                "generation_parameters",
                {},
            )
        )
        defaults.update(parameters or {})

        protected = {
            "model",
            "messages",
            "stream",
            "response_format",
        }

        for key, value in defaults.items():
            if key in protected:
                continue

            payload[key] = value

        return payload

    async def _post(
        self,
        payload: dict[str, Any],
    ) -> tuple[
        dict[str, Any],
        dict[str, str],
    ]:
        endpoint = self.config.options.get(
            "chat_completions_path",
            "/v1/chat/completions",
        )

        try:
            response = await self.client.request(
                method="POST",
                url=self._url(endpoint),
                headers=self.config.resolved_headers(),
                payload=payload,
                timeout_seconds=self.config.timeout_seconds,
            )
        except ProviderHTTPError as exc:
            raise ProviderAdapterError(
                str(exc)
            ) from exc

        return response.payload, response.headers

    def _normalize_response(
        self,
        *,
        model_id: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> ProviderResponse:
        choices = payload.get("choices")

        if not isinstance(choices, list) or not choices:
            raise ProviderAdapterError(
                "OpenAI-compatible response has no choices."
            )

        first = choices[0]

        if not isinstance(first, dict):
            raise ProviderAdapterError(
                "OpenAI-compatible response choice is invalid."
            )

        message = first.get("message")

        if not isinstance(message, dict):
            raise ProviderAdapterError(
                "OpenAI-compatible response message is invalid."
            )

        content = self._normalize_content(
            message.get("content")
        )

        usage_payload = payload.get("usage") or {}

        if not isinstance(usage_payload, dict):
            usage_payload = {}

        prompt_details = usage_payload.get(
            "prompt_tokens_details"
        ) or {}

        completion_details = usage_payload.get(
            "completion_tokens_details"
        ) or {}

        if not isinstance(prompt_details, dict):
            prompt_details = {}

        if not isinstance(completion_details, dict):
            completion_details = {}

        usage = NormalizedTokenUsage(
            input_tokens=int(
                usage_payload.get("prompt_tokens")
                or usage_payload.get("input_tokens")
                or 0
            ),
            cached_input_tokens=int(
                prompt_details.get("cached_tokens")
                or 0
            ),
            output_tokens=int(
                usage_payload.get("completion_tokens")
                or usage_payload.get("output_tokens")
                or 0
            ),
            reasoning_tokens=int(
                completion_details.get(
                    "reasoning_tokens"
                )
                or 0
            ),
        )

        request_id = (
            payload.get("id")
            or headers.get("x-request-id")
            or headers.get("X-Request-Id")
        )

        return ProviderResponse(
            provider_id=self.provider_id,
            model_id=str(
                payload.get("model") or model_id
            ),
            content=content,
            request_id=(
                str(request_id)
                if request_id is not None
                else None
            ),
            usage=usage,
            metadata={
                "finish_reason": first.get(
                    "finish_reason"
                ),
                "system_fingerprint": payload.get(
                    "system_fingerprint"
                ),
                "created": payload.get("created"),
                "tool_calls": message.get(
                    "tool_calls"
                ),
                "refusal": message.get(
                    "refusal"
                ),
            },
        )

    def _normalize_content(
        self,
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        if isinstance(value, str):
            return value

        if isinstance(value, list):
            text_parts: list[str] = []

            for item in value:
                if not isinstance(item, dict):
                    continue

                if item.get("type") in {
                    "text",
                    "output_text",
                }:
                    text = item.get("text")

                    if isinstance(text, str):
                        text_parts.append(text)

            return "\n".join(text_parts)

        raise ProviderAdapterError(
            "OpenAI-compatible message content "
            "has an unsupported format."
        )

    def _url(
        self,
        path: str,
    ) -> str:
        return (
            self.config.base_url.rstrip("/")
            + "/"
            + path.lstrip("/")
        )
