from __future__ import annotations

from .dynamic_role_assignment import (
    DynamicRoleAssignmentEngine,
)
from .dynamic_role_models import (
    DynamicRoleAssignment,
    RoleAssignmentAction,
    RoleAssignmentReason,
    RoleAssignmentRequest,
    RoleAssignmentStatus,
)
from .role_failover_models import (
    RoleFailoverRequest,
    RoleFailoverResult,
    RoleHealthDecision,
)
from .role_reassignment_policy import (
    RoleReassignmentPolicyEngine,
)


class AutomatedRoleFailoverEngine:
    """
    Evaluates active role health and replaces unhealthy Agents.

    Safety behavior:
    - The existing assignment remains active when no replacement exists.
    - The replacement is activated before the previous assignment is
      released.
    - The current Agent is excluded from replacement selection.
    """

    def __init__(
        self,
        *,
        assignment_engine: DynamicRoleAssignmentEngine,
        policy_engine: (
            RoleReassignmentPolicyEngine
            | None
        ) = None,
    ) -> None:
        self._assignment_engine = (
            assignment_engine
        )

        self._policy_engine = (
            policy_engine
            or RoleReassignmentPolicyEngine()
        )

    def evaluate_assignment(
        self,
        assignment: DynamicRoleAssignment,
    ):
        metrics = (
            self._assignment_engine
            .runtime_metrics(
                assignment.agent_id
            )
        )

        return self._policy_engine.evaluate(
            assignment=assignment,
            metrics=metrics,
        )

    def execute(
        self,
        request: RoleFailoverRequest,
    ) -> RoleFailoverResult:
        previous = self._find_active_assignment(
            assignment_id=(
                request.assignment_id
            ),
            team_id=request.team_id,
            role_name=(
                request.requirement
                .role_name
            ),
        )

        if previous is None:
            return RoleFailoverResult(
                failover_request_id=(
                    request.failover_request_id
                ),
                assessment=self._missing_assessment(
                    request
                ),
                completed=False,
                reasons=[
                    (
                        "active role assignment "
                        "was not found"
                    )
                ],
            )

        assessment = self.evaluate_assignment(
            previous
        )

        if (
            assessment.decision
            is RoleHealthDecision.KEEP
        ):
            return RoleFailoverResult(
                failover_request_id=(
                    request.failover_request_id
                ),
                assessment=assessment,
                previous_assignment=previous,
                completed=False,
                reasons=[
                    (
                        "current role assignment "
                        "remains healthy"
                    )
                ],
            )

        if (
            assessment.decision
            is RoleHealthDecision.BLOCKED
        ):
            return RoleFailoverResult(
                failover_request_id=(
                    request.failover_request_id
                ),
                assessment=assessment,
                previous_assignment=previous,
                completed=False,
                reasons=list(
                    assessment.reasons
                ),
            )

        action = (
            RoleAssignmentAction.FAILOVER
            if assessment.decision
            is RoleHealthDecision.FAILOVER
            else RoleAssignmentAction.REASSIGN
        )

        reason = self._assignment_reason(
            assessment.decision
        )

        selection = (
            self._assignment_engine.assign(
                RoleAssignmentRequest(
                    team_id=request.team_id,
                    workspace_id=(
                        request.workspace_id
                    ),
                    requirement=(
                        request.requirement
                    ),
                    action=action,
                    reason=reason,
                    current_agent_id=(
                        previous.agent_id
                    ),
                    requested_by=(
                        request.requested_by
                    ),
                    metadata={
                        **request.metadata,
                        "failover_request_id":
                            request
                            .failover_request_id,

                        "previous_assignment_id":
                            previous
                            .assignment_id,
                    },
                )
            )
        )

        if (
            not selection.fulfilled
            or not selection.assignments
        ):
            return RoleFailoverResult(
                failover_request_id=(
                    request.failover_request_id
                ),
                assessment=assessment,
                previous_assignment=previous,
                selection_result=selection,
                completed=False,
                reasons=[
                    (
                        "no eligible replacement "
                        "agent was available"
                    )
                ],
            )

        replacement = (
            selection.assignments[0]
        )

        policy = self._policy_engine.policy

        if (
            policy
            .activate_replacement_automatically
        ):
            replacement = (
                self._assignment_engine
                .activate(
                    replacement.assignment_id
                )
            )

        previous_released = False

        if (
            policy
            .release_previous_after_replacement
            and replacement.status
            is RoleAssignmentStatus.ACTIVE
        ):
            self._assignment_engine.release(
                previous.assignment_id
            )

            previous_released = True

        return RoleFailoverResult(
            failover_request_id=(
                request.failover_request_id
            ),
            assessment=assessment,
            previous_assignment=previous,
            replacement_assignment=(
                replacement
            ),
            selection_result=selection,
            completed=(
                replacement.status
                is RoleAssignmentStatus.ACTIVE
            ),
            previous_assignment_released=(
                previous_released
            ),
            reasons=[
                (
                    "replacement agent selected "
                    "and role failover completed"
                )
            ],
        )

    def scan_team(
        self,
        *,
        team_id: str,
        workspace_id: str,
        requirements_by_role: dict[
            str,
            object,
        ],
        requested_by: str,
    ) -> tuple[
        RoleFailoverResult,
        ...
    ]:
        results: list[
            RoleFailoverResult
        ] = []

        assignments = (
            self._assignment_engine
            .assignments_for_team(
                team_id
            )
        )

        for assignment in assignments:
            requirement = (
                requirements_by_role.get(
                    assignment.role_name
                )
            )

            if requirement is None:
                continue

            assessment = (
                self.evaluate_assignment(
                    assignment
                )
            )

            if not assessment.action_required:
                continue

            results.append(
                self.execute(
                    RoleFailoverRequest(
                        assignment_id=(
                            assignment
                            .assignment_id
                        ),
                        team_id=team_id,
                        workspace_id=(
                            workspace_id
                        ),
                        requirement=requirement,
                        requested_by=(
                            requested_by
                        ),
                    )
                )
            )

        return tuple(results)

    def _find_active_assignment(
        self,
        *,
        assignment_id: str,
        team_id: str,
        role_name: str,
    ) -> DynamicRoleAssignment | None:
        assignments = (
            self._assignment_engine
            .assignments_for_role(
                team_id=team_id,
                role_name=role_name,
            )
        )

        for assignment in assignments:
            if (
                assignment.assignment_id
                == assignment_id
            ):
                return assignment

        return None

    def _missing_assessment(
        self,
        request: RoleFailoverRequest,
    ):
        from .role_failover_models import (
            RoleHealthAssessment,
            RoleHealthTrigger,
        )

        return RoleHealthAssessment(
            assignment_id=(
                request.assignment_id
            ),
            team_id=request.team_id,
            role_name=(
                request.requirement.role_name
            ),
            agent_id="unknown",
            decision=RoleHealthDecision.BLOCKED,
            triggers=[
                RoleHealthTrigger
                .METRICS_UNAVAILABLE
            ],
            reasons=[
                "active assignment was not found"
            ],
            metrics_available=False,
        )

    @staticmethod
    def _assignment_reason(
        decision: RoleHealthDecision,
    ) -> RoleAssignmentReason:
        if (
            decision
            is RoleHealthDecision.FAILOVER
        ):
            return (
                RoleAssignmentReason
                .FAILOVER_REQUIRED
            )

        return (
            RoleAssignmentReason
            .PERFORMANCE_DEGRADED
        )
