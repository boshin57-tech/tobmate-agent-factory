from __future__ import annotations

from .agent_runtime_metrics import (
    AgentAvailabilityStatus,
    AgentRuntimeMetrics,
    RuntimeScoreBreakdown,
    RuntimeScoringWeights,
)


class RuntimeAgentScorer:
    """
    Calculates operational suitability for dynamic role assignment.

    Hard rejection:
    - Offline
    - Suspended
    - No remaining assignment capacity
    - Workload at 100 percent

    Degraded and busy Agents remain eligible but receive penalties.
    """

    DEFAULT_RESPONSE_TARGET_MS = 1000.0

    def __init__(
        self,
        weights: RuntimeScoringWeights | None = None,
        *,
        response_target_ms: float = (
            DEFAULT_RESPONSE_TARGET_MS
        ),
    ) -> None:
        if response_target_ms <= 0:
            raise ValueError(
                "response_target_ms must be positive"
            )

        self._weights = (
            weights
            or RuntimeScoringWeights()
        )

        self._response_target_ms = (
            response_target_ms
        )

    def score(
        self,
        metrics: AgentRuntimeMetrics,
    ) -> RuntimeScoreBreakdown:
        reasons: list[str] = []

        if (
            metrics.availability
            is AgentAvailabilityStatus.OFFLINE
        ):
            return RuntimeScoreBreakdown(
                agent_id=metrics.agent_id,
                eligible=False,
                reasons=[
                    "agent runtime status is offline"
                ],
            )

        if (
            metrics.availability
            is AgentAvailabilityStatus.SUSPENDED
        ):
            return RuntimeScoreBreakdown(
                agent_id=metrics.agent_id,
                eligible=False,
                reasons=[
                    "agent runtime status is suspended"
                ],
            )

        if not metrics.has_capacity:
            return RuntimeScoreBreakdown(
                agent_id=metrics.agent_id,
                eligible=False,
                reasons=[
                    "agent has no remaining runtime capacity"
                ],
            )

        availability_score = (
            self._weights.availability
        )

        capacity_ratio = (
            1.0
            - (
                metrics.current_assignments
                / metrics.maximum_assignments
            )
        )

        capacity_score = (
            capacity_ratio
            * self._weights.capacity
        )

        workload_score = (
            (1.0 - metrics.workload_ratio)
            * self._weights.low_workload
        )

        success_score = (
            metrics.success_rate
            * self._weights.success_rate
        )

        quality_score = (
            metrics.quality_score
            / 100.0
            * self._weights.quality
        )

        reliability_score = (
            metrics.reliability_score
            / 100.0
            * self._weights.reliability
        )

        if metrics.average_response_ms == 0:
            response_ratio = 1.0
        else:
            response_ratio = min(
                1.0,
                self._response_target_ms
                / metrics.average_response_ms,
            )

        response_score = (
            response_ratio
            * self._weights.response_speed
        )

        penalty_score = 0.0

        if (
            metrics.availability
            is AgentAvailabilityStatus.BUSY
        ):
            penalty_score += (
                self._weights.busy_penalty
            )
            reasons.append(
                "busy availability penalty"
            )

        if (
            metrics.availability
            is AgentAvailabilityStatus.DEGRADED
        ):
            penalty_score += (
                self._weights.degraded_penalty
            )
            reasons.append(
                "degraded availability penalty"
            )

        if metrics.consecutive_failures:
            penalty_score += (
                metrics.consecutive_failures
                * self._weights
                .consecutive_failure_penalty
            )
            reasons.append(
                "consecutive failure penalty"
            )

        total_score = (
            availability_score
            + capacity_score
            + workload_score
            + success_score
            + quality_score
            + reliability_score
            + response_score
            - penalty_score
        )

        reasons.extend(
            [
                (
                    "runtime capacity "
                    f"{round(capacity_ratio * 100, 2)}%"
                ),
                (
                    "workload "
                    f"{round(metrics.workload_ratio * 100, 2)}%"
                ),
                (
                    "success rate "
                    f"{round(metrics.success_rate * 100, 2)}%"
                ),
                (
                    "quality score "
                    f"{metrics.quality_score}"
                ),
                (
                    "reliability score "
                    f"{metrics.reliability_score}"
                ),
            ]
        )

        return RuntimeScoreBreakdown(
            agent_id=metrics.agent_id,
            eligible=True,
            availability_score=round(
                availability_score,
                4,
            ),
            capacity_score=round(
                capacity_score,
                4,
            ),
            workload_score=round(
                workload_score,
                4,
            ),
            success_score=round(
                success_score,
                4,
            ),
            quality_score=round(
                quality_score,
                4,
            ),
            reliability_score=round(
                reliability_score,
                4,
            ),
            response_score=round(
                response_score,
                4,
            ),
            penalty_score=round(
                penalty_score,
                4,
            ),
            total_score=round(
                total_score,
                4,
            ),
            reasons=reasons,
        )
