from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class TeamStatus(str, Enum):
    FORMING = "forming"
    READY = "ready"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class RoleCriticality(str, Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"


class TeamRoleRequirement(BaseModel):
    """
    Describes one role that must or may be filled in an Agent team.
    """

    role_name: str

    required_capabilities: set[str] = Field(
        default_factory=set
    )

    supported_tasks: set[str] = Field(
        default_factory=set
    )

    minimum_skill_level: int = 1

    minimum_members: int = 1
    maximum_members: int = 1

    criticality: RoleCriticality = (
        RoleCriticality.REQUIRED
    )

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
                "minimum_skill_level must be at least 1"
            )

        return value

    @field_validator(
        "minimum_members",
        "maximum_members",
    )
    @classmethod
    def validate_member_count(
        cls,
        value: int,
    ) -> int:
        if value < 1:
            raise ValueError(
                "member count must be at least 1"
            )

        return value

    def model_post_init(
        self,
        __context: object,
    ) -> None:
        if (
            self.maximum_members
            < self.minimum_members
        ):
            raise ValueError(
                "maximum_members must not be less than "
                "minimum_members"
            )


class TeamBuildRequest(BaseModel):
    """
    Requested Agent team composition for one project or workflow.
    """

    request_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    team_name: str

    workspace_id: str
    objective: str

    role_requirements: list[
        TeamRoleRequirement
    ] = Field(
        default_factory=list
    )

    allow_agent_role_reuse: bool = False

    requested_by: str

    created_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    metadata: dict[str, str] = Field(
        default_factory=dict
    )

    @field_validator(
        "team_name",
        "workspace_id",
        "objective",
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


class TeamMember(BaseModel):
    """
    One Agent assigned to one role in a team.
    """

    member_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    agent_id: str
    agent_name: str

    role_name: str

    matched_capabilities: set[str] = Field(
        default_factory=set
    )

    matched_tasks: set[str] = Field(
        default_factory=set
    )

    skill_level: int

    assignment_score: float = 0.0

    assigned_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    metadata: dict[str, str] = Field(
        default_factory=dict
    )


class UnfilledRole(BaseModel):
    role_name: str

    required_members: int
    assigned_members: int

    missing_capabilities: set[str] = Field(
        default_factory=set
    )

    reason: str


class AgentTeam(BaseModel):
    """
    Team produced by the Team Builder Engine.
    """

    team_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    request_id: str

    team_name: str
    workspace_id: str
    objective: str

    status: TeamStatus

    members: list[TeamMember] = Field(
        default_factory=list
    )

    unfilled_roles: list[UnfilledRole] = Field(
        default_factory=list
    )

    selection_metadata: dict[
        str,
        dict[str, object],
    ] = Field(
        default_factory=dict
    )

    created_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    activated_at: datetime | None = None

    metadata: dict[str, str] = Field(
        default_factory=dict
    )

    @property
    def member_count(self) -> int:
        return len(self.members)

    @property
    def is_ready(self) -> bool:
        return (
            self.status is TeamStatus.READY
            and not self.unfilled_roles
        )

    def members_for_role(
        self,
        role_name: str,
    ) -> tuple[TeamMember, ...]:
        return tuple(
            member
            for member in self.members
            if member.role_name == role_name
        )
