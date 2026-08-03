from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class TeamReadinessDecision(str, Enum):
    READY = "ready"

    APPROVAL_REQUIRED = (
        "approval_required"
    )

    BLOCKED = "blocked"

    REJECTED = "rejected"


class TeamReadinessPolicy(BaseModel):
    """
    Governance rules applied before a team can become active.
    """

    require_valid_team: bool = True

    require_human_approval: bool = False

    approval_required_environments: set[
        str
    ] = Field(
        default_factory=lambda: {
            "production",
            "mainnet",
        }
    )

    blocked_capabilities: set[str] = Field(
        default_factory=set
    )

    minimum_total_members: int = 1

    allow_warning_activation: bool = True


class TeamReadinessResult(BaseModel):
    team_id: str

    decision: TeamReadinessDecision

    approved: bool

    reasons: list[str] = Field(
        default_factory=list
    )

    required_approver: str | None = None

    evaluated_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )
