from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class ValidationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class TeamValidationCode(str, Enum):
    ROLE_COVERAGE_COMPLETE = (
        "role_coverage_complete"
    )

    REQUIRED_ROLE_UNFILLED = (
        "required_role_unfilled"
    )

    MINIMUM_MEMBERS_NOT_MET = (
        "minimum_members_not_met"
    )

    MAXIMUM_MEMBERS_EXCEEDED = (
        "maximum_members_exceeded"
    )

    AGENT_REUSED = (
        "agent_reused"
    )

    CAPABILITY_MISMATCH = (
        "capability_mismatch"
    )

    TASK_MISMATCH = (
        "task_mismatch"
    )

    SKILL_LEVEL_TOO_LOW = (
        "skill_level_too_low"
    )

    UNKNOWN_ROLE_ASSIGNMENT = (
        "unknown_role_assignment"
    )

    TEAM_HAS_NO_ROLES = (
        "team_has_no_roles"
    )

    TEAM_HAS_NO_MEMBERS = (
        "team_has_no_members"
    )


class TeamValidationIssue(BaseModel):
    code: TeamValidationCode
    severity: ValidationSeverity

    message: str

    role_name: str | None = None
    agent_id: str | None = None

    metadata: dict[str, object] = Field(
        default_factory=dict
    )


class RoleCoverageResult(BaseModel):
    role_name: str

    required_members: int
    maximum_members: int
    assigned_members: int

    required_capabilities: set[str] = Field(
        default_factory=set
    )

    required_tasks: set[str] = Field(
        default_factory=set
    )

    assigned_agent_ids: list[str] = Field(
        default_factory=list
    )

    covered: bool

    issues: list[
        TeamValidationIssue
    ] = Field(
        default_factory=list
    )


class TeamValidationReport(BaseModel):
    team_id: str
    request_id: str
    workspace_id: str

    valid: bool

    role_coverage: list[
        RoleCoverageResult
    ] = Field(
        default_factory=list
    )

    issues: list[
        TeamValidationIssue
    ] = Field(
        default_factory=list
    )

    validated_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    @property
    def error_count(self) -> int:
        return sum(
            issue.severity
            in {
                ValidationSeverity.ERROR,
                ValidationSeverity.CRITICAL,
            }
            for issue in self.issues
        )

    @property
    def warning_count(self) -> int:
        return sum(
            issue.severity
            is ValidationSeverity.WARNING
            for issue in self.issues
        )
