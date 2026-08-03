from __future__ import annotations

from collections.abc import Callable, Iterable

from .task_coordination_models import (
    CoordinatedTask,
)
from .task_workload_models import (
    TaskAgentAvailability,
    TaskAgentRuntimeProfile,
    TaskAgentScore,
    TaskAgentSelectionResult,
)


class TaskWorkloadBalancingEngine:
    """
    Selects the most suitable available Agent for a coordinated task.
    """

    def __init__(
        self,
        agent_provider: Callable[
            [],
            Iterable[TaskAgentRuntimeProfile],
        ],
        *,
        minimum_success_rate: float = 0.50,
        minimum_quality_score: float = 50.0,
        minimum_reliability_score: float = 50.0,
        maximum_workload_ratio: float = 0.90,
    ) -> None:
        self._agent_provider = (
            agent_provider
        )

        self._minimum_success_rate = (
            minimum_success_rate
        )

        self._minimum_quality_score = (
            minimum_quality_score
        )

        self._minimum_reliability_score = (
            minimum_reliability_score
        )

        self._maximum_workload_ratio = (
            maximum_workload_ratio
        )

    def select_agent(
        self,
        *,
        task: CoordinatedTask,
        excluded_agent_ids: (
            set[str] | None
        ) = None,
    ) -> TaskAgentSelectionResult:
        excluded = (
            excluded_agent_ids
            or set()
        )

        scores = [
            self.score_agent(
                task=task,
                agent=agent,
                excluded=(
                    agent.agent_id
                    in excluded
                ),
            )
            for agent in (
                self._agent_provider()
            )
        ]

        scores.sort(
            key=lambda score: (
                score.eligible,
                score.total_score,
                score.agent_id,
            ),
            reverse=True,
        )

        eligible = [
            score
            for score in scores
            if score.eligible
        ]

        selected = (
            eligible[0]
            if eligible
            else None
        )

        reasons: list[str] = []

        if selected is None:
            reasons.append(
                "no eligible Agent is available"
            )
        else:
            reasons.append(
                (
                    "selected highest-ranked "
                    "eligible Agent"
                )
            )

        return TaskAgentSelectionResult(
            task_id=task.task_id,
            selected_agent_id=(
                selected.agent_id
                if selected is not None
                else None
            ),
            ranked_candidates=scores,
            eligible_agent_ids=[
                score.agent_id
                for score in eligible
            ],
            excluded_agent_ids=[
                score.agent_id
                for score in scores
                if not score.eligible
            ],
            fulfilled=(
                selected is not None
            ),
            reasons=reasons,
        )

    def score_agent(
        self,
        *,
        task: CoordinatedTask,
        agent: TaskAgentRuntimeProfile,
        excluded: bool = False,
    ) -> TaskAgentScore:
        matched_capabilities = (
            task.required_capabilities
            & agent.capabilities
        )

        missing_capabilities = (
            task.required_capabilities
            - agent.capabilities
        )

        matched_tasks = (
            task.required_tasks
            & agent.supported_tasks
        )

        missing_tasks = (
            task.required_tasks
            - agent.supported_tasks
        )

        capability_score = (
            100.0
            if not task.required_capabilities
            else (
                len(matched_capabilities)
                / len(
                    task.required_capabilities
                )
                * 100.0
            )
        )

        supported_task_score = (
            100.0
            if not task.required_tasks
            else (
                len(matched_tasks)
                / len(task.required_tasks)
                * 100.0
            )
        )

        capacity_score = min(
            100.0,
            (
                agent.remaining_capacity
                / agent.maximum_task_count
                * 100.0
            ),
        )

        workload_score = max(
            0.0,
            (
                1.0
                - agent.workload_ratio
            )
            * 100.0,
        )

        performance_score = (
            agent.success_rate
            * 100.0
        )

        reliability_score = (
            agent.reliability_score
        )

        availability_score = (
            self._availability_score(
                agent.availability
            )
        )

        failure_penalty = min(
            30.0,
            agent.consecutive_failures
            * 5.0,
        )

        total_score = (
            capability_score * 0.25
            + supported_task_score * 0.15
            + capacity_score * 0.15
            + workload_score * 0.15
            + performance_score * 0.10
            + agent.quality_score * 0.10
            + reliability_score * 0.05
            + availability_score * 0.05
            - failure_penalty
        )

        reasons: list[str] = []

        if excluded:
            reasons.append(
                "Agent explicitly excluded"
            )

        if missing_capabilities:
            reasons.append(
                "missing required capabilities"
            )

        if missing_tasks:
            reasons.append(
                "missing required task support"
            )

        if agent.availability in {
            TaskAgentAvailability.OFFLINE,
            TaskAgentAvailability.MAINTENANCE,
            TaskAgentAvailability.OVERLOADED,
        }:
            reasons.append(
                (
                    "Agent availability does "
                    "not permit assignment"
                )
            )

        if not agent.has_capacity:
            reasons.append(
                "Agent has no remaining capacity"
            )

        if (
            agent.workload_ratio
            >= self._maximum_workload_ratio
        ):
            reasons.append(
                "Agent workload exceeds policy"
            )

        if (
            agent.success_rate
            < self._minimum_success_rate
        ):
            reasons.append(
                "Agent success rate below policy"
            )

        if (
            agent.quality_score
            < self._minimum_quality_score
        ):
            reasons.append(
                "Agent quality below policy"
            )

        if (
            agent.reliability_score
            < self._minimum_reliability_score
        ):
            reasons.append(
                "Agent reliability below policy"
            )

        eligible = (
            not excluded
            and not missing_capabilities
            and not missing_tasks
            and agent.availability
            in {
                TaskAgentAvailability.AVAILABLE,
                TaskAgentAvailability.BUSY,
            }
            and agent.has_capacity
            and agent.workload_ratio
            < self._maximum_workload_ratio
            and agent.success_rate
            >= self._minimum_success_rate
            and agent.quality_score
            >= self._minimum_quality_score
            and agent.reliability_score
            >= self._minimum_reliability_score
        )

        return TaskAgentScore(
            agent_id=agent.agent_id,
            task_id=task.task_id,
            capability_score=round(
                capability_score,
                4,
            ),
            supported_task_score=round(
                supported_task_score,
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
            performance_score=round(
                performance_score,
                4,
            ),
            reliability_score=round(
                reliability_score,
                4,
            ),
            availability_score=round(
                availability_score,
                4,
            ),
            total_score=round(
                max(0.0, total_score),
                4,
            ),
            eligible=eligible,
            matched_capabilities=(
                matched_capabilities
            ),
            missing_capabilities=(
                missing_capabilities
            ),
            matched_tasks=matched_tasks,
            missing_tasks=missing_tasks,
            reasons=reasons,
        )

    @staticmethod
    def _availability_score(
        availability: TaskAgentAvailability,
    ) -> float:
        return {
            TaskAgentAvailability.AVAILABLE:
                100.0,
            TaskAgentAvailability.BUSY:
                70.0,
            TaskAgentAvailability.DEGRADED:
                40.0,
            TaskAgentAvailability.OVERLOADED:
                10.0,
            TaskAgentAvailability.MAINTENANCE:
                0.0,
            TaskAgentAvailability.OFFLINE:
                0.0,
        }[availability]
