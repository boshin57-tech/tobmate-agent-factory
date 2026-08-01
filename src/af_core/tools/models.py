from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ExternalToolRisk(StrEnum):
    READ_ONLY = "READ_ONLY"
    WORKSPACE_WRITE = "WORKSPACE_WRITE"
    EXTERNAL_WRITE = "EXTERNAL_WRITE"
    PRIVILEGED = "PRIVILEGED"


class ExternalToolTransport(StrEnum):
    INTERNAL = "INTERNAL"
    MCP_STDIO = "MCP_STDIO"
    MCP_HTTP = "MCP_HTTP"
    REST = "REST"


class ToolExecutionStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    TIMED_OUT = "TIMED_OUT"


class ExternalToolDescriptor(BaseModel):
    tool_id: str
    name: str
    description: str
    input_schema: dict[str, Any] = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {},
        }
    )
    output_schema: dict[str, Any] | None = None
    risk: ExternalToolRisk = ExternalToolRisk.READ_ONLY
    transport: ExternalToolTransport = (
        ExternalToolTransport.INTERNAL
    )
    provider_id: str | None = None
    server_id: str | None = None
    tags: set[str] = Field(default_factory=set)
    timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        le=3600,
    )
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExternalToolCall(BaseModel):
    call_id: str
    tool_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    project_id: str | None = None
    run_id: str | None = None
    task_id: str | None = None
    agent_name: str | None = None
    requested_at: datetime = Field(default_factory=utc_now)


class ToolContentType(StrEnum):
    TEXT = "TEXT"
    JSON = "JSON"
    RESOURCE = "RESOURCE"
    IMAGE = "IMAGE"


class ToolContent(BaseModel):
    type: ToolContentType
    text: str | None = None
    json_value: Any | None = None
    uri: str | None = None
    mime_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExternalToolResult(BaseModel):
    call_id: str
    tool_id: str
    status: ToolExecutionStatus
    content: list[ToolContent] = Field(default_factory=list)
    is_error: bool = False
    error: str | None = None
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime = Field(default_factory=utc_now)
    duration_ms: float = Field(default=0.0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolAuditRecord(BaseModel):
    call: ExternalToolCall
    descriptor: ExternalToolDescriptor
    result: ExternalToolResult
    policy_reasons: list[str] = Field(default_factory=list)


class ExternalToolHandler(Protocol):
    async def __call__(
        self,
        call: ExternalToolCall,
    ) -> ExternalToolResult:
        ...
