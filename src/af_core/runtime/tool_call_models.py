from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from af_core.tools.models import (
    ExternalToolCall,
    ExternalToolResult,
    ToolExecutionStatus,
)


class ProviderToolCallFormat(StrEnum):
    OPENAI_RESPONSES = "OPENAI_RESPONSES"
    OPENAI_COMPATIBLE = "OPENAI_COMPATIBLE"
    GEMINI = "GEMINI"
    ANTHROPIC = "ANTHROPIC"
    GENERIC = "GENERIC"


class NormalizedToolCall(BaseModel):
    call_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(
        default_factory=dict
    )
    provider_format: ProviderToolCallFormat = (
        ProviderToolCallFormat.GENERIC
    )
    provider_id: str | None = None
    model_id: str | None = None
    raw: dict[str, Any] = Field(
        default_factory=dict
    )

    def to_external_call(
        self,
        *,
        tool_id: str | None = None,
        project_id: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
        agent_name: str | None = None,
    ) -> ExternalToolCall:
        return ExternalToolCall(
            call_id=self.call_id,
            tool_id=tool_id or self.tool_name,
            arguments=dict(self.arguments),
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            agent_name=agent_name,
        )


class ToolCallExecutionRecord(BaseModel):
    call: NormalizedToolCall
    external_call: ExternalToolCall
    result: ExternalToolResult
    approved: bool = False

    @property
    def successful(self) -> bool:
        return (
            self.result.status
            is ToolExecutionStatus.SUCCEEDED
            and not self.result.is_error
        )


class ToolCallBatchResult(BaseModel):
    records: list[ToolCallExecutionRecord] = Field(
        default_factory=list
    )

    @property
    def successful(self) -> bool:
        return all(
            record.successful
            for record in self.records
        )

    @property
    def failed_call_ids(self) -> list[str]:
        return [
            record.call.call_id
            for record in self.records
            if not record.successful
        ]


class ProviderToolResultMessage(BaseModel):
    role: str = "tool"
    call_id: str
    tool_name: str
    content: str
    is_error: bool = False
    metadata: dict[str, Any] = Field(
        default_factory=dict
    )
