from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class ToolRiskLevel(IntEnum):
    READ_ONLY = 0
    LOCAL_ANALYSIS = 1
    WORKSPACE_MUTATION = 2
    REPOSITORY_MUTATION = 3
    EXTERNAL_SIDE_EFFECT = 4
    PRODUCTION_CRITICAL = 5


class ToolRegistryError(RuntimeError):
    """Raised for invalid tool registration or access."""


ToolHandler = Callable[..., Any]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    risk_level: ToolRiskLevel
    handler: ToolHandler
    allowed_roles: frozenset[str]
    requires_workspace: bool = True


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if not definition.name:
            raise ToolRegistryError("Tool name is required")

        if definition.name in self._tools:
            raise ToolRegistryError(
                f"Tool already registered: {definition.name}"
            )

        self._tools[definition.name] = definition

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolRegistryError(
                f"Unknown tool: {name}"
            ) from exc

    def authorize(
        self,
        *,
        tool_name: str,
        agent_role: str,
        allowed_tools: set[str],
        maximum_risk: ToolRiskLevel,
    ) -> ToolDefinition:
        tool = self.get(tool_name)

        if tool_name not in allowed_tools:
            raise ToolRegistryError(
                f"Agent is not allowed to use tool: {tool_name}"
            )

        if agent_role not in tool.allowed_roles:
            raise ToolRegistryError(
                f"Role {agent_role} cannot use tool {tool_name}"
            )

        if tool.risk_level > maximum_risk:
            raise ToolRegistryError(
                f"Tool risk exceeds permitted level: {tool_name}"
            )

        return tool

    def list(self) -> list[ToolDefinition]:
        return sorted(
            self._tools.values(),
            key=lambda item: item.name,
        )
