from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from af_core.tools.models import (
    ExternalToolResult,
    ToolContentType,
)

from .tool_call_models import (
    NormalizedToolCall,
    ProviderToolCallFormat,
    ProviderToolResultMessage,
)


class ToolCallNormalizationError(RuntimeError):
    """Raised when a provider tool call cannot be normalized."""


class ProviderToolCallNormalizer:
    def normalize_many(
        self,
        *,
        provider_format: ProviderToolCallFormat,
        payload: list[dict[str, Any]],
        provider_id: str | None = None,
        model_id: str | None = None,
    ) -> list[NormalizedToolCall]:
        return [
            self.normalize(
                provider_format=provider_format,
                payload=item,
                provider_id=provider_id,
                model_id=model_id,
            )
            for item in payload
        ]

    def normalize(
        self,
        *,
        provider_format: ProviderToolCallFormat,
        payload: dict[str, Any],
        provider_id: str | None = None,
        model_id: str | None = None,
    ) -> NormalizedToolCall:
        handlers = {
            ProviderToolCallFormat.OPENAI_RESPONSES: (
                self._openai_responses
            ),
            ProviderToolCallFormat.OPENAI_COMPATIBLE: (
                self._openai_compatible
            ),
            ProviderToolCallFormat.GEMINI: (
                self._gemini
            ),
            ProviderToolCallFormat.ANTHROPIC: (
                self._anthropic
            ),
            ProviderToolCallFormat.GENERIC: (
                self._generic
            ),
        }

        call = handlers[provider_format](payload)

        return call.model_copy(
            update={
                "provider_format": provider_format,
                "provider_id": provider_id,
                "model_id": model_id,
                "raw": dict(payload),
            }
        )

    def result_message(
        self,
        *,
        tool_call: NormalizedToolCall,
        result: ExternalToolResult,
    ) -> ProviderToolResultMessage:
        text_parts: list[str] = []
        json_parts: list[Any] = []
        resources: list[dict[str, Any]] = []

        for item in result.content:
            if (
                item.type is ToolContentType.TEXT
                and item.text is not None
            ):
                text_parts.append(item.text)

            elif item.type is ToolContentType.JSON:
                json_parts.append(item.json_value)

            elif item.type in {
                ToolContentType.RESOURCE,
                ToolContentType.IMAGE,
            }:
                resources.append(
                    item.model_dump(mode="json")
                )

        payload: dict[str, Any] = {
            "status": result.status.value,
            "is_error": result.is_error,
        }

        if text_parts:
            payload["text"] = "\n".join(text_parts)

        if json_parts:
            payload["json"] = (
                json_parts[0]
                if len(json_parts) == 1
                else json_parts
            )

        if resources:
            payload["resources"] = resources

        if result.error:
            payload["error"] = result.error

        return ProviderToolResultMessage(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            content=json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
            ),
            is_error=result.is_error,
            metadata={
                "tool_id": result.tool_id,
                "duration_ms": result.duration_ms,
                **result.metadata,
            },
        )

    def _openai_responses(
        self,
        payload: dict[str, Any],
    ) -> NormalizedToolCall:
        name = payload.get("name")
        arguments = payload.get("arguments")
        call_id = (
            payload.get("call_id")
            or payload.get("id")
        )

        return self._build(
            name=name,
            arguments=arguments,
            call_id=call_id,
        )

    def _openai_compatible(
        self,
        payload: dict[str, Any],
    ) -> NormalizedToolCall:
        function = payload.get("function") or {}

        if not isinstance(function, dict):
            raise ToolCallNormalizationError(
                "OpenAI-compatible function payload "
                "must be an object."
            )

        return self._build(
            name=function.get("name"),
            arguments=function.get("arguments"),
            call_id=payload.get("id"),
        )

    def _gemini(
        self,
        payload: dict[str, Any],
    ) -> NormalizedToolCall:
        function = payload.get("functionCall", payload)

        if not isinstance(function, dict):
            raise ToolCallNormalizationError(
                "Gemini functionCall must be an object."
            )

        return self._build(
            name=function.get("name"),
            arguments=function.get("args"),
            call_id=(
                payload.get("id")
                or function.get("id")
            ),
        )

    def _anthropic(
        self,
        payload: dict[str, Any],
    ) -> NormalizedToolCall:
        return self._build(
            name=payload.get("name"),
            arguments=payload.get("input"),
            call_id=payload.get("id"),
        )

    def _generic(
        self,
        payload: dict[str, Any],
    ) -> NormalizedToolCall:
        return self._build(
            name=(
                payload.get("tool_name")
                or payload.get("name")
            ),
            arguments=payload.get(
                "arguments",
                {},
            ),
            call_id=(
                payload.get("call_id")
                or payload.get("id")
            ),
        )

    def _build(
        self,
        *,
        name: Any,
        arguments: Any,
        call_id: Any,
    ) -> NormalizedToolCall:
        if not isinstance(name, str) or not name.strip():
            raise ToolCallNormalizationError(
                "Tool call name is required."
            )

        parsed_arguments = self._arguments(
            arguments
        )

        resolved_call_id = (
            str(call_id)
            if call_id is not None
            else f"call_{uuid4().hex}"
        )

        return NormalizedToolCall(
            call_id=resolved_call_id,
            tool_name=name.strip(),
            arguments=parsed_arguments,
        )

    def _arguments(
        self,
        value: Any,
    ) -> dict[str, Any]:
        if value is None:
            return {}

        if isinstance(value, dict):
            return dict(value)

        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ToolCallNormalizationError(
                    "Tool call arguments are not valid JSON: "
                    f"{exc}"
                ) from exc

            if not isinstance(parsed, dict):
                raise ToolCallNormalizationError(
                    "Tool call arguments must decode "
                    "to an object."
                )

            return parsed

        raise ToolCallNormalizationError(
            "Tool call arguments must be an object "
            "or JSON object string."
        )
