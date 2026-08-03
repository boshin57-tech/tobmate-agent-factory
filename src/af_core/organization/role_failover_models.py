from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from .dynamic_role_models import (
    DynamicRoleAssignment,
    DynamicRoleRequirement,
    RoleAssignmentResult,
)


class RoleHealthDecision(str, Enum):
    KEEP = "keep"
    REASSIGN = "reassign"
    FAILOVER = "failover"
    BLOCKED = "blocked"


class RoleHealthTrigger(str, Enum):
    HEALTHY = "healthy"

    METRICS_UNAVAILABLE = (
        "metrics_unavailable"
    )

    AGENT_OFFLINE = (
        "agent_offline"
    )

    AGENT_SUSPENDED = (
        "agent_suspended"
    )

    WORKLOAD_EXCEEDED = (
        "workload_exceeded"
    )

    FAILURE_THRESHOLD_EXCEEDED = (
        "failure_threshold_exceeded"
    )

    SUCCESS_RATE_DEGRADED = (
        "success_rate_degraded"
    )

    QUALITY_DEGRADED = (
        "quality_degraded"
    )

    RELIABILITY_DEGRADED = (
        "reliability_degraded"
    )

    HEARTBEAT_STALE = (
        "heartbeat_stale"
    )


class ReassignmentPolicy(BaseModel):
    """
    Runtime policy used to determine whether an active role should
    remain assigned, be reassigned, or immediately fail over.
    """

    require_runtime_metrics: bool = True

    maximum_workload_ratio: float = 0.90

    maximum_consecutive_failures: int = 3

    minimum_success_rate: float = 0.80

    minimum_quality_score: float = 70.0

    minimum_reliability_score: float = 75.0

    maximum_heartbeat_age_seconds: int = 300

    failover_on_offline: bool = True

    failover_on_suspended: bool = True

    reassign_on_overload: bool = True

    reassign_on_performance_degradation: bool = True

    release_previous_after_replacement: bool = True

    activate_replacement_automatically: bool = True

    @field_validator(
        "maximum_workload_ratio",
        "minimum_success_rate",
    )
    @classmethod
    def validate_ratio(
        cls,
        value: float,
    ) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError(
                "ratio must be between 0.0 and 1.0"
            )

        return value

    @field_validator(
        "minimum_quality_score",
        "minimum_reliability_score",
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

    @field_validator(
        "maximum_consecutive_failures",
        "maximum_heartbeat_age_seconds",
    )
    @classmethod
    def validate_non_negative(
        cls,
        value: int,
    ) -> int:
        if value < 0:
            raise ValueError(
                "policy value must not be negative"
            )

        return value


class RoleHealthAssessment(BaseModel):
    assignment_id: str
    team_id: str
    role_name: str
    agent_id: str

    decision: RoleHealthDecision

    triggers: list[
        RoleHealthTrigger
    ] = Field(
        default_factory=list
    )

    reasons: list[str] = Field(
        default_factory=list
    )

    metrics_available: bool

    evaluated_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    @property
    def action_required(self) -> bool:
        return self.decision in {
            RoleHealthDecision.REASSIGN,
            RoleHealthDecision.FAILOVER,
        }


class RoleFailoverRequest(BaseModel):
    failover_request_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    assignment_id: str

    team_id: str
    workspace_id: str

    requirement: DynamicRoleRequirement

    requested_by: str

    metadata: dict[str, str] = Field(
        default_factory=dict
    )

    @field_validator(
        "assignment_id",
        "team_id",
        "workspace_id",
        "requested_by",
    )
    @classmethod
    def validate_required_text(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "value must not be empty"
            )

        return normalized


class RoleFailoverResult(BaseModel):
    failover_request_id: str

    assessment: RoleHealthAssessment

    previous_assignment: (
        DynamicRoleAssignment
        | None
    ) = None

    replacement_assignment: (
        DynamicRoleAssignment
        | None
    ) = None

    selection_result: (
        RoleAssignmentResult
        | None
    ) = None

    completed: bool = False

    previous_assignment_released: bool = False

    reasons: list[str] = Field(
        default_factory=list
    )
