from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class TeamEventType(str, Enum):
    BUILD_REQUESTED = (
        "team.build.requested"
    )

    CREATED = (
        "team.created"
    )

    VALIDATION_COMPLETED = (
        "team.validation.completed"
    )

    APPROVAL_REQUIRED = (
        "team.approval.required"
    )

    READY = (
        "team.ready"
    )

    ACTIVATED = (
        "team.activated"
    )

    BLOCKED = (
        "team.blocked"
    )

    REJECTED = (
        "team.rejected"
    )


class TeamEventPayload(BaseModel):
    team_id: str
    request_id: str
    team_name: str
    workspace_id: str

    event_type: TeamEventType

    status: str

    member_count: int = 0

    member_agent_ids: list[str] = Field(
        default_factory=list
    )

    unfilled_roles: list[str] = Field(
        default_factory=list
    )

    validation_valid: bool | None = None

    readiness_decision: str | None = None

    reasons: list[str] = Field(
        default_factory=list
    )

    metadata: dict[str, object] = Field(
        default_factory=dict
    )
