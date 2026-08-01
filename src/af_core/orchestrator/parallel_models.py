from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ParallelTaskStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class AgentTaskAssignment(BaseModel):
    task_id: str
    agent_name: str
    agent_role: str
    workspace_path: str | None = None
    branch: str | None = None
    status: ParallelTaskStatus = ParallelTaskStatus.PENDING
    attempt: int = 0


class AgentTaskResult(BaseModel):
    task_id: str
    agent_name: str
    success: bool
    workspace_path: str
    branch: str
    changed_files: list[str] = Field(default_factory=list)
    diff_text: str = ""
    summary: str = ""
    error: str | None = None


class ParallelBatch(BaseModel):
    batch_number: int
    task_ids: list[str]
    maximum_parallelism: int


class ParallelExecutionResult(BaseModel):
    successful: bool
    batches: list[ParallelBatch] = Field(default_factory=list)
    task_results: dict[str, AgentTaskResult] = Field(
        default_factory=dict
    )
    failed_task_ids: list[str] = Field(default_factory=list)
    blocked_task_ids: list[str] = Field(default_factory=list)
