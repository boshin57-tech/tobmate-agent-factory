from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .dynamic_role_models import (
    DynamicRoleAssignment,
)
from .role_failover_models import (
    RoleFailoverResult,
)


class RoleEventType(str, Enum):
    ASSIGNMENT_PROPOSED = (
        "role.assignment.proposed"
    )

    ASSIGNMENT_APPROVED = (
        "role.assignment.approved"
    )

    ASSIGNMENT_ACTIVATED = (
        "role.assignment.activated"
    )

    ASSIGNMENT_RELEASED = (
        "role.assignment.released"
    )

    REASSIGNMENT_REQUESTED = (
        "role.reassignment.requested"
    )

    FAILOVER_STARTED = (
        "role.failover.started"
    )

    FAILOVER_COMPLETED = (
        "role.failover.completed"
    )

    FAILOVER_BLOCKED = (
        "role.failover.blocked"
    )


class RoleAssignmentEventPayload(BaseModel):
    event_type: RoleEventType

    assignment_id: str
    request_id: str

    team_id: str
    workspace_id: str

    role_name: str

    agent_id: str
    agent_name: str

    action: str
    reason: str
    status: str

    replaced_agent_id: str | None = None

    assignment_score: float = 0.0

    matched_capabilities: list[str] = Field(
        default_factory=list
    )

    matched_tasks: list[str] = Field(
        default_factory=list
    )

    metadata: dict[str, object] = Field(
        default_factory=dict
    )

    @classmethod
    def from_assignment(
        cls,
        *,
        event_type: RoleEventType,
        assignment: DynamicRoleAssignment,
    ) -> "RoleAssignmentEventPayload":
        return cls(
            event_type=event_type,
            assignment_id=(
                assignment.assignment_id
            ),
            request_id=assignment.request_id,
            team_id=assignment.team_id,
            workspace_id=(
                assignment.workspace_id
            ),
            role_name=assignment.role_name,
            agent_id=assignment.agent_id,
            agent_name=assignment.agent_name,
            action=assignment.action.value,
            reason=assignment.reason.value,
            status=assignment.status.value,
            replaced_agent_id=(
                assignment.replaced_agent_id
            ),
            assignment_score=(
                assignment.assignment_score
            ),
            matched_capabilities=sorted(
                assignment.matched_capabilities
            ),
            matched_tasks=sorted(
                assignment.matched_tasks
            ),
            metadata=dict(
                assignment.metadata
            ),
        )


class RoleFailoverEventPayload(BaseModel):
    event_type: RoleEventType

    failover_request_id: str

    team_id: str
    role_name: str

    previous_assignment_id: str | None = None
    previous_agent_id: str | None = None

    replacement_assignment_id: str | None = None
    replacement_agent_id: str | None = None

    decision: str

    completed: bool

    previous_assignment_released: bool

    reasons: list[str] = Field(
        default_factory=list
    )

    triggers: list[str] = Field(
        default_factory=list
    )

    @classmethod
    def from_result(
        cls,
        *,
        event_type: RoleEventType,
        result: RoleFailoverResult,
    ) -> "RoleFailoverEventPayload":
        previous = (
            result.previous_assignment
        )

        replacement = (
            result.replacement_assignment
        )

        return cls(
            event_type=event_type,
            failover_request_id=(
                result.failover_request_id
            ),
            team_id=(
                result.assessment.team_id
            ),
            role_name=(
                result.assessment.role_name
            ),
            previous_assignment_id=(
                previous.assignment_id
                if previous is not None
                else None
            ),
            previous_agent_id=(
                previous.agent_id
                if previous is not None
                else None
            ),
            replacement_assignment_id=(
                replacement.assignment_id
                if replacement is not None
                else None
            ),
            replacement_agent_id=(
                replacement.agent_id
                if replacement is not None
                else None
            ),
            decision=(
                result.assessment
                .decision.value
            ),
            completed=result.completed,
            previous_assignment_released=(
                result
                .previous_assignment_released
            ),
            reasons=list(result.reasons),
            triggers=[
                trigger.value
                for trigger
                in result.assessment.triggers
            ],
        )
