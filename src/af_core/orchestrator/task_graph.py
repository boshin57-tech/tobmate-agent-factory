from __future__ import annotations

from collections import defaultdict, deque
from enum import StrEnum

from pydantic import BaseModel, Field

from .planner import PlannedTask, ProjectPlan


class TaskGraphError(ValueError):
    """Raised when a task graph is invalid."""


class GraphTaskStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class TaskGraphState(BaseModel):
    statuses: dict[str, GraphTaskStatus] = Field(default_factory=dict)


class TaskGraph:
    def __init__(self, plan: ProjectPlan) -> None:
        self.plan = plan
        self.tasks = {
            task.id: task
            for task in plan.tasks
        }
        self.dependencies = {
            task.id: set(task.dependencies)
            for task in plan.tasks
        }
        self.dependents = self._build_dependents()

        self._validate()
        self.topological_order = self._topological_sort()

    def initial_state(self) -> TaskGraphState:
        return TaskGraphState(
            statuses={
                task_id: GraphTaskStatus.PENDING
                for task_id in self.tasks
            }
        )

    def ready_tasks(
        self,
        state: TaskGraphState,
    ) -> list[PlannedTask]:
        self._validate_state(state)

        ready: list[PlannedTask] = []

        for task_id in self.topological_order:
            if state.statuses[task_id] is not GraphTaskStatus.PENDING:
                continue

            dependency_states = [
                state.statuses[dependency]
                for dependency in self.dependencies[task_id]
            ]

            if all(
                status is GraphTaskStatus.COMPLETED
                for status in dependency_states
            ):
                ready.append(self.tasks[task_id])

        return ready

    def mark_running(
        self,
        state: TaskGraphState,
        task_id: str,
    ) -> TaskGraphState:
        self._require_task(task_id)

        ready_ids = {
            task.id
            for task in self.ready_tasks(state)
        }

        if task_id not in ready_ids:
            raise TaskGraphError(
                f"Task is not ready to run: {task_id}"
            )

        return self._updated(
            state,
            task_id,
            GraphTaskStatus.RUNNING,
        )

    def mark_completed(
        self,
        state: TaskGraphState,
        task_id: str,
    ) -> TaskGraphState:
        self._require_status(
            state,
            task_id,
            GraphTaskStatus.RUNNING,
        )

        return self._updated(
            state,
            task_id,
            GraphTaskStatus.COMPLETED,
        )

    def mark_failed(
        self,
        state: TaskGraphState,
        task_id: str,
    ) -> TaskGraphState:
        self._require_task(task_id)

        current = state.statuses.get(task_id)

        if current not in {
            GraphTaskStatus.PENDING,
            GraphTaskStatus.RUNNING,
        }:
            raise TaskGraphError(
                f"Task cannot fail from state {current}: {task_id}"
            )

        updated = dict(state.statuses)
        updated[task_id] = GraphTaskStatus.FAILED

        queue = deque(self.dependents[task_id])
        visited: set[str] = set()

        while queue:
            dependent = queue.popleft()

            if dependent in visited:
                continue

            visited.add(dependent)

            if updated[dependent] is GraphTaskStatus.PENDING:
                updated[dependent] = GraphTaskStatus.BLOCKED

            queue.extend(self.dependents[dependent])

        return TaskGraphState(statuses=updated)

    def is_complete(self, state: TaskGraphState) -> bool:
        self._validate_state(state)

        return all(
            status is GraphTaskStatus.COMPLETED
            for status in state.statuses.values()
        )

    def has_failures(self, state: TaskGraphState) -> bool:
        self._validate_state(state)

        return any(
            status in {
                GraphTaskStatus.FAILED,
                GraphTaskStatus.BLOCKED,
            }
            for status in state.statuses.values()
        )

    def _build_dependents(self) -> dict[str, set[str]]:
        result: dict[str, set[str]] = defaultdict(set)

        for task_id, dependencies in self.dependencies.items():
            result.setdefault(task_id, set())

            for dependency in dependencies:
                result[dependency].add(task_id)

        return dict(result)

    def _validate(self) -> None:
        known = set(self.tasks)

        for task_id, dependencies in self.dependencies.items():
            unknown = dependencies - known

            if unknown:
                raise TaskGraphError(
                    f"Task {task_id} has unknown dependencies: "
                    f"{', '.join(sorted(unknown))}"
                )

    def _topological_sort(self) -> list[str]:
        indegree = {
            task_id: len(dependencies)
            for task_id, dependencies in self.dependencies.items()
        }

        queue = deque(
            sorted(
                task_id
                for task_id, degree in indegree.items()
                if degree == 0
            )
        )
        ordered: list[str] = []

        while queue:
            task_id = queue.popleft()
            ordered.append(task_id)

            for dependent in sorted(self.dependents[task_id]):
                indegree[dependent] -= 1

                if indegree[dependent] == 0:
                    queue.append(dependent)

        if len(ordered) != len(self.tasks):
            unresolved = sorted(
                task_id
                for task_id, degree in indegree.items()
                if degree > 0
            )

            raise TaskGraphError(
                "Task graph contains a dependency cycle: "
                + ", ".join(unresolved)
            )

        return ordered

    def _updated(
        self,
        state: TaskGraphState,
        task_id: str,
        status: GraphTaskStatus,
    ) -> TaskGraphState:
        updated = dict(state.statuses)
        updated[task_id] = status
        return TaskGraphState(statuses=updated)

    def _validate_state(
        self,
        state: TaskGraphState,
    ) -> None:
        expected = set(self.tasks)
        actual = set(state.statuses)

        if expected != actual:
            raise TaskGraphError(
                "Task graph state does not match plan tasks."
            )

    def _require_task(self, task_id: str) -> None:
        if task_id not in self.tasks:
            raise TaskGraphError(
                f"Unknown task: {task_id}"
            )

    def _require_status(
        self,
        state: TaskGraphState,
        task_id: str,
        expected: GraphTaskStatus,
    ) -> None:
        self._require_task(task_id)
        self._validate_state(state)

        actual = state.statuses[task_id]

        if actual is not expected:
            raise TaskGraphError(
                f"Task {task_id} must be {expected}, got {actual}"
            )
