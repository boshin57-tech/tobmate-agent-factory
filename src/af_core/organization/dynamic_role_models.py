from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class RoleAssignmentAction(str, Enum):
    ASSIGN = "assign"
    REASSIGN = "reassign"
    RELEASE = "release"
    PROMOTE = "promote"
    DEMOTE = "demote"
    FAILOVER = "failover"


class RoleAssignmentReason(str, Enum):
    INITIAL_ASSIGNMENT = (
        "initial_assignment"
    )

    CAPABILITY_MATCH = (
        "capability_match"
    )

    AGENT_UNAVAILABLE = (
        "agent_unavailable"
    )

    AGENT_OVERLOADED = (
        "agent_overloaded"
    )

    PERFORMANCE_DEGRADED = (
        "performance_degraded"
    )

    HIGHER_PRIORITY_TASK = (
        "higher_priority_task"
    )

    ROLE_REQUIREMENT_CHANGED = (
        "role_requirement_changed"
    )

    MANUAL_OVERRIDE = (
        "manual_override"
    )

    FAILOVER_REQUIRED = (
        "failover_required"
    )


class RoleAssignmentStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    ACTIVE = "active"
    REJECTED = "rejected"
    RELEASED = "released"
    SUPERSEDED = "superseded"


class DynamicRoleRequirement(BaseModel):
    """
    Runtime role requirement used for dynamic assignment.
    """

    role_name: str

    required_capabilities: set[str] = Field(
        default_factory=set
    )

    required_tasks: set[str] = Field(
        default_factory=set
    )

    minimum_skill_level: int = 1

    priority: int = 5

    exclusive: bool = True

    minimum_assignments: int = 1
    maximum_assignments: int = 1

    metadata: dict[str, str] = Field(
        default_factory=dict
    )

    @field_validator("role_name")
    @classmethod
    def validate_role_name(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "role_name must not be empty"
            )

        return normalized

    @field_validator("minimum_skill_level")
    @classmethod
    def validate_skill_level(
        cls,
        value: int,
    ) -> int:
        if value < 1:
            raise ValueError(
                "minimum_skill_level "
                "must be at least 1"
            )

        return value

    @field_validator("priority")
    @classmethod
    def validate_priority(
        cls,
        value: int,
    ) -> int:
        if not 0 <= value <= 9:
            raise ValueError(
                "priority must be "
                "between 0 and 9"
            )

        return value

    @field_validator(
        "minimum_assignments",
        "maximum_assignments",
    )
    @classmethod
    def validate_assignment_count(
        cls,
        value: int,
    ) -> int:
        if value < 1:
            raise ValueError(
                "assignment count "
                "must be at least 1"
            )

        return value

    def model_post_init(
        self,
        __context: object,
    ) -> None:
        if (
            self.maximum_assignments
            < self.minimum_assignments
        ):
            raise ValueError(
                "maximum_assignments must "
                "not be less than "
                "minimum_assignments"
            )


class RoleAssignmentRequest(BaseModel):
    request_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    team_id: str
    workspace_id: str

    requirement: DynamicRoleRequirement

    action: RoleAssignmentAction = (
        RoleAssignmentAction.ASSIGN
    )

    reason: RoleAssignmentReason = (
        RoleAssignmentReason
        .CAPABILITY_MATCH
    )

    current_agent_id: str | None = None

    requested_by: str

    human_approval_required: bool = False

    created_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    metadata: dict[str, str] = Field(
        default_factory=dict
    )

    @field_validator(
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


class RoleCandidateEvaluation(BaseModel):
    agent_id: str
    agent_name: str

    eligible: bool

    matched_capabilities: set[str] = Field(
        default_factory=set
    )

    matched_tasks: set[str] = Field(
        default_factory=set
    )

    missing_capabilities: set[str] = Field(
        default_factory=set
    )

    missing_tasks: set[str] = Field(
        default_factory=set
    )

    skill_level: int

    capability_score: float = 0.0
    runtime_score: float = 0.0
    score: float = 0.0

    runtime_metrics_available: bool = False

    runtime_reasons: list[str] = Field(
        default_factory=list
    )

    rejection_reasons: list[str] = Field(
        default_factory=list
    )


class DynamicRoleAssignment(BaseModel):
    assignment_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    request_id: str

    team_id: str
    workspace_id: str

    role_name: str

    agent_id: str
    agent_name: str

    action: RoleAssignmentAction
    reason: RoleAssignmentReason

    status: RoleAssignmentStatus = (
        RoleAssignmentStatus.PROPOSED
    )

    replaced_agent_id: str | None = None

    matched_capabilities: set[str] = Field(
        default_factory=set
    )

    matched_tasks: set[str] = Field(
        default_factory=set
    )

    assignment_score: float = 0.0

    assigned_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    activated_at: datetime | None = None
    released_at: datetime | None = None

    metadata: dict[str, str] = Field(
        default_factory=dict
    )


class RoleAssignmentResult(BaseModel):
    request_id: str
    team_id: str

    assignments: list[
        DynamicRoleAssignment
    ] = Field(
        default_factory=list
    )

    candidates: list[
        RoleCandidateEvaluation
    ] = Field(
        default_factory=list
    )

    fulfilled: bool

    required_assignments: int
    completed_assignments: int

    reasons: list[str] = Field(
        default_factory=list
    )
