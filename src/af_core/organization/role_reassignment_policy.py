from __future__ import annotations

from datetime import datetime, timezone

from .agent_runtime_metrics import (
    AgentAvailabilityStatus,
    AgentRuntimeMetrics,
)
from .dynamic_role_models import (
    DynamicRoleAssignment,
)
from .role_failover_models import (
    ReassignmentPolicy,
    RoleHealthAssessment,
    RoleHealthDecision,
    RoleHealthTrigger,
)


class RoleReassignmentPolicyEngine:
    """
    Evaluates the runtime health of an active role assignment.
    """

    def __init__(
        self,
        policy: ReassignmentPolicy | None = None,
    ) -> None:
        self._policy = (
            policy
            or ReassignmentPolicy()
        )

    def evaluate(
        self,
        *,
        assignment: DynamicRoleAssignment,
        metrics: AgentRuntimeMetrics | None,
        evaluated_at: datetime | None = None,
    ) -> RoleHealthAssessment:
        now = (
            evaluated_at
            or datetime.now(timezone.utc)
        )

        if metrics is None:
            if self._policy.require_runtime_metrics:
                return RoleHealthAssessment(
                    assignment_id=(
                        assignment.assignment_id
                    ),
                    team_id=assignment.team_id,
                    role_name=assignment.role_name,
                    agent_id=assignment.agent_id,
                    decision=(
                        RoleHealthDecision.BLOCKED
                    ),
                    triggers=[
                        RoleHealthTrigger
                        .METRICS_UNAVAILABLE
                    ],
                    reasons=[
                        (
                            "runtime metrics are "
                            "required but unavailable"
                        )
                    ],
                    metrics_available=False,
                    evaluated_at=now,
                )

            return RoleHealthAssessment(
                assignment_id=(
                    assignment.assignment_id
                ),
                team_id=assignment.team_id,
                role_name=assignment.role_name,
                agent_id=assignment.agent_id,
                decision=RoleHealthDecision.KEEP,
                triggers=[
                    RoleHealthTrigger.HEALTHY
                ],
                reasons=[
                    (
                        "runtime metrics are optional "
                        "and no failure condition "
                        "was observed"
                    )
                ],
                metrics_available=False,
                evaluated_at=now,
            )

        triggers: list[
            RoleHealthTrigger
        ] = []

        reasons: list[str] = []

        immediate_failover = False
        reassignment_required = False

        if (
            metrics.availability
            is AgentAvailabilityStatus.OFFLINE
        ):
            triggers.append(
                RoleHealthTrigger.AGENT_OFFLINE
            )

            reasons.append(
                "assigned agent is offline"
            )

            immediate_failover = (
                self._policy
                .failover_on_offline
            )

        if (
            metrics.availability
            is AgentAvailabilityStatus.SUSPENDED
        ):
            triggers.append(
                RoleHealthTrigger
                .AGENT_SUSPENDED
            )

            reasons.append(
                "assigned agent is suspended"
            )

            immediate_failover = (
                immediate_failover
                or self._policy
                .failover_on_suspended
            )

        heartbeat_age = (
            now
            - metrics.last_heartbeat_at
        ).total_seconds()

        if (
            heartbeat_age
            > self._policy
            .maximum_heartbeat_age_seconds
        ):
            triggers.append(
                RoleHealthTrigger
                .HEARTBEAT_STALE
            )

            reasons.append(
                (
                    "agent heartbeat age exceeded "
                    "the permitted threshold"
                )
            )

            immediate_failover = True

        if (
            metrics.workload_ratio
            >= self._policy
            .maximum_workload_ratio
        ):
            triggers.append(
                RoleHealthTrigger
                .WORKLOAD_EXCEEDED
            )

            reasons.append(
                (
                    "agent workload exceeded "
                    "the reassignment threshold"
                )
            )

            reassignment_required = (
                self._policy
                .reassign_on_overload
            )

        if (
            metrics.consecutive_failures
            >= self._policy
            .maximum_consecutive_failures
            and self._policy
            .maximum_consecutive_failures
            > 0
        ):
            triggers.append(
                RoleHealthTrigger
                .FAILURE_THRESHOLD_EXCEEDED
            )

            reasons.append(
                (
                    "agent consecutive failures "
                    "reached the policy threshold"
                )
            )

            reassignment_required = True

        performance_degraded = False

        if (
            metrics.success_rate
            < self._policy
            .minimum_success_rate
        ):
            triggers.append(
                RoleHealthTrigger
                .SUCCESS_RATE_DEGRADED
            )

            reasons.append(
                "agent success rate is below policy"
            )

            performance_degraded = True

        if (
            metrics.quality_score
            < self._policy
            .minimum_quality_score
        ):
            triggers.append(
                RoleHealthTrigger
                .QUALITY_DEGRADED
            )

            reasons.append(
                "agent quality score is below policy"
            )

            performance_degraded = True

        if (
            metrics.reliability_score
            < self._policy
            .minimum_reliability_score
        ):
            triggers.append(
                RoleHealthTrigger
                .RELIABILITY_DEGRADED
            )

            reasons.append(
                (
                    "agent reliability score "
                    "is below policy"
                )
            )

            performance_degraded = True

        if (
            performance_degraded
            and self._policy
            .reassign_on_performance_degradation
        ):
            reassignment_required = True

        if immediate_failover:
            decision = (
                RoleHealthDecision.FAILOVER
            )

        elif reassignment_required:
            decision = (
                RoleHealthDecision.REASSIGN
            )

        else:
            decision = RoleHealthDecision.KEEP

            triggers.append(
                RoleHealthTrigger.HEALTHY
            )

            reasons.append(
                "assignment satisfies runtime policy"
            )

        return RoleHealthAssessment(
            assignment_id=(
                assignment.assignment_id
            ),
            team_id=assignment.team_id,
            role_name=assignment.role_name,
            agent_id=assignment.agent_id,
            decision=decision,
            triggers=triggers,
            reasons=reasons,
            metrics_available=True,
            evaluated_at=now,
        )

    @property
    def policy(self) -> ReassignmentPolicy:
        return self._policy
