"""Multi-agent coordination domain models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CoordinationAgentStatus(StrEnum):
    ACTIVE = "active"
    BUSY = "busy"
    PAUSED = "paused"
    OFFLINE = "offline"


class CoordinationTaskStatus(StrEnum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


class CoordinationConflictType(StrEnum):
    DUPLICATE_ASSIGNMENT = "duplicate_assignment"
    CAPABILITY_MISMATCH = "capability_mismatch"
    AUTHORITY_DENIED = "authority_denied"
    DEPENDENCY_BLOCKED = "dependency_blocked"
    RESOURCE_CONFLICT = "resource_conflict"


class CoordinationDecision(StrEnum):
    ASSIGN = "assign"
    REASSIGN = "reassign"
    BLOCK = "block"
    WAIT = "wait"
    COMPLETE = "complete"


class CoordinationAgent(BaseModel):
    model_config = ConfigDict(frozen=True)

    agent_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    role: str = Field(min_length=1)

    capability_ids: frozenset[str] = frozenset()
    status: CoordinationAgentStatus = (
        CoordinationAgentStatus.ACTIVE
    )

    maximum_parallel_tasks: int = Field(
        default=1,
        ge=1,
    )
    metadata: dict[str, object] = Field(
        default_factory=dict
    )


class CoordinationTask(BaseModel):
    model_config = ConfigDict(frozen=True)

    task_id: str = Field(min_length=1)
    name: str = Field(min_length=1)

    required_capability_ids: frozenset[str] = (
        frozenset()
    )
    dependency_ids: frozenset[str] = frozenset()

    priority: int = Field(default=0, ge=0)
    status: CoordinationTaskStatus = (
        CoordinationTaskStatus.PENDING
    )

    assigned_agent_id: str | None = None
    metadata: dict[str, object] = Field(
        default_factory=dict
    )


class CoordinationAssignment(BaseModel):
    model_config = ConfigDict(frozen=True)

    assignment_id: str = Field(
        default_factory=lambda: str(uuid4())
    )
    task_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)

    decision: CoordinationDecision
    reason: str = ""

    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, object] = Field(
        default_factory=dict
    )


class CoordinationConflict(BaseModel):
    model_config = ConfigDict(frozen=True)

    conflict_id: str = Field(
        default_factory=lambda: str(uuid4())
    )
    conflict_type: CoordinationConflictType

    task_id: str | None = None
    agent_id: str | None = None

    reason: str = ""
    resolved: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class CoordinationSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    agent_count: int
    task_count: int
    active_assignment_count: int
    unresolved_conflict_count: int

    created_at: datetime = Field(default_factory=utc_now)
