from __future__ import annotations

import asyncio
import time
from typing import Any

from .models import (
    ExternalToolCall,
    ExternalToolDescriptor,
    ExternalToolHandler,
    ExternalToolResult,
    ToolAuditRecord,
    ToolExecutionStatus,
)
from .policy import ExternalToolPolicy


class ExternalToolRegistryError(RuntimeError):
    """Raised for invalid external tool registration."""


class ExternalToolRegistry:
    def __init__(
        self,
        *,
        policy: ExternalToolPolicy | None = None,
    ) -> None:
        self.policy = policy or ExternalToolPolicy()

        self._descriptors: dict[
            str,
            ExternalToolDescriptor,
        ] = {}

        self._handlers: dict[
            str,
            ExternalToolHandler,
        ] = {}

        self._audit: list[ToolAuditRecord] = []

    def register(
        self,
        *,
        descriptor: ExternalToolDescriptor,
        handler: ExternalToolHandler,
    ) -> None:
        tool_id = descriptor.tool_id.strip()

        if not tool_id:
            raise ExternalToolRegistryError(
                "Tool ID is required."
            )

        if tool_id in self._descriptors:
            raise ExternalToolRegistryError(
                f"Tool already registered: {tool_id}"
            )

        self._descriptors[tool_id] = descriptor
        self._handlers[tool_id] = handler

    def unregister(
        self,
        tool_id: str,
    ) -> None:
        if tool_id not in self._descriptors:
            raise ExternalToolRegistryError(
                f"Tool not registered: {tool_id}"
            )

        del self._descriptors[tool_id]
        del self._handlers[tool_id]

    def get(
        self,
        tool_id: str,
    ) -> ExternalToolDescriptor:
        try:
            return self._descriptors[tool_id]
        except KeyError as exc:
            raise ExternalToolRegistryError(
                f"Unknown external tool: {tool_id}"
            ) from exc

    def list(
        self,
        *,
        enabled_only: bool = True,
        tags: set[str] | None = None,
    ) -> list[ExternalToolDescriptor]:
        required_tags = tags or set()
        descriptors: list[
            ExternalToolDescriptor
        ] = []

        for descriptor in self._descriptors.values():
            if enabled_only and not descriptor.enabled:
                continue

            if (
                required_tags
                and not required_tags.issubset(
                    descriptor.tags
                )
            ):
                continue

            descriptors.append(descriptor)

        return sorted(
            descriptors,
            key=lambda item: item.tool_id,
        )

    async def execute(
        self,
        call: ExternalToolCall,
        *,
        approved: bool = False,
    ) -> ExternalToolResult:
        descriptor = self.get(call.tool_id)

        decision = self.policy.evaluate(
            descriptor=descriptor,
            call=call,
            approved=approved,
        )

        if not decision.allowed:
            result = ExternalToolResult(
                call_id=call.call_id,
                tool_id=call.tool_id,
                status=ToolExecutionStatus.BLOCKED,
                is_error=True,
                error="; ".join(decision.reasons),
            )

            self._record(
                call=call,
                descriptor=descriptor,
                result=result,
                reasons=decision.reasons,
            )

            return result

        validation_error = self._validate_arguments(
            descriptor.input_schema,
            call.arguments,
        )

        if validation_error is not None:
            result = ExternalToolResult(
                call_id=call.call_id,
                tool_id=call.tool_id,
                status=ToolExecutionStatus.FAILED,
                is_error=True,
                error=validation_error,
            )

            self._record(
                call=call,
                descriptor=descriptor,
                result=result,
                reasons=[],
            )

            return result

        handler = self._handlers[call.tool_id]
        started = time.perf_counter()

        try:
            result = await asyncio.wait_for(
                handler(call),
                timeout=descriptor.timeout_seconds,
            )
        except TimeoutError:
            result = ExternalToolResult(
                call_id=call.call_id,
                tool_id=call.tool_id,
                status=ToolExecutionStatus.TIMED_OUT,
                is_error=True,
                error=(
                    "Tool execution exceeded "
                    f"{descriptor.timeout_seconds} seconds."
                ),
            )
        except Exception as exc:
            result = ExternalToolResult(
                call_id=call.call_id,
                tool_id=call.tool_id,
                status=ToolExecutionStatus.FAILED,
                is_error=True,
                error=str(exc),
            )

        result.duration_ms = (
            time.perf_counter() - started
        ) * 1000.0

        self._record(
            call=call,
            descriptor=descriptor,
            result=result,
            reasons=decision.reasons,
        )

        return result

    def audit_records(
        self,
    ) -> list[ToolAuditRecord]:
        return list(self._audit)

    def _record(
        self,
        *,
        call: ExternalToolCall,
        descriptor: ExternalToolDescriptor,
        result: ExternalToolResult,
        reasons: list[str],
    ) -> None:
        self._audit.append(
            ToolAuditRecord(
                call=call,
                descriptor=descriptor,
                result=result,
                policy_reasons=list(reasons),
            )
        )

    def _validate_arguments(
        self,
        schema: dict[str, Any],
        arguments: dict[str, Any],
    ) -> str | None:
        if schema.get("type", "object") != "object":
            return (
                "Only object-shaped tool input schemas "
                "are currently supported."
            )

        properties = schema.get(
            "properties",
            {},
        )
        required = set(
            schema.get(
                "required",
                [],
            )
        )

        if not isinstance(properties, dict):
            return (
                "Tool input schema properties "
                "are invalid."
            )

        missing = sorted(
            required.difference(arguments)
        )

        if missing:
            return (
                "Missing required tool arguments: "
                + ", ".join(missing)
            )

        additional_allowed = schema.get(
            "additionalProperties",
            True,
        )

        if not additional_allowed:
            unknown = sorted(
                set(arguments).difference(
                    properties
                )
            )

            if unknown:
                return (
                    "Unknown tool arguments: "
                    + ", ".join(unknown)
                )

        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        for name, value in arguments.items():
            property_schema = properties.get(
                name
            )

            if not isinstance(
                property_schema,
                dict,
            ):
                continue

            expected_name = property_schema.get(
                "type"
            )
            expected_type = type_map.get(
                expected_name
            )

            if (
                expected_type is not None
                and not isinstance(
                    value,
                    expected_type,
                )
            ):
                return (
                    f"Argument {name!r} must be "
                    f"{expected_name}."
                )

        return None
