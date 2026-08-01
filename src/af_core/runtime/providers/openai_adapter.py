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


class OpenAIAdapter:
    """Native OpenAI Responses API adapter."""

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
            model_id=model_id,
            parameters=parameters,
        )

        raw, headers = await self._post_response(
            payload
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
            model_id=model_id,
            parameters=parameters,
        )

        schema_name = (
            response_model.__name__
            .replace(" ", "_")
            .lower()
        )

        payload["text"] = {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": (
                    response_model.model_json_schema()
                ),
            }
        }

        raw, headers = await self._post_response(
            payload
        )

        normalized = self._normalize_response(
            requested_model_id=model_id,
            payload=raw,
            headers=headers,
        )

        refusal = normalized.metadata.get("refusal")

        if refusal:
            raise ProviderAdapterError(
                f"OpenAI refused structured output: {refusal}"
            )

        if normalized.content is None:
            raise ProviderAdapterError(
                "OpenAI returned no structured output."
            )

        try:
            parsed = response_model.model_validate_json(
                normalized.content
            )
        except Exception as exc:
            raise ProviderAdapterError(
                "OpenAI structured response validation "
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
                url=self._url("/v1/models"),
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
            message="OpenAI API is reachable.",
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
        input_items: list[dict[str, Any]] = []

        for message in messages:
            if message.role not in {
                "system",
                "user",
                "assistant",
                "developer",
            }:
                raise ProviderAdapterError(
                    f"Unsupported OpenAI message role: "
                    f"{message.role}"
                )

            input_items.append(
                {
                    "role": message.role,
                    "content": message.content,
                }
            )

        if not input_items:
            raise ProviderAdapterError(
                "OpenAI requires at least one input message."
            )

        payload: dict[str, Any] = {
            "model": model_id,
            "input": input_items,
        }

        defaults = dict(
            self.config.options.get(
                "response_parameters",
                {},
            )
        )
        defaults.update(parameters or {})

        protected = {
            "model",
            "input",
            "text",
        }

        for key, value in defaults.items():
            if key in protected:
                continue

            payload[key] = value

        return payload

    async def _post_response(
        self,
        payload: dict[str, Any],
    ) -> tuple[
        dict[str, Any],
        dict[str, str],
    ]:
        endpoint = self.config.options.get(
            "responses_path",
            "/v1/responses",
        )

        try:
            response = await self.client.request(
                method="POST",
                url=self._url(endpoint),
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
                "Authorization",
                f"Bearer {api_key}",
            )

        organization = self.config.options.get(
            "organization"
        )
        project = self.config.options.get(
            "project"
        )

        if organization:
            headers.setdefault(
                "OpenAI-Organization",
                str(organization),
            )

        if project:
            headers.setdefault(
                "OpenAI-Project",
                str(project),
            )

        headers.setdefault(
            "Content-Type",
            "application/json",
        )

        return headers

    def _normalize_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
    ) -> list[ProviderToolCall]:
        normalized: list[ProviderToolCall] = []

        for index, item in enumerate(tool_calls):
            name = item.get("name")

            if not isinstance(name, str) or not name:
                continue

            raw_arguments = item.get(
                "arguments",
                {},
            )

            if isinstance(raw_arguments, str):
                try:
                    arguments = json.loads(
                        raw_arguments
                    )
                except json.JSONDecodeError:
                    arguments = {
                        "__raw_arguments__": (
                            raw_arguments
                        ),
                    }
            elif isinstance(raw_arguments, dict):
                arguments = dict(raw_arguments)
            else:
                arguments = {
                    "__raw_arguments__": (
                        raw_arguments
                    ),
                }

            if not isinstance(arguments, dict):
                arguments = {
                    "__value__": arguments,
                }

            call_id = (
                item.get("call_id")
                or item.get("id")
                or f"openai_call_{index + 1}"
            )

            normalized.append(
                ProviderToolCall(
                    call_id=str(call_id),
                    tool_name=name,
                    arguments=arguments,
                    provider_format=(
                        "OPENAI_RESPONSES"
                    ),
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
        output = payload.get("output")

        if not isinstance(output, list):
            raise ProviderAdapterError(
                "OpenAI response output is invalid."
            )

        text_parts: list[str] = []
        refusals: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        output_types: list[str] = []

        for item in output:
            if not isinstance(item, dict):
                continue

            item_type = item.get("type")

            if isinstance(item_type, str):
                output_types.append(item_type)

            if item_type in {
                "function_call",
                "custom_tool_call",
                "computer_call",
            }:
                tool_calls.append(item)
                continue

            if item_type != "message":
                continue

            content_items = item.get("content") or []

            if not isinstance(content_items, list):
                continue

            for content_item in content_items:
                if not isinstance(content_item, dict):
                    continue

                content_type = content_item.get("type")

                if content_type == "output_text":
                    text = content_item.get("text")

                    if isinstance(text, str):
                        text_parts.append(text)

                elif content_type == "refusal":
                    refusal = content_item.get(
                        "refusal"
                    )

                    if isinstance(refusal, str):
                        refusals.append(refusal)

        usage_payload = payload.get("usage") or {}

        if not isinstance(usage_payload, dict):
            usage_payload = {}

        input_details = usage_payload.get(
            "input_tokens_details"
        ) or {}
        output_details = usage_payload.get(
            "output_tokens_details"
        ) or {}

        if not isinstance(input_details, dict):
            input_details = {}

        if not isinstance(output_details, dict):
            output_details = {}

        usage = NormalizedTokenUsage(
            input_tokens=int(
                usage_payload.get("input_tokens")
                or 0
            ),
            cached_input_tokens=int(
                input_details.get("cached_tokens")
                or 0
            ),
            output_tokens=int(
                usage_payload.get("output_tokens")
                or 0
            ),
            reasoning_tokens=int(
                output_details.get(
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

        content = (
            "\n".join(text_parts)
            if text_parts
            else None
        )
        refusal = (
            "\n".join(refusals)
            if refusals
            else None
        )

        incomplete_details = payload.get(
            "incomplete_details"
        )

        if not isinstance(
            incomplete_details,
            dict,
        ):
            incomplete_details = None

        return ProviderResponse(
            provider_id=self.provider_id,
            model_id=str(
                payload.get("model")
                or requested_model_id
            ),
            content=content,
            request_id=(
                str(request_id)
                if request_id is not None
                else None
            ),
            usage=usage,
            tool_calls=self._normalize_tool_calls(
                tool_calls
            ),
            metadata={
                "status": payload.get("status"),
                "created_at": payload.get(
                    "created_at"
                ),
                "completed_at": payload.get(
                    "completed_at"
                ),
                "refusal": refusal,
                "tool_calls": tool_calls,
                "output_types": output_types,
                "incomplete_details": (
                    incomplete_details
                ),
                "error": payload.get("error"),
                "service_tier": payload.get(
                    "service_tier"
                ),
                "store": payload.get("store"),
                "total_tokens": usage_payload.get(
                    "total_tokens"
                ),
            },
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
