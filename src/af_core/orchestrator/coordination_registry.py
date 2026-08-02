"""Agent and task registries for multi-agent coordination."""

from __future__ import annotations

from threading import RLock

from af_core.orchestrator.coordination_models import (
    CoordinationAgent,
    CoordinationTask,
)


class CoordinationRegistryError(RuntimeError):
    pass


class CoordinationRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, CoordinationAgent] = {}
        self._tasks: dict[str, CoordinationTask] = {}
        self._lock = RLock()

    def register_agent(
        self,
        agent: CoordinationAgent,
        *,
        replace: bool = False,
    ) -> CoordinationAgent:
        with self._lock:
            if (
                agent.agent_id in self._agents
                and not replace
            ):
                raise CoordinationRegistryError(
                    "Agent already registered: "
                    f"{agent.agent_id}"
                )

            self._agents[agent.agent_id] = agent
            return agent

    def register_task(
        self,
        task: CoordinationTask,
        *,
        replace: bool = False,
    ) -> CoordinationTask:
        with self._lock:
            if (
                task.task_id in self._tasks
                and not replace
            ):
                raise CoordinationRegistryError(
                    "Task already registered: "
                    f"{task.task_id}"
                )

            missing = [
                dependency_id
                for dependency_id in task.dependency_ids
                if dependency_id not in self._tasks
            ]

            if missing:
                raise CoordinationRegistryError(
                    "Unknown task dependencies: "
                    + ", ".join(sorted(missing))
                )

            self._tasks[task.task_id] = task
            return task

    def get_agent(
        self,
        agent_id: str,
    ) -> CoordinationAgent:
        with self._lock:
            try:
                return self._agents[agent_id]
            except KeyError as exc:
                raise CoordinationRegistryError(
                    f"Unknown agent: {agent_id}"
                ) from exc

    def get_task(
        self,
        task_id: str,
    ) -> CoordinationTask:
        with self._lock:
            try:
                return self._tasks[task_id]
            except KeyError as exc:
                raise CoordinationRegistryError(
                    f"Unknown task: {task_id}"
                ) from exc

    def update_agent(
        self,
        agent: CoordinationAgent,
    ) -> CoordinationAgent:
        with self._lock:
            if agent.agent_id not in self._agents:
                raise CoordinationRegistryError(
                    f"Unknown agent: {agent.agent_id}"
                )

            self._agents[agent.agent_id] = agent
            return agent

    def update_task(
        self,
        task: CoordinationTask,
    ) -> CoordinationTask:
        with self._lock:
            if task.task_id not in self._tasks:
                raise CoordinationRegistryError(
                    f"Unknown task: {task.task_id}"
                )

            self._tasks[task.task_id] = task
            return task

    def list_agents(
        self,
    ) -> tuple[CoordinationAgent, ...]:
        with self._lock:
            return tuple(
                sorted(
                    self._agents.values(),
                    key=lambda item: item.agent_id,
                )
            )

    def list_tasks(
        self,
    ) -> tuple[CoordinationTask, ...]:
        with self._lock:
            return tuple(
                sorted(
                    self._tasks.values(),
                    key=lambda item: (
                        -item.priority,
                        item.task_id,
                    ),
                )
            )

    def task_dependencies_completed(
        self,
        task_id: str,
    ) -> bool:
        task = self.get_task(task_id)

        for dependency_id in task.dependency_ids:
            dependency = self.get_task(dependency_id)

            if dependency.status.value != "completed":
                return False

        return True

    def active_task_count(
        self,
        agent_id: str,
    ) -> int:
        with self._lock:
            return sum(
                1
                for task in self._tasks.values()
                if task.assigned_agent_id == agent_id
                and task.status.value in {
                    "assigned",
                    "running",
                }
            )
