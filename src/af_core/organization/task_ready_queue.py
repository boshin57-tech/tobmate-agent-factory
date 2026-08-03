from __future__ import annotations

from .task_coordination_models import (
    CoordinatedTask,
    CoordinatedTaskStatus,
    TaskCoordinationWorkflow,
    TaskExecutionMode,
)
from .task_dependency_models import (
    ReadyTaskQueue,
    ReadyTaskRanking,
    TaskDependencyGraph,
)


class TaskReadyQueueEngine:
    """
    Produces a deterministic, priority-aware queue of executable tasks.
    """

    def build_queue(
        self,
        *,
        workflow: TaskCoordinationWorkflow,
        graph: TaskDependencyGraph,
        include_assigned: bool = False,
    ) -> ReadyTaskQueue:
        eligible_statuses = {
            CoordinatedTaskStatus.READY,
            CoordinatedTaskStatus
            .RETRY_PENDING,
        }

        if include_assigned:
            eligible_statuses.add(
                CoordinatedTaskStatus
                .ASSIGNED
            )

        rankings: list[
            ReadyTaskRanking
        ] = []

        for task in workflow.tasks:
            if task.status not in (
                eligible_statuses
            ):
                continue

            node = graph.nodes.get(
                task.task_id
            )

            if node is None:
                raise ValueError(
                    "workflow task is missing "
                    "from dependency graph"
                )

            score = (
                task.priority.rank
                * 100.0
                + len(node.dependents)
                * 10.0
                + node.depth
                * 2.0
                + self._duration_bonus(
                    task
                    .estimated_duration_minutes
                )
                + self._mode_bonus(
                    task.execution_mode
                )
            )

            rankings.append(
                ReadyTaskRanking(
                    task_id=task.task_id,
                    priority_rank=(
                        task.priority.rank
                    ),
                    dependency_depth=(
                        node.depth
                    ),
                    dependent_count=len(
                        node.dependents
                    ),
                    estimated_duration_minutes=(
                        task
                        .estimated_duration_minutes
                    ),
                    scheduling_score=round(
                        score,
                        4,
                    ),
                )
            )

        rankings.sort(
            key=lambda item: (
                -item.scheduling_score,
                -item.priority_rank,
                -item.dependent_count,
                -item.dependency_depth,
                item
                .estimated_duration_minutes,
                item.task_id,
            )
        )

        return ReadyTaskQueue(
            workflow_id=(
                workflow.workflow_id
            ),
            ranked_tasks=rankings,
        )

    def select_batch(
        self,
        *,
        workflow: TaskCoordinationWorkflow,
        graph: TaskDependencyGraph,
        maximum_tasks: int,
    ) -> list[str]:
        if maximum_tasks < 1:
            raise ValueError(
                "maximum_tasks must be at least 1"
            )

        queue = self.build_queue(
            workflow=workflow,
            graph=graph,
        )

        tasks_by_id = {
            task.task_id: task
            for task in workflow.tasks
        }

        selected: list[str] = []

        for ranking in queue.ranked_tasks:
            task = tasks_by_id[
                ranking.task_id
            ]

            if (
                task.execution_mode
                is TaskExecutionMode
                .EXCLUSIVE
            ):
                if not selected:
                    return [
                        task.task_id
                    ]

                continue

            selected.append(
                task.task_id
            )

            if len(selected) >= maximum_tasks:
                break

        return selected

    @staticmethod
    def _duration_bonus(
        duration_minutes: int,
    ) -> float:
        if duration_minutes <= 0:
            return 5.0

        return max(
            0.0,
            10.0
            - min(
                10.0,
                duration_minutes
                / 60.0,
            ),
        )

    @staticmethod
    def _mode_bonus(
        mode: TaskExecutionMode,
    ) -> float:
        if (
            mode
            is TaskExecutionMode.PARALLEL
        ):
            return 3.0

        if (
            mode
            is TaskExecutionMode.EXCLUSIVE
        ):
            return 1.0

        return 0.0
