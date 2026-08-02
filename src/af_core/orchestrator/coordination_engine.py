"""Multi-agent task assignment and conflict coordination."""

from __future__ import annotations

from threading import RLock

from af_core.orchestrator.coordination_models import (
    CoordinationAgentStatus,
    CoordinationAssignment,
    CoordinationConflict,
    CoordinationConflictType,
    CoordinationDecision,
    CoordinationSnapshot,
    CoordinationTask,
    CoordinationTaskStatus,
)
from af_core.orchestrator.coordination_registry import (
    CoordinationRegistry,
    CoordinationRegistryError,
)


class CoordinationEngineError(RuntimeError):
    pass


class CoordinationEngine:
    def __init__(
        self,
        *,
        registry: CoordinationRegistry,
    ) -> None:
        self._registry = registry
        self._assignments: list[
            CoordinationAssignment
        ] = []
        self._conflicts: list[
            CoordinationConflict
        ] = []
        self._lock = RLock()

    def assign(
        self,
        *,
        task_id: str,
        agent_id: str,
    ) -> CoordinationAssignment:
        task = self._registry.get_task(task_id)
        agent = self._registry.get_agent(agent_id)

        conflict = self._detect_assignment_conflict(
            task=task,
            agent_id=agent_id,
        )

        if conflict is not None:
            self._record_conflict(conflict)

            assignment = CoordinationAssignment(
                task_id=task_id,
                agent_id=agent_id,
                decision=CoordinationDecision.BLOCK,
                reason=conflict.reason,
                metadata={
                    "conflict_id": conflict.conflict_id,
                    "conflict_type": (
                        conflict.conflict_type.value
                    ),
                },
            )
            self._record_assignment(assignment)
            return assignment

        updated_task = task.model_copy(
            update={
                "status": CoordinationTaskStatus.ASSIGNED,
                "assigned_agent_id": agent_id,
            }
        )
        self._registry.update_task(updated_task)

        assignment = CoordinationAssignment(
            task_id=task_id,
            agent_id=agent_id,
            decision=CoordinationDecision.ASSIGN,
            reason="Task assigned to eligible agent",
        )
        self._record_assignment(assignment)
        return assignment

    def reassign(
        self,
        *,
        task_id: str,
        agent_id: str,
    ) -> CoordinationAssignment:
        task = self._registry.get_task(task_id)

        if task.assigned_agent_id is None:
            return self.assign(
                task_id=task_id,
                agent_id=agent_id,
            )

        updated = task.model_copy(
            update={
                "assigned_agent_id": None,
                "status": CoordinationTaskStatus.PENDING,
            }
        )
        self._registry.update_task(updated)

        result = self.assign(
            task_id=task_id,
            agent_id=agent_id,
        )

        if result.decision is CoordinationDecision.ASSIGN:
            result = result.model_copy(
                update={
                    "decision": CoordinationDecision.REASSIGN,
                    "reason": "Task reassigned",
                }
            )
            self._replace_last_assignment(result)

        return result

    def start_task(
        self,
        task_id: str,
    ) -> CoordinationTask:
        task = self._registry.get_task(task_id)

        if task.assigned_agent_id is None:
            raise CoordinationEngineError(
                "Task must be assigned before start"
            )

        if not self._registry.task_dependencies_completed(
            task_id
        ):
            conflict = CoordinationConflict(
                conflict_type=(
                    CoordinationConflictType
                    .DEPENDENCY_BLOCKED
                ),
                task_id=task_id,
                agent_id=task.assigned_agent_id,
                reason="Task dependencies are incomplete",
            )
            self._record_conflict(conflict)

            blocked = task.model_copy(
                update={
                    "status": (
                        CoordinationTaskStatus.BLOCKED
                    )
                }
            )
            self._registry.update_task(blocked)
            return blocked

        running = task.model_copy(
            update={
                "status": CoordinationTaskStatus.RUNNING
            }
        )
        self._registry.update_task(running)
        return running

    def complete_task(
        self,
        task_id: str,
    ) -> CoordinationTask:
        task = self._registry.get_task(task_id)

        if task.status is not CoordinationTaskStatus.RUNNING:
            raise CoordinationEngineError(
                "Only running tasks may be completed"
            )

        completed = task.model_copy(
            update={
                "status": CoordinationTaskStatus.COMPLETED
            }
        )
        self._registry.update_task(completed)

        if task.assigned_agent_id is not None:
            self._record_assignment(
                CoordinationAssignment(
                    task_id=task_id,
                    agent_id=task.assigned_agent_id,
                    decision=CoordinationDecision.COMPLETE,
                    reason="Task completed",
                )
            )

        return completed

    def assignments(
        self,
    ) -> tuple[CoordinationAssignment, ...]:
        with self._lock:
            return tuple(self._assignments)

    def conflicts(
        self,
        *,
        unresolved_only: bool = False,
    ) -> tuple[CoordinationConflict, ...]:
        with self._lock:
            conflicts = tuple(self._conflicts)

        if unresolved_only:
            conflicts = tuple(
                conflict
                for conflict in conflicts
                if not conflict.resolved
            )

        return conflicts

    def resolve_conflict(
        self,
        conflict_id: str,
    ) -> CoordinationConflict:
        with self._lock:
            for index, conflict in enumerate(
                self._conflicts
            ):
                if conflict.conflict_id != conflict_id:
                    continue

                resolved = conflict.model_copy(
                    update={"resolved": True}
                )
                self._conflicts[index] = resolved
                return resolved

        raise CoordinationEngineError(
            f"Unknown coordination conflict: {conflict_id}"
        )

    def snapshot(self) -> CoordinationSnapshot:
        tasks = self._registry.list_tasks()

        active_assignment_count = sum(
            1
            for task in tasks
            if task.assigned_agent_id is not None
            and task.status in {
                CoordinationTaskStatus.ASSIGNED,
                CoordinationTaskStatus.RUNNING,
            }
        )

        return CoordinationSnapshot(
            agent_count=len(
                self._registry.list_agents()
            ),
            task_count=len(tasks),
            active_assignment_count=(
                active_assignment_count
            ),
            unresolved_conflict_count=len(
                self.conflicts(unresolved_only=True)
            ),
        )

    def _detect_assignment_conflict(
        self,
        *,
        task: CoordinationTask,
        agent_id: str,
    ) -> CoordinationConflict | None:
        agent = self._registry.get_agent(agent_id)

        if task.assigned_agent_id is not None:
            return CoordinationConflict(
                conflict_type=(
                    CoordinationConflictType
                    .DUPLICATE_ASSIGNMENT
                ),
                task_id=task.task_id,
                agent_id=agent_id,
                reason="Task is already assigned",
            )

        if agent.status not in {
            CoordinationAgentStatus.ACTIVE,
            CoordinationAgentStatus.BUSY,
        }:
            return CoordinationConflict(
                conflict_type=(
                    CoordinationConflictType
                    .RESOURCE_CONFLICT
                ),
                task_id=task.task_id,
                agent_id=agent_id,
                reason="Agent is unavailable",
            )

        missing = (
            task.required_capability_ids
            - agent.capability_ids
        )

        if missing:
            return CoordinationConflict(
                conflict_type=(
                    CoordinationConflictType
                    .CAPABILITY_MISMATCH
                ),
                task_id=task.task_id,
                agent_id=agent_id,
                reason=(
                    "Agent lacks required capabilities: "
                    + ", ".join(sorted(missing))
                ),
            )

        active_count = self._registry.active_task_count(
            agent_id
        )

        if active_count >= agent.maximum_parallel_tasks:
            return CoordinationConflict(
                conflict_type=(
                    CoordinationConflictType
                    .RESOURCE_CONFLICT
                ),
                task_id=task.task_id,
                agent_id=agent_id,
                reason="Agent task capacity exceeded",
            )

        if not self._registry.task_dependencies_completed(
            task.task_id
        ):
            return CoordinationConflict(
                conflict_type=(
                    CoordinationConflictType
                    .DEPENDENCY_BLOCKED
                ),
                task_id=task.task_id,
                agent_id=agent_id,
                reason="Task dependencies are incomplete",
            )

        return None

    def _record_assignment(
        self,
        assignment: CoordinationAssignment,
    ) -> None:
        with self._lock:
            self._assignments.append(assignment)

    def _replace_last_assignment(
        self,
        assignment: CoordinationAssignment,
    ) -> None:
        with self._lock:
            if not self._assignments:
                raise CoordinationEngineError(
                    "No assignment history to replace"
                )

            self._assignments[-1] = assignment

    def _record_conflict(
        self,
        conflict: CoordinationConflict,
    ) -> None:
        with self._lock:
            self._conflicts.append(conflict)
