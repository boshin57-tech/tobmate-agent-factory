"""Autonomous project execution lifecycle coordination."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Mapping

from af_core.orchestrator.project_execution_models import (
    ProjectExecutionError,
    ProjectRunEventKind,
    ProjectRunSnapshot,
    ProjectRunState,
    ProjectRunStatus,
    ProjectTaskRuntimeState,
    ProjectTaskStatus,
)
from af_core.orchestrator.project_execution_repository import (
    JsonProjectRunRepository,
)


class ProjectExecutionRuntimeError(ProjectExecutionError):
    """Raised when project execution coordination is invalid."""


class ProjectExecutionRuntime:
    """Coordinate planning, task registration and readiness."""

    def __init__(
        self,
        repository: JsonProjectRunRepository,
    ) -> None:
        self._repository = repository

    @property
    def repository(self) -> JsonProjectRunRepository:
        return self._repository

    def create_run(
        self,
        *,
        project_id: str,
        repository_path: str,
        now: float,
        workflow_id: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> ProjectRunSnapshot:
        """Create and persist one autonomous project run."""

        state = ProjectRunState.create(
            project_id=project_id,
            repository_path=repository_path,
            now=now,
            workflow_id=workflow_id,
            metadata=metadata,
        )

        return self._repository.create(
            state,
            occurred_at=now,
        )

    def begin_planning(
        self,
        run_id: str,
        *,
        now: float,
    ) -> ProjectRunSnapshot:
        """Move a newly created run into planning."""

        current = self._repository.get(run_id)
        planned = current.state.transition(
            ProjectRunStatus.PLANNING,
            now=now,
        )

        return self._repository.save(
            planned,
            expected_version=current.state.version,
            occurred_at=now,
            event_kind=ProjectRunEventKind.RUN_TRANSITIONED,
            detail={
                "previous_status": (
                    current.state.status.value
                ),
            },
        )

    def register_task(
        self,
        run_id: str,
        *,
        task_id: str,
        now: float,
        dependencies: Iterable[str] = (),
        assigned_agent_id: str | None = None,
        assigned_team_id: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> ProjectRunSnapshot:
        """Register one planned task and dependency declaration."""

        current = self._repository.get(run_id)
        state = current.state

        if state.status is not ProjectRunStatus.PLANNING:
            raise ProjectExecutionRuntimeError(
                "tasks may only be registered during planning"
            )

        if task_id in state.tasks:
            raise ProjectExecutionRuntimeError(
                f"task already registered: {task_id}"
            )

        dependency_ids = tuple(
            dict.fromkeys(dependencies)
        )

        if task_id in dependency_ids:
            raise ProjectExecutionRuntimeError(
                "task cannot depend on itself"
            )

        task_metadata = dict(metadata or {})
        task_metadata["dependencies"] = dependency_ids

        task = ProjectTaskRuntimeState(
            task_id=task_id,
            assigned_agent_id=assigned_agent_id,
            assigned_team_id=assigned_team_id,
            metadata=task_metadata,
        )

        updated = state.with_task(
            task,
            now=now,
        )

        return self._repository.save(
            updated,
            expected_version=state.version,
            occurred_at=now,
            event_kind=ProjectRunEventKind.TASK_REGISTERED,
            detail={
                "task_id": task_id,
                "dependencies": list(dependency_ids),
                "assigned_agent_id": assigned_agent_id,
                "assigned_team_id": assigned_team_id,
            },
        )

    def finalize_plan(
        self,
        run_id: str,
        *,
        now: float,
    ) -> ProjectRunSnapshot:
        """Validate the task graph and make the run ready."""

        current = self._repository.get(run_id)
        state = current.state

        if state.status is not ProjectRunStatus.PLANNING:
            raise ProjectExecutionRuntimeError(
                "only planning runs may be finalized"
            )

        if not state.tasks:
            raise ProjectExecutionRuntimeError(
                "project run must contain at least one task"
            )

        self._validate_dependencies(state.tasks)

        ready = state.transition(
            ProjectRunStatus.READY,
            now=now,
        )

        return self._repository.save(
            ready,
            expected_version=state.version,
            occurred_at=now,
            event_kind=ProjectRunEventKind.RUN_TRANSITIONED,
            detail={
                "previous_status": state.status.value,
                "task_count": len(state.tasks),
            },
        )

    def start_run(
        self,
        run_id: str,
        *,
        now: float,
    ) -> ProjectRunSnapshot:
        """Start a ready or recovered project run."""

        current = self._repository.get(run_id)
        state = current.state

        if state.status not in {
            ProjectRunStatus.READY,
            ProjectRunStatus.RECOVERING,
        }:
            raise ProjectExecutionRuntimeError(
                "project run is not startable: "
                f"{state.status.value}"
            )

        running = state.transition(
            ProjectRunStatus.RUNNING,
            now=now,
        )

        return self._repository.save(
            running,
            expected_version=state.version,
            occurred_at=now,
            event_kind=ProjectRunEventKind.RUN_TRANSITIONED,
            detail={
                "previous_status": state.status.value,
            },
        )

    def refresh_ready_tasks(
        self,
        run_id: str,
        *,
        now: float,
    ) -> ProjectRunSnapshot:
        """Promote dependency-satisfied tasks to ready."""

        current = self._repository.get(run_id)
        state = current.state

        if state.status not in {
            ProjectRunStatus.READY,
            ProjectRunStatus.RUNNING,
            ProjectRunStatus.RECOVERING,
        }:
            raise ProjectExecutionRuntimeError(
                "run cannot evaluate ready tasks: "
                f"{state.status.value}"
            )

        updated = state
        changed: list[str] = []

        for task_id in sorted(state.tasks):
            task = updated.tasks[task_id]

            if task.status not in {
                ProjectTaskStatus.PENDING,
                ProjectTaskStatus.BLOCKED,
            }:
                continue

            dependencies = self._dependencies(task)

            if all(
                updated.tasks[dependency].status
                is ProjectTaskStatus.SUCCEEDED
                for dependency in dependencies
            ):
                promoted = task.transition(
                    ProjectTaskStatus.READY,
                    now=now,
                )

                updated = updated.with_task(
                    promoted,
                    now=now,
                )
                changed.append(task_id)

        if not changed:
            return current

        return self._repository.save(
            updated,
            expected_version=state.version,
            occurred_at=now,
            event_kind=ProjectRunEventKind.TASK_TRANSITIONED,
            detail={
                "ready_tasks": changed,
            },
        )

    def ready_tasks(
        self,
        run_id: str,
    ) -> tuple[ProjectTaskRuntimeState, ...]:
        """Return ready tasks in deterministic order."""

        state = self._repository.get(run_id).state

        return tuple(
            state.tasks[task_id]
            for task_id in sorted(state.tasks)
            if (
                state.tasks[task_id].status
                is ProjectTaskStatus.READY
            )
        )

    @staticmethod
    def _dependencies(
        task: ProjectTaskRuntimeState,
    ) -> tuple[str, ...]:
        return tuple(
            str(item)
            for item in task.metadata.get(
                "dependencies",
                (),
            )
        )

    def _validate_dependencies(
        self,
        tasks: Mapping[
            str,
            ProjectTaskRuntimeState,
        ],
    ) -> None:
        task_ids = set(tasks)

        for task in tasks.values():
            unknown = (
                set(self._dependencies(task))
                - task_ids
            )

            if unknown:
                raise ProjectExecutionRuntimeError(
                    f"task {task.task_id} has unknown "
                    "dependencies: "
                    + ", ".join(sorted(unknown))
                )

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visited:
                return

            if task_id in visiting:
                raise ProjectExecutionRuntimeError(
                    "cyclic project task dependency detected"
                )

            visiting.add(task_id)

            for dependency in self._dependencies(
                tasks[task_id]
            ):
                visit(dependency)

            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in sorted(tasks):
            visit(task_id)


from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass(frozen=True, slots=True)
class ProjectTaskExecutionResult:
    """Result returned by an autonomous task executor."""

    succeeded: bool
    output_reference: str | None = None
    error: str = ""
    metadata: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class ProjectExecutionCycle:
    """Summary of one autonomous task execution cycle."""

    run_id: str
    task_id: str
    status: ProjectTaskStatus
    succeeded: bool
    output_reference: str | None = None
    error: str = ""


class ProjectTaskExecutor(Protocol):
    """Adapter capable of executing one project task."""

    def execute(
        self,
        *,
        run: ProjectRunState,
        task: ProjectTaskRuntimeState,
    ) -> ProjectTaskExecutionResult:
        ...


class AutonomousProjectExecutionRuntime(
    ProjectExecutionRuntime
):
    """Execute ready project tasks and persist lifecycle changes."""

    def assign_task(
        self,
        run_id: str,
        task_id: str,
        *,
        now: float,
        agent_id: str | None = None,
        team_id: str | None = None,
    ) -> ProjectRunSnapshot:
        """Assign a ready task to an agent or team."""

        current = self.repository.get(run_id)
        state = current.state
        task = self._task(state, task_id)

        if task.status is not ProjectTaskStatus.READY:
            raise ProjectExecutionRuntimeError(
                "only ready tasks may be assigned"
            )

        if agent_id is None and team_id is None:
            raise ProjectExecutionRuntimeError(
                "agent_id or team_id is required"
            )

        assigned = replace(
            task,
            assigned_agent_id=agent_id,
            assigned_team_id=team_id,
        )

        updated = state.with_task(
            assigned,
            now=now,
        )

        return self.repository.save(
            updated,
            expected_version=state.version,
            occurred_at=now,
            event_kind=ProjectRunEventKind.TASK_ASSIGNED,
            detail={
                "task_id": task_id,
                "agent_id": agent_id,
                "team_id": team_id,
            },
        )

    def begin_task(
        self,
        run_id: str,
        task_id: str,
        *,
        now: float,
    ) -> ProjectRunSnapshot:
        """Move one ready task into active execution."""

        current = self.repository.get(run_id)
        state = current.state

        if state.status is not ProjectRunStatus.RUNNING:
            raise ProjectExecutionRuntimeError(
                "tasks may only execute while run is running"
            )

        task = self._task(state, task_id)

        if task.status is not ProjectTaskStatus.READY:
            raise ProjectExecutionRuntimeError(
                "task is not ready for execution"
            )

        running = task.transition(
            ProjectTaskStatus.RUNNING,
            now=now,
        )

        updated = state.with_task(
            running,
            now=now,
        )

        return self.repository.save(
            updated,
            expected_version=state.version,
            occurred_at=now,
            event_kind=ProjectRunEventKind.TASK_TRANSITIONED,
            detail={
                "task_id": task_id,
                "previous_status": task.status.value,
                "status": running.status.value,
                "attempt": running.attempts,
            },
        )

    def complete_task(
        self,
        run_id: str,
        task_id: str,
        *,
        now: float,
        output_reference: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> ProjectRunSnapshot:
        """Persist successful task completion and output."""

        current = self.repository.get(run_id)
        state = current.state
        task = self._task(state, task_id)

        if task.status is not ProjectTaskStatus.RUNNING:
            raise ProjectExecutionRuntimeError(
                "only running tasks may complete"
            )

        completed = task.transition(
            ProjectTaskStatus.SUCCEEDED,
            now=now,
        )

        merged_metadata = dict(completed.metadata)
        merged_metadata.update(dict(metadata or {}))

        completed = replace(
            completed,
            output_reference=output_reference,
            metadata=merged_metadata,
        )

        updated = state.with_task(
            completed,
            now=now,
        )

        saved = self.repository.save(
            updated,
            expected_version=state.version,
            occurred_at=now,
            event_kind=ProjectRunEventKind.TASK_TRANSITIONED,
            detail={
                "task_id": task_id,
                "previous_status": task.status.value,
                "status": completed.status.value,
            },
        )

        self.repository.append_event(
            run_id,
            kind=ProjectRunEventKind.TASK_OUTPUT_RECORDED,
            occurred_at=now,
            task_id=task_id,
            detail={
                "output_reference": output_reference,
            },
        )

        return self.repository.get(
            saved.state.run_id
        )

    def fail_task(
        self,
        run_id: str,
        task_id: str,
        *,
        now: float,
        error: str,
    ) -> ProjectRunSnapshot:
        """Persist one task execution failure."""

        current = self.repository.get(run_id)
        state = current.state
        task = self._task(state, task_id)

        if task.status is not ProjectTaskStatus.RUNNING:
            raise ProjectExecutionRuntimeError(
                "only running tasks may fail"
            )

        failed = task.transition(
            ProjectTaskStatus.FAILED,
            now=now,
            error=error,
        )

        updated = state.with_task(
            failed,
            now=now,
        )

        return self.repository.save(
            updated,
            expected_version=state.version,
            occurred_at=now,
            event_kind=ProjectRunEventKind.TASK_TRANSITIONED,
            detail={
                "task_id": task_id,
                "previous_status": task.status.value,
                "status": failed.status.value,
                "error": error,
            },
        )

    @staticmethod
    def _task(
        state: ProjectRunState,
        task_id: str,
    ) -> ProjectTaskRuntimeState:
        try:
            return state.tasks[task_id]
        except KeyError as exc:
            raise ProjectExecutionRuntimeError(
                f"project task not found: {task_id}"
            ) from exc

    def retry_task(
        self,
        run_id: str,
        task_id: str,
        *,
        now: float,
    ) -> ProjectRunSnapshot:
        """Return a failed or blocked task to ready state."""

        current = self.repository.get(run_id)
        state = current.state
        task = self._task(state, task_id)

        if state.status not in {
            ProjectRunStatus.RUNNING,
            ProjectRunStatus.RECOVERING,
        }:
            raise ProjectExecutionRuntimeError(
                "run is not eligible for task retry"
            )

        if task.status not in {
            ProjectTaskStatus.FAILED,
            ProjectTaskStatus.BLOCKED,
        }:
            raise ProjectExecutionRuntimeError(
                "task is not retryable"
            )

        dependencies = self._dependencies(task)

        if not all(
            state.tasks[dependency].status
            is ProjectTaskStatus.SUCCEEDED
            for dependency in dependencies
        ):
            raise ProjectExecutionRuntimeError(
                "task dependencies are not satisfied"
            )

        ready = task.transition(
            ProjectTaskStatus.READY,
            now=now,
        )

        updated = state.with_task(
            ready,
            now=now,
        )

        return self.repository.save(
            updated,
            expected_version=state.version,
            occurred_at=now,
            event_kind=ProjectRunEventKind.TASK_TRANSITIONED,
            detail={
                "task_id": task_id,
                "previous_status": task.status.value,
                "status": ready.status.value,
                "retry_attempt": task.attempts + 1,
            },
        )

    def execute_next(
        self,
        run_id: str,
        executor: ProjectTaskExecutor,
        *,
        now: float,
        default_agent_id: str | None = None,
        default_team_id: str | None = None,
    ) -> ProjectExecutionCycle | None:
        """Execute the next deterministic ready task."""

        current = self.repository.get(run_id)

        if current.state.status is not ProjectRunStatus.RUNNING:
            raise ProjectExecutionRuntimeError(
                "project run is not running"
            )

        self.refresh_ready_tasks(
            run_id,
            now=now,
        )

        ready = self.ready_tasks(run_id)

        if not ready:
            return None

        task = ready[0]

        if (
            task.assigned_agent_id is None
            and task.assigned_team_id is None
        ):
            if (
                default_agent_id is None
                and default_team_id is None
            ):
                raise ProjectExecutionRuntimeError(
                    "ready task has no agent or team assignment"
                )

            assigned = self.assign_task(
                run_id,
                task.task_id,
                now=now,
                agent_id=default_agent_id,
                team_id=default_team_id,
            )

            task = assigned.state.tasks[
                task.task_id
            ]

        started = self.begin_task(
            run_id,
            task.task_id,
            now=now,
        )

        running_task = started.state.tasks[
            task.task_id
        ]

        try:
            result = executor.execute(
                run=started.state,
                task=running_task,
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

            self.fail_task(
                run_id,
                task.task_id,
                now=now,
                error=error,
            )

            return ProjectExecutionCycle(
                run_id=run_id,
                task_id=task.task_id,
                status=ProjectTaskStatus.FAILED,
                succeeded=False,
                error=error,
            )

        if not isinstance(
            result,
            ProjectTaskExecutionResult,
        ):
            error = (
                "executor returned unsupported result type"
            )

            self.fail_task(
                run_id,
                task.task_id,
                now=now,
                error=error,
            )

            return ProjectExecutionCycle(
                run_id=run_id,
                task_id=task.task_id,
                status=ProjectTaskStatus.FAILED,
                succeeded=False,
                error=error,
            )

        if result.succeeded:
            self.complete_task(
                run_id,
                task.task_id,
                now=now,
                output_reference=result.output_reference,
                metadata=result.metadata,
            )

            self.refresh_ready_tasks(
                run_id,
                now=now,
            )

            return ProjectExecutionCycle(
                run_id=run_id,
                task_id=task.task_id,
                status=ProjectTaskStatus.SUCCEEDED,
                succeeded=True,
                output_reference=(
                    result.output_reference
                ),
            )

        error = result.error or (
            "task execution failed"
        )

        self.fail_task(
            run_id,
            task.task_id,
            now=now,
            error=error,
        )

        return ProjectExecutionCycle(
            run_id=run_id,
            task_id=task.task_id,
            status=ProjectTaskStatus.FAILED,
            succeeded=False,
            error=error,
        )

    def run_until_blocked(
        self,
        run_id: str,
        executor: ProjectTaskExecutor,
        *,
        clock: Callable[[], float],
        limit: int = 100,
        default_agent_id: str | None = None,
        default_team_id: str | None = None,
    ) -> tuple[ProjectExecutionCycle, ...]:
        """Execute tasks until no work remains or failure blocks progress."""

        if limit < 1:
            raise ProjectExecutionRuntimeError(
                "execution limit must be at least one"
            )

        cycles: list[ProjectExecutionCycle] = []

        for _ in range(limit):
            cycle = self.execute_next(
                run_id,
                executor,
                now=clock(),
                default_agent_id=default_agent_id,
                default_team_id=default_team_id,
            )

            if cycle is None:
                break

            cycles.append(cycle)

            if not cycle.succeeded:
                break

        return tuple(cycles)
