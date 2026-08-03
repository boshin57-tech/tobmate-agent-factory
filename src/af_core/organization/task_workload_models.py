from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from .task_coordination_models import (
    CoordinatedTask,
)


class TaskAgentAvailability(str, Enum):
    AVAILABLE = "available"
    BUSY = "busy"
    OVERLOADED = "overloaded"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    MAINTENANCE = "maintenance"


class TaskReassignmentReason(str, Enum):
    AGENT_OFFLINE = "agent_offline"
    AGENT_OVERLOADED = "agent_overloaded"
    AGENT_DEGRADED = "agent_degraded"
    TASK_FAILURE = "task_failure"
    CAPABILITY_MISMATCH = "capability_mismatch"
    PRIORITY_REBALANCE = "priority_rebalance"
    MANUAL_REQUEST = "manual_request"
    CAPACITY_EXCEEDED = "capacity_exceeded"


class TaskReassignmentDecision(str, Enum):
    NOT_REQUIRED = "not_required"
    REASSIGN = "reassign"
    BLOCKED = "blocked"
    ESCALATE = "escalate"


class TaskAgentRuntimeProfile(BaseModel):
    agent_id: str
    agent_name: str = ""

    capabilities: set[str] = Field(
        default_factory=set
    )

    supported_tasks: set[str] = Field(
        default_factory=set
    )

    availability: TaskAgentAvailability = (
        TaskAgentAvailability.AVAILABLE
    )

    current_task_count: int = 0
    maximum_task_count: int = 1

    workload_ratio: float = 0.0

    success_rate: float = 1.0
    quality_score: float = 100.0
    reliability_score: float = 100.0

    consecutive_failures: int = 0

    average_response_ms: float = 0.0

    metadata: dict[str, str] = Field(
        default_factory=dict
    )

    @field_validator(
        "agent_id",
    )
    @classmethod
    def validate_agent_id(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "agent_id must not be empty"
            )

        return normalized

    @field_validator(
        "current_task_count",
        "consecutive_failures",
    )
    @classmethod
    def validate_non_negative_integer(
        cls,
        value: int,
    ) -> int:
        if value < 0:
            raise ValueError(
                "value must not be negative"
            )

        return value

    @field_validator(
        "maximum_task_count",
    )
    @classmethod
    def validate_maximum_task_count(
        cls,
        value: int,
    ) -> int:
        if value < 1:
            raise ValueError(
                "maximum_task_count must be at least 1"
            )

        return value

    @field_validator(
        "workload_ratio",
        "success_rate",
    )
    @classmethod
    def validate_ratio(
        cls,
        value: float,
    ) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError(
                "ratio must be between 0 and 1"
            )

        return value

    @field_validator(
        "quality_score",
        "reliability_score",
    )
    @classmethod
    def validate_score(
        cls,
        value: float,
    ) -> float:
        if not 0.0 <= value <= 100.0:
            raise ValueError(
                "score must be between 0 and 100"
            )

        return value

    @property
    def remaining_capacity(self) -> int:
        return max(
            0,
            self.maximum_task_count
            - self.current_task_count,
        )

    @property
    def has_capacity(self) -> bool:
        return (
            self.remaining_capacity > 0
            and self.workload_ratio < 1.0
        )


class TaskAgentScore(BaseModel):
    agent_id: str
    task_id: str

    capability_score: float = 0.0
    supported_task_score: float = 0.0
    capacity_score: float = 0.0
    workload_score: float = 0.0
    performance_score: float = 0.0
    reliability_score: float = 0.0
    availability_score: float = 0.0

    total_score: float = 0.0

    eligible: bool = False

    matched_capabilities: set[str] = Field(
        default_factory=set
    )

    missing_capabilities: set[str] = Field(
        default_factory=set
    )

    matched_tasks: set[str] = Field(
        default_factory=set
    )

    missing_tasks: set[str] = Field(
        default_factory=set
    )

    reasons: list[str] = Field(
        default_factory=list
    )


class TaskAgentSelectionResult(BaseModel):
    task_id: str

    selected_agent_id: str | None = None

    ranked_candidates: list[
        TaskAgentScore
    ] = Field(
        default_factory=list
    )

    eligible_agent_ids: list[str] = Field(
        default_factory=list
    )

    excluded_agent_ids: list[str] = Field(
        default_factory=list
    )

    fulfilled: bool = False

    reasons: list[str] = Field(
        default_factory=list
    )


class TaskReassignmentAssessment(BaseModel):
    workflow_id: str
    task_id: str

    current_agent_id: str | None = None

    decision: TaskReassignmentDecision

    reasons: list[
        TaskReassignmentReason
    ] = Field(
        default_factory=list
    )

    details: list[str] = Field(
        default_factory=list
    )

    replacement_required: bool = False


class TaskReassignmentRequest(BaseModel):
    request_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    workflow_id: str
    task_id: str

    requested_by: str

    reason: TaskReassignmentReason

    excluded_agent_ids: set[str] = Field(
        default_factory=set
    )

    force: bool = False

    metadata: dict[str, str] = Field(
        default_factory=dict
    )

    requested_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )


class TaskReassignmentRecord(BaseModel):
    reassignment_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    request_id: str

    workflow_id: str
    task_id: str

    previous_agent_id: str | None = None
    replacement_agent_id: str | None = None

    reason: TaskReassignmentReason

    decision: TaskReassignmentDecision

    previous_assignment_released: bool = False
    replacement_assignment_created: bool = False

    replacement_score: float = 0.0

    details: list[str] = Field(
        default_factory=list
    )

    created_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )


class TaskReassignmentResult(BaseModel):
    assessment: TaskReassignmentAssessment

    record: TaskReassignmentRecord

    task: CoordinatedTask

    completed: bool = False

    previous_agent_id: str | None = None
    replacement_agent_id: str | None = None

    reasons: list[str] = Field(
        default_factory=list
    )
