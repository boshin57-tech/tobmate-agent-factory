from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from af_core.orchestrator.planner import PlannedTask, ProjectPlan
from af_core.orchestrator.task_graph import (
    GraphTaskStatus,
    TaskGraph,
)
from af_core.workspace.manager import (
    WorkspaceManager,
    WorkspaceRecord,
)

from .parallel_models import (
    AgentTaskAssignment,
    AgentTaskResult,
    ParallelBatch,
    ParallelExecutionResult,
)


ParallelTaskHandler = Callable[
    [
        PlannedTask,
        AgentTaskAssignment,
        WorkspaceRecord,
    ],
    Awaitable[AgentTaskResult],
]


class ParallelExecutionError(RuntimeError):
    """Raised when parallel execution cannot continue safely."""


class ParallelTaskScheduler:
    def __init__(
        self,
        *,
        workspace_root: str | Path,
        maximum_parallelism: int = 2,
    ) -> None:
        if maximum_parallelism < 1:
            raise ValueError(
                "maximum_parallelism must be at least 1"
            )

        self.workspace_root = Path(
            workspace_root
        ).expanduser().resolve()
        self.workspace_root.mkdir(
            parents=True,
            exist_ok=True,
        )
        self.maximum_parallelism = maximum_parallelism

    async def execute(
        self,
        *,
        plan: ProjectPlan,
        source_repository: str | Path,
        project_id: str,
        run_id: str,
        handler: ParallelTaskHandler,
        base_revision: str = "HEAD",
    ) -> ParallelExecutionResult:
        graph = TaskGraph(plan)
        state = graph.initial_state()

        results: dict[str, AgentTaskResult] = {}
        batches: list[ParallelBatch] = []
        batch_number = 1

        while True:
            ready = graph.ready_tasks(state)

            if not ready:
                break

            batch_tasks = ready[: self.maximum_parallelism]

            batches.append(
                ParallelBatch(
                    batch_number=batch_number,
                    task_ids=[
                        task.id
                        for task in batch_tasks
                    ],
                    maximum_parallelism=(
                        self.maximum_parallelism
                    ),
                )
            )

            running_state = state

            for task in batch_tasks:
                running_state = graph.mark_running(
                    running_state,
                    task.id,
                )

            state = running_state

            batch_results = await asyncio.gather(
                *[
                    self._execute_task(
                        task=task,
                        source_repository=source_repository,
                        project_id=project_id,
                        run_id=run_id,
                        handler=handler,
                        base_revision=base_revision,
                    )
                    for task in batch_tasks
                ],
                return_exceptions=True,
            )

            for task, task_result in zip(
                batch_tasks,
                batch_results,
                strict=True,
            ):
                if isinstance(task_result, Exception):
                    state = graph.mark_failed(
                        state,
                        task.id,
                    )

                    results[task.id] = AgentTaskResult(
                        task_id=task.id,
                        agent_name=self._agent_name(
                            task,
                        ),
                        success=False,
                        workspace_path="",
                        branch="",
                        error=str(task_result),
                    )
                    continue

                results[task.id] = task_result

                if task_result.success:
                    state = graph.mark_completed(
                        state,
                        task.id,
                    )
                else:
                    state = graph.mark_failed(
                        state,
                        task.id,
                    )

            batch_number += 1

            if graph.has_failures(state):
                break

        failed = sorted(
            task_id
            for task_id, status in state.statuses.items()
            if status is GraphTaskStatus.FAILED
        )
        blocked = sorted(
            task_id
            for task_id, status in state.statuses.items()
            if status is GraphTaskStatus.BLOCKED
        )

        return ParallelExecutionResult(
            successful=(
                not failed
                and not blocked
                and graph.is_complete(state)
            ),
            batches=batches,
            task_results=results,
            failed_task_ids=failed,
            blocked_task_ids=blocked,
        )

    async def _execute_task(
        self,
        *,
        task: PlannedTask,
        source_repository: str | Path,
        project_id: str,
        run_id: str,
        handler: ParallelTaskHandler,
        base_revision: str,
    ) -> AgentTaskResult:
        task_project_id = (
            f"{project_id}-{task.id}"
        )
        task_run_id = (
            f"{run_id}-{task.id}"
        )

        manager = WorkspaceManager(
            self.workspace_root
        )
        workspace = manager.create(
            source_repository=source_repository,
            project_id=task_project_id,
            run_id=task_run_id,
            base_revision=base_revision,
        )

        assignment = AgentTaskAssignment(
            task_id=task.id,
            agent_name=self._agent_name(task),
            agent_role=task.agent_role,
            workspace_path=workspace.workspace_path,
            branch=workspace.branch,
            attempt=1,
        )

        result = await handler(
            task,
            assignment,
            workspace,
        )

        if result.task_id != task.id:
            raise ParallelExecutionError(
                "Handler returned result for wrong task: "
                f"expected {task.id}, got {result.task_id}"
            )

        if result.workspace_path != workspace.workspace_path:
            raise ParallelExecutionError(
                f"Handler changed workspace identity for {task.id}"
            )

        if result.branch != workspace.branch:
            raise ParallelExecutionError(
                f"Handler changed branch identity for {task.id}"
            )

        return result

    def _agent_name(
        self,
        task: PlannedTask,
    ) -> str:
        return f"{task.agent_role}-{task.id}"
