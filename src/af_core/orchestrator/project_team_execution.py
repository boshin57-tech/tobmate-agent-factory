"""Team-aware autonomous project task execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from af_core.orchestrator.project_execution_models import (
    ProjectRunStatus,
    ProjectTaskRuntimeState,
    ProjectTaskStatus,
)
from af_core.orchestrator.project_execution_runtime import (
    AutonomousProjectExecutionRuntime,
    ProjectTaskExecutionResult,
    ProjectTaskExecutor,
)
from af_core.orchestrator.project_team_coordination import (
    ProjectConflictKind,
    ProjectHandoffStatus,
    ProjectTeamAssignment,
    ProjectTeamCoordinationError,
    ProjectTeamCoordinationRegistry,
    ProjectTeamRole,
)


class ProjectTeamExecutionError(
    ProjectTeamCoordinationError
):
    """Raised when team-aware execution is invalid."""


@dataclass(frozen=True, slots=True)
class ProjectTeamExecutionCycle:
    """Result of one team-controlled task execution."""

    run_id: str
    task_id: str
    team_id: str
    status: ProjectTaskStatus
    succeeded: bool
    output_reference: str | None = None
    error: str = ""
    handoff_ids: tuple[str, ...] = ()


class ProjectTeamExecutionCoordinator:
    """Enforce ownership, capability and coordination gates."""

    def __init__(
        self,
        runtime: AutonomousProjectExecutionRuntime,
        registry: ProjectTeamCoordinationRegistry,
    ) -> None:
        self._runtime = runtime
        self._registry = registry

    @property
    def runtime(
        self,
    ) -> AutonomousProjectExecutionRuntime:
        return self._runtime

    @property
    def registry(
        self,
    ) -> ProjectTeamCoordinationRegistry:
        return self._registry

    def assign_task(
        self,
        *,
        run_id: str,
        task_id: str,
        team_id: str,
        capabilities: Iterable[str] = (),
        role: ProjectTeamRole = ProjectTeamRole.OWNER,
        now: float,
    ) -> ProjectTeamAssignment:
        """Assign a capable team to one registered task."""

        snapshot = self._runtime.repository.get(run_id)

        try:
            task = snapshot.state.tasks[task_id]
        except KeyError as exc:
            raise ProjectTeamExecutionError(
                f"project task not found: {task_id}"
            ) from exc

        provided = frozenset(
            str(item)
            for item in capabilities
        )
        required = self._required_capabilities(task)
        missing = required - provided

        if missing:
            self._registry.record_conflict(
                run_id=run_id,
                task_id=task_id,
                kind=ProjectConflictKind.AUTHORITY,
                teams=(team_id,),
                reason=(
                    "team lacks required capabilities: "
                    + ", ".join(sorted(missing))
                ),
                now=now,
            )

            raise ProjectTeamExecutionError(
                "team lacks required task capabilities: "
                + ", ".join(sorted(missing))
            )

        return self._registry.assign(
            run_id=run_id,
            task_id=task_id,
            team_id=team_id,
            role=role,
            capabilities=provided,
        )

    def eligible_tasks(
        self,
        run_id: str,
    ) -> tuple[ProjectTaskRuntimeState, ...]:
        """Return ready tasks permitted to execute."""

        state = self._runtime.repository.get(
            run_id
        ).state

        if state.status is not ProjectRunStatus.RUNNING:
            return ()

        ready = self._runtime.ready_tasks(run_id)
        coordination = self._registry.snapshot(run_id)

        assignments = {
            item.task_id: item
            for item in coordination.assignments
        }

        blocked = {
            item.task_id
            for item in coordination.blockers
            if not item.resolved
        }

        conflicted = {
            item.task_id
            for item in coordination.conflicts
            if not item.resolved
        }

        pending_handoffs = {
            item.target_task_id
            for item in coordination.handoffs
            if item.status
            is not ProjectHandoffStatus.COMPLETED
        }

        eligible: list[
            ProjectTaskRuntimeState
        ] = []

        for task in ready:
            assignment = assignments.get(
                task.task_id
            )

            if assignment is None:
                continue

            if task.task_id in blocked:
                continue

            if task.task_id in conflicted:
                continue

            if task.task_id in pending_handoffs:
                continue

            required = self._required_capabilities(
                task
            )

            if not required.issubset(
                assignment.capabilities
            ):
                continue

            if (
                task.assigned_team_id is not None
                and task.assigned_team_id
                != assignment.team_id
            ):
                continue

            eligible.append(task)

        return tuple(eligible)

    @staticmethod
    def _required_capabilities(
        task: ProjectTaskRuntimeState,
    ) -> frozenset[str]:
        return frozenset(
            str(item)
            for item in task.metadata.get(
                "required_capabilities",
                (),
            )
        )

    def execute_next(
        self,
        run_id: str,
        executor: ProjectTaskExecutor,
        *,
        now: float,
    ) -> ProjectTeamExecutionCycle | None:
        """Execute the next team-authorized ready task."""

        current = self._runtime.repository.get(run_id)

        if current.state.status is not ProjectRunStatus.RUNNING:
            raise ProjectTeamExecutionError(
                "project run is not running"
            )

        self._runtime.refresh_ready_tasks(
            run_id,
            now=now,
        )

        eligible = self.eligible_tasks(run_id)

        if not eligible:
            return None

        task = eligible[0]

        assignment = self._registry.assignment(
            run_id,
            task.task_id,
        )

        current_task = self._runtime.repository.get(
            run_id
        ).state.tasks[task.task_id]

        if current_task.assigned_team_id is None:
            assigned = self._runtime.assign_task(
                run_id,
                task.task_id,
                now=now,
                team_id=assignment.team_id,
            )

            current_task = assigned.state.tasks[
                task.task_id
            ]

        elif (
            current_task.assigned_team_id
            != assignment.team_id
        ):
            conflict = self._registry.record_conflict(
                run_id=run_id,
                task_id=task.task_id,
                kind=ProjectConflictKind.TASK_OWNERSHIP,
                teams=(
                    current_task.assigned_team_id,
                    assignment.team_id,
                ),
                reason=(
                    "runtime team differs from "
                    "coordination ownership"
                ),
                now=now,
            )

            raise ProjectTeamExecutionError(
                "team ownership conflict: "
                f"{conflict.conflict_id}"
            )

        started = self._runtime.begin_task(
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

            self._runtime.fail_task(
                run_id,
                task.task_id,
                now=now,
                error=error,
            )

            return ProjectTeamExecutionCycle(
                run_id=run_id,
                task_id=task.task_id,
                team_id=assignment.team_id,
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

            self._runtime.fail_task(
                run_id,
                task.task_id,
                now=now,
                error=error,
            )

            return ProjectTeamExecutionCycle(
                run_id=run_id,
                task_id=task.task_id,
                team_id=assignment.team_id,
                status=ProjectTaskStatus.FAILED,
                succeeded=False,
                error=error,
            )

        if not result.succeeded:
            error = result.error or (
                "task execution failed"
            )

            self._runtime.fail_task(
                run_id,
                task.task_id,
                now=now,
                error=error,
            )

            return ProjectTeamExecutionCycle(
                run_id=run_id,
                task_id=task.task_id,
                team_id=assignment.team_id,
                status=ProjectTaskStatus.FAILED,
                succeeded=False,
                error=error,
            )

        self._runtime.complete_task(
            run_id,
            task.task_id,
            now=now,
            output_reference=result.output_reference,
            metadata=result.metadata,
        )

        self._runtime.refresh_ready_tasks(
            run_id,
            now=now,
        )

        handoff_ids = self._create_handoffs(
            run_id=run_id,
            source_task_id=task.task_id,
            artifact_reference=result.output_reference,
            now=now,
        )

        return ProjectTeamExecutionCycle(
            run_id=run_id,
            task_id=task.task_id,
            team_id=assignment.team_id,
            status=ProjectTaskStatus.SUCCEEDED,
            succeeded=True,
            output_reference=result.output_reference,
            handoff_ids=handoff_ids,
        )

    def _create_handoffs(
        self,
        *,
        run_id: str,
        source_task_id: str,
        artifact_reference: str | None,
        now: float,
    ) -> tuple[str, ...]:
        """Create required cross-team downstream handoffs."""

        if artifact_reference is None:
            return ()

        state = self._runtime.repository.get(
            run_id
        ).state

        source_assignment = self._registry.assignment(
            run_id,
            source_task_id,
        )

        existing = {
            (
                handoff.source_task_id,
                handoff.target_task_id,
                handoff.artifact_reference,
            )
            for handoff in self._registry.snapshot(
                run_id
            ).handoffs
        }

        created: list[str] = []

        for target_id in sorted(state.tasks):
            target = state.tasks[target_id]

            if source_task_id not in self._dependencies(
                target
            ):
                continue

            try:
                target_assignment = (
                    self._registry.assignment(
                        run_id,
                        target_id,
                    )
                )
            except ProjectTeamCoordinationError:
                continue

            if (
                source_assignment.team_id
                == target_assignment.team_id
            ):
                continue

            identity = (
                source_task_id,
                target_id,
                artifact_reference,
            )

            if identity in existing:
                continue

            handoff = self._registry.create_handoff(
                run_id=run_id,
                source_task_id=source_task_id,
                target_task_id=target_id,
                artifact_reference=artifact_reference,
                now=now,
            )

            created.append(handoff.handoff_id)

        return tuple(created)

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
