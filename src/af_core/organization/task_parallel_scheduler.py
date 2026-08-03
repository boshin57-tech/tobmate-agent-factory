from __future__ import annotations

from .task_coordination_models import (
    CoordinatedTask,
    TaskExecutionMode,
)
from .task_dependency_models import (
    ParallelSchedule,
    TaskDependencyGraph,
    TaskExecutionWave,
)


class ParallelTaskScheduler:
    """
    Converts a validated task dependency graph into an executable
    parallel schedule.

    Scheduling guarantees:
    - Dependency waves preserve topological ordering.
    - Exclusive tasks receive their own execution wave.
    - Non-exclusive tasks in the same dependency wave may execute
      together.
    - Task priority determines ordering within each wave.
    """

    def build_schedule(
        self,
        *,
        graph: TaskDependencyGraph,
        tasks: list[CoordinatedTask],
    ) -> ParallelSchedule:
        if graph.has_cycle:
            raise ValueError(
                "cannot schedule a cyclic dependency graph"
            )

        tasks_by_id = {
            task.task_id: task
            for task in tasks
        }

        missing_task_ids = (
            set(graph.nodes)
            - set(tasks_by_id)
        )

        if missing_task_ids:
            raise ValueError(
                "graph contains unknown task IDs: "
                + ", ".join(
                    sorted(missing_task_ids)
                )
            )

        waves: list[
            TaskExecutionWave
        ] = []

        wave_number = 0

        for dependency_wave in (
            graph.execution_waves
        ):
            ordered_tasks = sorted(
                (
                    tasks_by_id[task_id]
                    for task_id
                    in dependency_wave
                ),
                key=lambda task: (
                    -task.priority.rank,
                    task.task_id,
                ),
            )

            normal_tasks = [
                task
                for task in ordered_tasks
                if (
                    task.execution_mode
                    is not TaskExecutionMode
                    .EXCLUSIVE
                )
            ]

            exclusive_tasks = [
                task
                for task in ordered_tasks
                if (
                    task.execution_mode
                    is TaskExecutionMode
                    .EXCLUSIVE
                )
            ]

            if normal_tasks:
                waves.append(
                    self._build_normal_wave(
                        wave_number=(
                            wave_number
                        ),
                        tasks=normal_tasks,
                    )
                )

                wave_number += 1

            for task in exclusive_tasks:
                waves.append(
                    TaskExecutionWave(
                        wave_number=(
                            wave_number
                        ),
                        task_ids=[
                            task.task_id
                        ],
                        parallel_task_ids=[],
                        exclusive_task_ids=[
                            task.task_id
                        ],
                        estimated_duration_minutes=(
                            task
                            .estimated_duration_minutes
                        ),
                    )
                )

                wave_number += 1

        maximum_parallelism = max(
            (
                len(wave.task_ids)
                for wave in waves
            ),
            default=0,
        )

        estimated_duration = sum(
            wave.estimated_duration_minutes
            for wave in waves
        )

        return ParallelSchedule(
            workflow_id=graph.workflow_id,
            waves=waves,
            total_task_count=len(tasks),
            maximum_parallelism=(
                maximum_parallelism
            ),
            estimated_duration_minutes=(
                estimated_duration
            ),
            critical_path=list(
                graph.critical_path
            ),
            critical_path_duration_minutes=(
                graph
                .critical_path_duration_minutes
            ),
        )

    @staticmethod
    def _build_normal_wave(
        *,
        wave_number: int,
        tasks: list[CoordinatedTask],
    ) -> TaskExecutionWave:
        task_ids = [
            task.task_id
            for task in tasks
        ]

        parallel_ids = [
            task.task_id
            for task in tasks
            if (
                task.execution_mode
                is TaskExecutionMode.PARALLEL
            )
        ]

        sequential_ids = [
            task.task_id
            for task in tasks
            if (
                task.execution_mode
                is TaskExecutionMode.SEQUENTIAL
            )
        ]

        if sequential_ids:
            duration = sum(
                task.estimated_duration_minutes
                for task in tasks
                if task.task_id
                in sequential_ids
            )

            parallel_duration = max(
                (
                    task.estimated_duration_minutes
                    for task in tasks
                    if task.task_id
                    in parallel_ids
                ),
                default=0,
            )

            duration += parallel_duration
        else:
            duration = max(
                (
                    task.estimated_duration_minutes
                    for task in tasks
                ),
                default=0,
            )

        return TaskExecutionWave(
            wave_number=wave_number,
            task_ids=task_ids,
            parallel_task_ids=(
                parallel_ids
            ),
            exclusive_task_ids=[],
            estimated_duration_minutes=(
                duration
            ),
        )
