from __future__ import annotations

from collections import Counter

from .team_models import (
    AgentTeam,
    RoleCriticality,
    TeamBuildRequest,
    TeamRoleRequirement,
)
from .team_validation_models import (
    RoleCoverageResult,
    TeamValidationCode,
    TeamValidationIssue,
    TeamValidationReport,
    ValidationSeverity,
)


class TeamValidator:
    """
    Validates role coverage, member assignments,
    capabilities, tasks, skill levels, and reuse policy.
    """

    def validate(
        self,
        *,
        request: TeamBuildRequest,
        team: AgentTeam,
    ) -> TeamValidationReport:
        issues: list[
            TeamValidationIssue
        ] = []

        coverage_results: list[
            RoleCoverageResult
        ] = []

        requirements_by_role = {
            requirement.role_name:
                requirement
            for requirement
            in request.role_requirements
        }

        if not request.role_requirements:
            issues.append(
                TeamValidationIssue(
                    code=(
                        TeamValidationCode
                        .TEAM_HAS_NO_ROLES
                    ),
                    severity=(
                        ValidationSeverity.WARNING
                    ),
                    message=(
                        "team request contains no "
                        "role requirements"
                    ),
                )
            )

        if (
            request.role_requirements
            and not team.members
        ):
            issues.append(
                TeamValidationIssue(
                    code=(
                        TeamValidationCode
                        .TEAM_HAS_NO_MEMBERS
                    ),
                    severity=(
                        ValidationSeverity.ERROR
                    ),
                    message=(
                        "team contains no assigned "
                        "members"
                    ),
                )
            )

        for requirement in (
            request.role_requirements
        ):
            coverage = self._validate_role(
                requirement=requirement,
                team=team,
            )

            coverage_results.append(
                coverage
            )

            issues.extend(
                coverage.issues
            )

        known_roles = set(
            requirements_by_role
        )

        for member in team.members:
            if member.role_name not in known_roles:
                issues.append(
                    TeamValidationIssue(
                        code=(
                            TeamValidationCode
                            .UNKNOWN_ROLE_ASSIGNMENT
                        ),
                        severity=(
                            ValidationSeverity.ERROR
                        ),
                        message=(
                            "member assigned to an "
                            "unknown role"
                        ),
                        role_name=(
                            member.role_name
                        ),
                        agent_id=(
                            member.agent_id
                        ),
                    )
                )

        if not request.allow_agent_role_reuse:
            agent_counts = Counter(
                member.agent_id
                for member in team.members
            )

            for agent_id, count in (
                agent_counts.items()
            ):
                if count <= 1:
                    continue

                issues.append(
                    TeamValidationIssue(
                        code=(
                            TeamValidationCode
                            .AGENT_REUSED
                        ),
                        severity=(
                            ValidationSeverity.ERROR
                        ),
                        message=(
                            "agent assigned to "
                            "multiple roles while "
                            "role reuse is disabled"
                        ),
                        agent_id=agent_id,
                        metadata={
                            "assignment_count":
                                count,
                        },
                    )
                )

        valid = not any(
            issue.severity
            in {
                ValidationSeverity.ERROR,
                ValidationSeverity.CRITICAL,
            }
            for issue in issues
        )

        if (
            valid
            and request.role_requirements
        ):
            issues.append(
                TeamValidationIssue(
                    code=(
                        TeamValidationCode
                        .ROLE_COVERAGE_COMPLETE
                    ),
                    severity=(
                        ValidationSeverity.INFO
                    ),
                    message=(
                        "all required role coverage "
                        "rules are satisfied"
                    ),
                )
            )

        return TeamValidationReport(
            team_id=team.team_id,
            request_id=request.request_id,
            workspace_id=(
                request.workspace_id
            ),
            valid=valid,
            role_coverage=(
                coverage_results
            ),
            issues=issues,
        )

    def _validate_role(
        self,
        *,
        requirement: TeamRoleRequirement,
        team: AgentTeam,
    ) -> RoleCoverageResult:
        members = list(
            team.members_for_role(
                requirement.role_name
            )
        )

        issues: list[
            TeamValidationIssue
        ] = []

        assigned_count = len(
            members
        )

        if (
            requirement.criticality
            is RoleCriticality.REQUIRED
            and assigned_count == 0
        ):
            issues.append(
                TeamValidationIssue(
                    code=(
                        TeamValidationCode
                        .REQUIRED_ROLE_UNFILLED
                    ),
                    severity=(
                        ValidationSeverity.ERROR
                    ),
                    message=(
                        "required role has no "
                        "assigned member"
                    ),
                    role_name=(
                        requirement.role_name
                    ),
                )
            )

        if (
            assigned_count
            < requirement.minimum_members
            and requirement.criticality
            is RoleCriticality.REQUIRED
        ):
            issues.append(
                TeamValidationIssue(
                    code=(
                        TeamValidationCode
                        .MINIMUM_MEMBERS_NOT_MET
                    ),
                    severity=(
                        ValidationSeverity.ERROR
                    ),
                    message=(
                        "assigned member count is "
                        "below the required minimum"
                    ),
                    role_name=(
                        requirement.role_name
                    ),
                    metadata={
                        "minimum_members":
                            requirement
                            .minimum_members,

                        "assigned_members":
                            assigned_count,
                    },
                )
            )

        if (
            assigned_count
            > requirement.maximum_members
        ):
            issues.append(
                TeamValidationIssue(
                    code=(
                        TeamValidationCode
                        .MAXIMUM_MEMBERS_EXCEEDED
                    ),
                    severity=(
                        ValidationSeverity.ERROR
                    ),
                    message=(
                        "assigned member count "
                        "exceeds the allowed maximum"
                    ),
                    role_name=(
                        requirement.role_name
                    ),
                    metadata={
                        "maximum_members":
                            requirement
                            .maximum_members,

                        "assigned_members":
                            assigned_count,
                    },
                )
            )

        for member in members:
            missing_capabilities = (
                requirement
                .required_capabilities
                - member.matched_capabilities
            )

            if missing_capabilities:
                issues.append(
                    TeamValidationIssue(
                        code=(
                            TeamValidationCode
                            .CAPABILITY_MISMATCH
                        ),
                        severity=(
                            ValidationSeverity.ERROR
                        ),
                        message=(
                            "assigned member does not "
                            "cover all required "
                            "capabilities"
                        ),
                        role_name=(
                            requirement.role_name
                        ),
                        agent_id=member.agent_id,
                        metadata={
                            "missing_capabilities":
                                sorted(
                                    missing_capabilities
                                ),
                        },
                    )
                )

            missing_tasks = (
                requirement.supported_tasks
                - member.matched_tasks
            )

            if missing_tasks:
                issues.append(
                    TeamValidationIssue(
                        code=(
                            TeamValidationCode
                            .TASK_MISMATCH
                        ),
                        severity=(
                            ValidationSeverity.ERROR
                        ),
                        message=(
                            "assigned member does not "
                            "cover all required tasks"
                        ),
                        role_name=(
                            requirement.role_name
                        ),
                        agent_id=member.agent_id,
                        metadata={
                            "missing_tasks":
                                sorted(
                                    missing_tasks
                                ),
                        },
                    )
                )

            if (
                member.skill_level
                < requirement
                .minimum_skill_level
            ):
                issues.append(
                    TeamValidationIssue(
                        code=(
                            TeamValidationCode
                            .SKILL_LEVEL_TOO_LOW
                        ),
                        severity=(
                            ValidationSeverity.ERROR
                        ),
                        message=(
                            "assigned member skill "
                            "level is below the role "
                            "minimum"
                        ),
                        role_name=(
                            requirement.role_name
                        ),
                        agent_id=member.agent_id,
                        metadata={
                            "minimum_skill_level":
                                requirement
                                .minimum_skill_level,

                            "member_skill_level":
                                member.skill_level,
                        },
                    )
                )

        covered = not any(
            issue.severity
            in {
                ValidationSeverity.ERROR,
                ValidationSeverity.CRITICAL,
            }
            for issue in issues
        )

        return RoleCoverageResult(
            role_name=requirement.role_name,
            required_members=(
                requirement.minimum_members
            ),
            maximum_members=(
                requirement.maximum_members
            ),
            assigned_members=(
                assigned_count
            ),
            required_capabilities=(
                requirement
                .required_capabilities
            ),
            required_tasks=(
                requirement.supported_tasks
            ),
            assigned_agent_ids=[
                member.agent_id
                for member in members
            ],
            covered=covered,
            issues=issues,
        )
