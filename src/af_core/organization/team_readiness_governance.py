from __future__ import annotations

from datetime import datetime, timezone

from .readiness_models import (
    TeamReadinessDecision,
    TeamReadinessPolicy,
    TeamReadinessResult,
)
from .team_models import (
    AgentTeam,
    TeamStatus,
)
from .team_validation_models import (
    TeamValidationReport,
)


class TeamReadinessGovernance:
    """
    Determines whether a validated Agent team may become active.
    """

    def __init__(
        self,
        policy: TeamReadinessPolicy | None = None,
    ) -> None:
        self._policy = (
            policy
            or TeamReadinessPolicy()
        )

    def evaluate(
        self,
        *,
        team: AgentTeam,
        validation: TeamValidationReport,
        environment: str = "runtime",
        human_approved: bool = False,
        approver_id: str | None = None,
    ) -> TeamReadinessResult:
        reasons: list[str] = []

        normalized_environment = (
            environment.strip().lower()
        )

        if not normalized_environment:
            normalized_environment = (
                "runtime"
            )

        if (
            self._policy.require_valid_team
            and not validation.valid
        ):
            return TeamReadinessResult(
                team_id=team.team_id,
                decision=(
                    TeamReadinessDecision
                    .BLOCKED
                ),
                approved=False,
                reasons=[
                    "team validation failed",
                ],
            )

        if (
            team.member_count
            < self._policy
            .minimum_total_members
        ):
            return TeamReadinessResult(
                team_id=team.team_id,
                decision=(
                    TeamReadinessDecision
                    .BLOCKED
                ),
                approved=False,
                reasons=[
                    (
                        "team member count is below "
                        "the governance minimum"
                    ),
                ],
            )

        team_capabilities = set()

        for member in team.members:
            team_capabilities.update(
                member.matched_capabilities
            )

        blocked = (
            team_capabilities
            .intersection(
                self._policy
                .blocked_capabilities
            )
        )

        if blocked:
            return TeamReadinessResult(
                team_id=team.team_id,
                decision=(
                    TeamReadinessDecision
                    .REJECTED
                ),
                approved=False,
                reasons=[
                    (
                        "team contains blocked "
                        "capabilities: "
                        + ", ".join(
                            sorted(blocked)
                        )
                    )
                ],
            )

        approval_required = (
            self._policy
            .require_human_approval
            or normalized_environment
            in self._policy
            .approval_required_environments
        )

        if (
            approval_required
            and not human_approved
        ):
            return TeamReadinessResult(
                team_id=team.team_id,
                decision=(
                    TeamReadinessDecision
                    .APPROVAL_REQUIRED
                ),
                approved=False,
                reasons=[
                    (
                        "human approval is required "
                        f"for {normalized_environment}"
                    )
                ],
                required_approver=(
                    "authorized-human"
                ),
            )

        if (
            approval_required
            and human_approved
            and not approver_id
        ):
            return TeamReadinessResult(
                team_id=team.team_id,
                decision=(
                    TeamReadinessDecision
                    .BLOCKED
                ),
                approved=False,
                reasons=[
                    (
                        "approved team activation "
                        "requires approver_id"
                    )
                ],
            )

        if validation.warning_count:
            reasons.append(
                (
                    f"team has "
                    f"{validation.warning_count} "
                    "validation warning(s)"
                )
            )

            if not (
                self._policy
                .allow_warning_activation
            ):
                return TeamReadinessResult(
                    team_id=team.team_id,
                    decision=(
                        TeamReadinessDecision
                        .BLOCKED
                    ),
                    approved=False,
                    reasons=reasons,
                )

        reasons.append(
            "team satisfies readiness governance"
        )

        if approver_id:
            reasons.append(
                f"approved by {approver_id}"
            )

        return TeamReadinessResult(
            team_id=team.team_id,
            decision=(
                TeamReadinessDecision.READY
            ),
            approved=True,
            reasons=reasons,
        )

    def activate(
        self,
        *,
        team: AgentTeam,
        readiness: TeamReadinessResult,
    ) -> AgentTeam:
        if (
            readiness.decision
            is not TeamReadinessDecision.READY
            or not readiness.approved
        ):
            raise ValueError(
                "team is not approved for activation"
            )

        return team.model_copy(
            update={
                "status":
                    TeamStatus.ACTIVE,

                "activated_at":
                    datetime.now(
                        timezone.utc
                    ),
            }
        )
