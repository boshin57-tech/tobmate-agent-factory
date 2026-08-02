"""Workflow orchestration domain models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPENSATING = "compensating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStepStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATED = "compensated"
    SKIPPED = "skipped"


class WorkflowDecision(StrEnum):
    SCHEDULE = "schedule"
    WAIT = "wait"
    RETRY = "retry"
    COMPENSATE = "compensate"
    COMPLETE = "complete"
    FAIL = "fail"


class WorkflowStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    step_id: str = Field(min_length=1)
    name: str = Field(min_length=1)

    dependency_ids: frozenset[str] = frozenset()
    required_capability_ids: frozenset[str] = frozenset()

    maximum_attempts: int = Field(default=1, ge=1)
    compensation_step_id: str | None = None

    status: WorkflowStepStatus = WorkflowStepStatus.PENDING
    attempt_count: int = Field(default=0, ge=0)

    assigned_agent_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class WorkflowDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    workflow_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)

    steps: tuple[WorkflowStep, ...]
    metadata: dict[str, object] = Field(default_factory=dict)


class WorkflowRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str = Field(
        default_factory=lambda: str(uuid4())
    )
    workflow_id: str = Field(min_length=1)
    workflow_version: int = Field(ge=1)

    status: WorkflowStatus = WorkflowStatus.PENDING
    steps: tuple[WorkflowStep, ...]

    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)

    metadata: dict[str, object] = Field(default_factory=dict)


class WorkflowScheduleDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision_id: str = Field(
        default_factory=lambda: str(uuid4())
    )
    run_id: str
    step_id: str | None = None

    decision: WorkflowDecision
    reason: str = ""

    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, object] = Field(default_factory=dict)


class WorkflowCheckpoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    checkpoint_id: str = Field(
        default_factory=lambda: str(uuid4())
    )
    run_id: str
    sequence: int = Field(ge=1)

    status: WorkflowStatus
    steps: tuple[WorkflowStep, ...]

    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, object] = Field(default_factory=dict)
