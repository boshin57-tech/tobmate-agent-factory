from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class AgentRole(StrEnum):
    PLANNER = "planner"
    IMPLEMENTER = "implementer"
    TESTER = "tester"
    REVIEWER = "reviewer"
    COMPLETION_AUDITOR = "completion_auditor"


class AgentStatus(StrEnum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ToolCall(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str


class AgentAction(BaseModel):
    action_type: Literal[
        "tool_call",
        "complete",
        "fail",
        "request_review",
    ]
    tool_call: ToolCall | None = None
    summary: str | None = None
    error: str | None = None

    @model_validator(mode="after")
    def validate_action(self) -> "AgentAction":
        if self.action_type == "tool_call" and self.tool_call is None:
            raise ValueError(
                "tool_call action requires tool_call details"
            )

        if self.action_type != "tool_call" and self.tool_call is not None:
            raise ValueError(
                "Only tool_call actions may contain tool_call details"
            )

        if self.action_type == "complete" and not self.summary:
            raise ValueError(
                "complete action requires a summary"
            )

        if self.action_type == "fail" and not self.error:
            raise ValueError(
                "fail action requires an error"
            )

        return self


class AgentProfile(BaseModel):
    name: str
    role: AgentRole
    capabilities: set[str] = Field(default_factory=set)
    allowed_tools: set[str] = Field(default_factory=set)
    maximum_steps: int = Field(default=20, ge=1, le=200)
    command_timeout_seconds: int = Field(
        default=60,
        ge=1,
        le=600,
    )


class AgentExecutionState(BaseModel):
    agent_name: str
    role: AgentRole
    status: AgentStatus = AgentStatus.IDLE
    step: int = 0
    tool_calls: list[ToolCall] = Field(default_factory=list)
    summaries: list[str] = Field(default_factory=list)
    last_error: str | None = None

    def begin(self) -> None:
        if self.status not in {
            AgentStatus.IDLE,
            AgentStatus.WAITING,
        }:
            raise ValueError(
                f"Agent cannot begin from state {self.status}"
            )

        self.status = AgentStatus.RUNNING

    def record_tool_call(self, call: ToolCall) -> None:
        if self.status is not AgentStatus.RUNNING:
            raise ValueError(
                "Agent must be running to record a tool call"
            )

        self.tool_calls.append(call)
        self.step += 1

    def complete(self, summary: str) -> None:
        if self.status is not AgentStatus.RUNNING:
            raise ValueError(
                "Agent must be running to complete"
            )

        self.summaries.append(summary)
        self.status = AgentStatus.COMPLETED

    def fail(self, error: str) -> None:
        self.last_error = error
        self.status = AgentStatus.FAILED
