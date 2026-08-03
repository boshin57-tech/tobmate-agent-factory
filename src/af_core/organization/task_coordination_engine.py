from __future__ import annotations

from datetime import datetime, timezone

from .task_coordination_models import (
    CoordinatedTask,
    CoordinatedTaskStatus,
    CoordinationStatus,
    TaskAssignment,
    TaskCoordinationResult,
    TaskCoordinationWorkflow,
    TaskExecutionRecord,
    TaskFailurePolicy,
)
from .task_coordination_repository import (
    TaskCoordinationRepository,
)
from .dynamic_task_reassignment import (
    DynamicTaskReassignmentEngine,
)
from .task_runtime_profile_repository import (
    TaskRuntimeProfileRepository,
)
from .task_workload_balancer import (
    TaskWorkloadBalancingEngine,
)
from .task_workload_models import (
    TaskAgentRuntimeProfile,
    TaskAgentSelectionResult,
    TaskReassignmentRecord,
    TaskReassignmentRequest,
    TaskReassignmentResult,
)


class MultiAgentTaskCoordinationEngine:
    def __init__(
        self,
        repository: TaskCoordinationRepository | None = None,
        *,
        runtime_profiles: (
            TaskRuntimeProfileRepository
            | None
        ) = None,
        workload_balancer: (
            TaskWorkloadBalancingEngine
            | None
        ) = None,
        reassignment_engine: (
            DynamicTaskReassignmentEngine
            | None
        ) = None,
    ) -> None:
        self._repository = (
            repository
            or TaskCoordinationRepository()
        )

        self._runtime_profiles = (
            runtime_profiles
            or TaskRuntimeProfileRepository()
        )

        self._workload_balancer = (
            workload_balancer
            or TaskWorkloadBalancingEngine(
                agent_provider=(
                    self._runtime_profiles.all
                )
            )
        )

        self._reassignment_engine = (
            reassignment_engine
            or DynamicTaskReassignmentEngine(
                workload_balancer=(
                    self._workload_balancer
                ),
                agent_provider=(
                    self._runtime_profiles.all
                ),
            )
        )

    def register_runtime_profile(
        self,
        profile: TaskAgentRuntimeProfile,
    ) -> TaskAgentRuntimeProfile:
        return self._runtime_profiles.upsert(
            profile
        )

    def runtime_profile(
        self,
        agent_id: str,
    ) -> TaskAgentRuntimeProfile | None:
        return self._runtime_profiles.get(
            agent_id
        )

    def automatically_assign_task(
        self,
        *,
        workflow_id: str,
        task_id: str,
        assigned_by: str,
        excluded_agent_ids: (
            set[str] | None
        ) = None,
    ) -> tuple[
        TaskCoordinationWorkflow,
        TaskAgentSelectionResult,
    ]:
        workflow = self._require_workflow(
            workflow_id
        )

        task = self._require_task(
            workflow=workflow,
            task_id=task_id,
        )

        if task.status not in {
            CoordinatedTaskStatus.READY,
            CoordinatedTaskStatus
            .RETRY_PENDING,
        }:
            raise ValueError(
                "automatic assignment requires "
                "a READY or RETRY_PENDING task"
            )

        selection = (
            self._workload_balancer
            .select_agent(
                task=task,
                excluded_agent_ids=(
                    excluded_agent_ids
                ),
            )
        )

        if (
            not selection.fulfilled
            or selection.selected_agent_id
            is None
        ):
            return workflow, selection

        selected_score = next(
            score
            for score
            in selection.ranked_candidates
            if (
                score.agent_id
                == selection.selected_agent_id
            )
        )

        updated = self.assign_task(
            workflow_id=workflow_id,
            task_id=task_id,
            agent_id=(
                selection.selected_agent_id
            ),
            assigned_by=assigned_by,
            assignment_score=(
                selected_score.total_score
            ),
            matched_capabilities=set(
                selected_score
                .matched_capabilities
            ),
            matched_tasks=set(
                selected_score.matched_tasks
            ),
        )

        self._runtime_profiles.increment_task_count(
            selection.selected_agent_id
        )

        return updated, selection

    def reassign_task(
        self,
        request: TaskReassignmentRequest,
    ) -> TaskReassignmentResult:
        workflow = self._require_workflow(
            request.workflow_id
        )

        previous_task = self._require_task(
            workflow=workflow,
            task_id=request.task_id,
        )

        previous_agent_id = (
            previous_task.assigned_agent_id
        )

        updated, result = (
            self._reassignment_engine.execute(
                workflow=workflow,
                request=request,
            )
        )

        self._repository.replace(
            updated
        )

        if result.completed:
            if previous_agent_id is not None:
                previous_profile = (
                    self._runtime_profiles.get(
                        previous_agent_id
                    )
                )

                if previous_profile is not None:
                    self._runtime_profiles.decrement_task_count(
                        previous_agent_id
                    )

            if (
                result.replacement_agent_id
                is not None
            ):
                replacement_profile = (
                    self._runtime_profiles.get(
                        result.replacement_agent_id
                    )
                )

                if replacement_profile is not None:
                    self._runtime_profiles.increment_task_count(
                        result.replacement_agent_id
                    )

        return result

    def reassign_unhealthy_tasks(
        self,
        *,
        workflow_id: str,
        requested_by: str,
    ) -> list[
        TaskReassignmentResult
    ]:
        workflow = self._require_workflow(
            workflow_id
        )

        previous_assignments = {
            task.task_id:
                task.assigned_agent_id
            for task in workflow.tasks
        }

        updated, results = (
            self._reassignment_engine
            .reassign_unhealthy_tasks(
                workflow=workflow,
                requested_by=requested_by,
            )
        )

        self._repository.replace(
            updated
        )

        for result in results:
            if not result.completed:
                continue

            previous_agent_id = (
                previous_assignments.get(
                    result.task.task_id
                )
            )

            if previous_agent_id is not None:
                profile = (
                    self._runtime_profiles.get(
                        previous_agent_id
                    )
                )

                if profile is not None:
                    self._runtime_profiles.decrement_task_count(
                        previous_agent_id
                    )

            replacement_agent_id = (
                result.replacement_agent_id
            )

            if replacement_agent_id is not None:
                profile = (
                    self._runtime_profiles.get(
                        replacement_agent_id
                    )
                )

                if profile is not None:
                    self._runtime_profiles.increment_task_count(
                        replacement_agent_id
                    )

        return results

    def reassignment_history(
        self,
        *,
        workflow_id: str | None = None,
        task_id: str | None = None,
    ) -> tuple[
        TaskReassignmentRecord,
        ...
    ]:
        return self._reassignment_engine.history(
            workflow_id=workflow_id,
            task_id=task_id,
        )

    def create_workflow(
        self,
        workflow: TaskCoordinationWorkflow,
    ) -> TaskCoordinationWorkflow:
        if workflow.status is not CoordinationStatus.CREATED:
            raise ValueError(
                "new workflow must have CREATED status"
            )

        self._validate_unique_task_ids(
            workflow.tasks
        )

        return self._repository.save(
            workflow
        )

    def add_task(
        self,
        *,
        workflow_id: str,
        task: CoordinatedTask,
    ) -> TaskCoordinationWorkflow:
        workflow = self._require_workflow(
            workflow_id
        )

        if workflow.status not in {
            CoordinationStatus.CREATED,
            CoordinationStatus.READY,
        }:
            raise ValueError(
                "tasks cannot be added after workflow start"
            )

        if task.workflow_id != workflow_id:
            raise ValueError(
                "task workflow_id does not match workflow"
            )

        if any(
            existing.task_id == task.task_id
            for existing in workflow.tasks
        ):
            raise ValueError(
                "task already exists"
            )

        updated = workflow.model_copy(
            update={
                "tasks": [
                    *workflow.tasks,
                    task,
                ]
            }
        )

        return self._repository.replace(
            updated
        )

    def prepare_workflow(
        self,
        workflow_id: str,
    ) -> TaskCoordinationWorkflow:
        workflow = self._require_workflow(
            workflow_id
        )

        if workflow.status is not CoordinationStatus.CREATED:
            raise ValueError(
                "only CREATED workflows can be prepared"
            )

        if not workflow.tasks:
            raise ValueError(
                "workflow requires at least one task"
            )

        task_ids = {
            task.task_id
            for task in workflow.tasks
        }

        for task in workflow.tasks:
            unknown = task.dependencies - task_ids

            if unknown:
                raise ValueError(
                    "task contains unknown dependencies: "
                    + ", ".join(sorted(unknown))
                )

            if task.task_id in task.dependencies:
                raise ValueError(
                    "task cannot depend on itself"
                )

        prepared_tasks = [
            task.model_copy(
                update={
                    "status": (
                        CoordinatedTaskStatus.READY
                        if not task.dependencies
                        else CoordinatedTaskStatus.BLOCKED
                    ),
                    "blocked_reason": (
                        None
                        if not task.dependencies
                        else "waiting for dependencies"
                    ),
                }
            )
            for task in workflow.tasks
        ]

        prepared = workflow.model_copy(
            update={
                "status": CoordinationStatus.READY,
                "tasks": prepared_tasks,
            }
        )

        return self._repository.replace(
            prepared
        )

    def assign_task(
        self,
        *,
        workflow_id: str,
        task_id: str,
        agent_id: str,
        assigned_by: str,
        assignment_score: float = 0.0,
        matched_capabilities: set[str] | None = None,
        matched_tasks: set[str] | None = None,
    ) -> TaskCoordinationWorkflow:
        workflow = self._require_workflow(
            workflow_id
        )

        task = self._require_task(
            workflow=workflow,
            task_id=task_id,
        )

        if task.status not in {
            CoordinatedTaskStatus.READY,
            CoordinatedTaskStatus.ASSIGNED,
            CoordinatedTaskStatus.RETRY_PENDING,
        }:
            raise ValueError(
                "task cannot be assigned from current status"
            )

        agent_id = agent_id.strip()
        assigned_by = assigned_by.strip()

        if not agent_id:
            raise ValueError(
                "agent_id must not be empty"
            )

        if not assigned_by:
            raise ValueError(
                "assigned_by must not be empty"
            )

        assignment = TaskAssignment(
            workflow_id=workflow_id,
            task_id=task_id,
            agent_id=agent_id,
            assignment_score=assignment_score,
            matched_capabilities=(
                matched_capabilities or set()
            ),
            matched_tasks=(
                matched_tasks or set()
            ),
            assigned_by=assigned_by,
        )

        updated_task = task.model_copy(
            update={
                "assigned_agent_id": agent_id,
                "status":
                    CoordinatedTaskStatus.ASSIGNED,
                "assigned_at":
                    assignment.assigned_at,
                "blocked_reason": None,
            }
        )

        return self._replace_task(
            workflow=workflow,
            task=updated_task,
            assignments=[
                *workflow.assignments,
                assignment,
            ],
        )

    def start_workflow(
        self,
        workflow_id: str,
    ) -> TaskCoordinationWorkflow:
        workflow = self._require_workflow(
            workflow_id
        )

        if (
            workflow.status
            is not CoordinationStatus.READY
        ):
            raise ValueError(
                "only READY workflows can be started"
            )

        started = workflow.model_copy(
            update={
                "status":
                    CoordinationStatus.RUNNING,
                "started_at":
                    datetime.now(
                        timezone.utc
                    ),
            }
        )

        return self._repository.replace(
            started
        )

    def start_task(
        self,
        *,
        workflow_id: str,
        task_id: str,
    ) -> TaskCoordinationWorkflow:
        workflow = self._require_workflow(
            workflow_id
        )

        if (
            workflow.status
            is not CoordinationStatus.RUNNING
        ):
            raise ValueError(
                "workflow must be RUNNING"
            )

        task = self._require_task(
            workflow=workflow,
            task_id=task_id,
        )

        if (
            task.status
            is not CoordinatedTaskStatus.ASSIGNED
        ):
            raise ValueError(
                "only ASSIGNED tasks can be started"
            )

        if task.assigned_agent_id is None:
            raise ValueError(
                "task has no assigned Agent"
            )

        attempt_number = (
            task.attempt_count + 1
        )

        record = TaskExecutionRecord(
            workflow_id=workflow_id,
            task_id=task_id,
            agent_id=(
                task.assigned_agent_id
            ),
            attempt_number=(
                attempt_number
            ),
        )

        running_task = task.model_copy(
            update={
                "status":
                    CoordinatedTaskStatus.RUNNING,
                "attempt_count":
                    attempt_number,
                "started_at":
                    record.started_at,
                "completed_at":
                    None,
                "error_message":
                    None,
            }
        )

        return self._replace_task(
            workflow=workflow,
            task=running_task,
            execution_records=[
                *workflow.execution_records,
                record,
            ],
        )

    def complete_task(
        self,
        *,
        workflow_id: str,
        task_id: str,
        result: (
            dict[str, object] | None
        ) = None,
    ) -> TaskCoordinationWorkflow:
        workflow = self._require_workflow(
            workflow_id
        )

        task = self._require_task(
            workflow=workflow,
            task_id=task_id,
        )

        if (
            task.status
            is not CoordinatedTaskStatus.RUNNING
        ):
            raise ValueError(
                "only RUNNING tasks can be completed"
            )

        completed_at = datetime.now(
            timezone.utc
        )

        task_result = result or {}

        completed_task = task.model_copy(
            update={
                "status":
                    CoordinatedTaskStatus.COMPLETED,
                "result":
                    task_result,
                "completed_at":
                    completed_at,
                "error_message":
                    None,
                "blocked_reason":
                    None,
            }
        )

        records = self._complete_execution_record(
            workflow=workflow,
            task=task,
            successful=True,
            result=task_result,
            error_message=None,
            completed_at=completed_at,
        )

        updated = self._replace_task(
            workflow=workflow,
            task=completed_task,
            execution_records=records,
        )

        updated = self._refresh_task_states(
            updated
        )

        if task.assigned_agent_id is not None:
            profile = self._runtime_profiles.get(
                task.assigned_agent_id
            )

            if profile is not None:
                self._runtime_profiles.decrement_task_count(
                    task.assigned_agent_id
                )

        return self._evaluate_workflow_status(
            updated
        )

    def fail_task(
        self,
        *,
        workflow_id: str,
        task_id: str,
        error_message: str,
    ) -> TaskCoordinationWorkflow:
        workflow = self._require_workflow(
            workflow_id
        )

        task = self._require_task(
            workflow=workflow,
            task_id=task_id,
        )

        if (
            task.status
            is not CoordinatedTaskStatus.RUNNING
        ):
            raise ValueError(
                "only RUNNING tasks can fail"
            )

        normalized_error = (
            error_message.strip()
        )

        if not normalized_error:
            raise ValueError(
                "error_message must not be empty"
            )

        completed_at = datetime.now(
            timezone.utc
        )

        can_retry = (
            task.failure_policy
            is TaskFailurePolicy.RETRY
            and task.attempt_count
            < task.maximum_attempts
        )

        new_status = (
            CoordinatedTaskStatus.RETRY_PENDING
            if can_retry
            else CoordinatedTaskStatus.FAILED
        )

        failed_task = task.model_copy(
            update={
                "status":
                    new_status,
                "error_message":
                    normalized_error,
                "completed_at": (
                    None
                    if can_retry
                    else completed_at
                ),
            }
        )

        records = self._complete_execution_record(
            workflow=workflow,
            task=task,
            successful=False,
            result={},
            error_message=normalized_error,
            completed_at=completed_at,
        )

        updated = self._replace_task(
            workflow=workflow,
            task=failed_task,
            execution_records=records,
        )

        updated = self._refresh_task_states(
            updated
        )

        if task.assigned_agent_id is not None:
            profile = self._runtime_profiles.get(
                task.assigned_agent_id
            )

            if profile is not None:
                self._runtime_profiles.decrement_task_count(
                    task.assigned_agent_id
                )

        return self._evaluate_workflow_status(
            updated
        )

    def cancel_workflow(
        self,
        workflow_id: str,
    ) -> TaskCoordinationWorkflow:
        workflow = self._require_workflow(
            workflow_id
        )

        if workflow.status in {
            CoordinationStatus.COMPLETED,
            CoordinationStatus.FAILED,
            CoordinationStatus.CANCELLED,
        }:
            raise ValueError(
                "workflow is already finalized"
            )

        tasks = [
            (
                task.model_copy(
                    update={
                        "status":
                            CoordinatedTaskStatus
                            .CANCELLED,
                        "blocked_reason":
                            "workflow cancelled",
                    }
                )
                if task.status
                not in {
                    CoordinatedTaskStatus
                    .COMPLETED,
                    CoordinatedTaskStatus
                    .FAILED,
                    CoordinatedTaskStatus
                    .CANCELLED,
                    CoordinatedTaskStatus
                    .SKIPPED,
                }
                else task
            )
            for task in workflow.tasks
        ]

        cancelled = workflow.model_copy(
            update={
                "status":
                    CoordinationStatus.CANCELLED,
                "tasks":
                    tasks,
                "completed_at":
                    datetime.now(
                        timezone.utc
                    ),
            }
        )

        return self._repository.replace(
            cancelled
        )

    def coordination_result(
        self,
        workflow_id: str,
    ) -> TaskCoordinationResult:
        workflow = self._require_workflow(
            workflow_id
        )

        return TaskCoordinationResult(
            workflow=workflow,
            ready_task_ids=(
                self._task_ids_by_status(
                    workflow,
                    CoordinatedTaskStatus.READY,
                )
            ),
            blocked_task_ids=(
                self._task_ids_by_status(
                    workflow,
                    CoordinatedTaskStatus.BLOCKED,
                )
            ),
            running_task_ids=(
                self._task_ids_by_status(
                    workflow,
                    CoordinatedTaskStatus.RUNNING,
                )
            ),
            completed_task_ids=(
                self._task_ids_by_status(
                    workflow,
                    CoordinatedTaskStatus.COMPLETED,
                )
            ),
            failed_task_ids=(
                self._task_ids_by_status(
                    workflow,
                    CoordinatedTaskStatus.FAILED,
                )
            ),
        )

    def get_workflow(
        self,
        workflow_id: str,
    ) -> TaskCoordinationWorkflow | None:
        return self._repository.get(
            workflow_id
        )

    def workflows_for_workspace(
        self,
        workspace_id: str,
    ) -> tuple[
        TaskCoordinationWorkflow,
        ...
    ]:
        return self._repository.by_workspace(
            workspace_id
        )

    def workflows_for_team(
        self,
        team_id: str,
    ) -> tuple[
        TaskCoordinationWorkflow,
        ...
    ]:
        return self._repository.by_team(
            team_id
        )

    def _refresh_task_states(
        self,
        workflow: TaskCoordinationWorkflow,
    ) -> TaskCoordinationWorkflow:
        completed_ids = {
            task.task_id
            for task in workflow.tasks
            if (
                task.status
                is CoordinatedTaskStatus
                .COMPLETED
            )
        }

        failed_ids = {
            task.task_id
            for task in workflow.tasks
            if (
                task.status
                is CoordinatedTaskStatus
                .FAILED
            )
        }

        refreshed: list[
            CoordinatedTask
        ] = []

        for task in workflow.tasks:
            if (
                task.status
                is not CoordinatedTaskStatus
                .BLOCKED
            ):
                refreshed.append(
                    task
                )
                continue

            failed_dependencies = (
                task.dependencies
                .intersection(
                    failed_ids
                )
            )

            if failed_dependencies:
                refreshed.append(
                    task.model_copy(
                        update={
                            "blocked_reason": (
                                "dependency failed: "
                                + ", ".join(
                                    sorted(
                                        failed_dependencies
                                    )
                                )
                            )
                        }
                    )
                )
                continue

            if (
                task.dependencies
                .issubset(
                    completed_ids
                )
            ):
                refreshed.append(
                    task.model_copy(
                        update={
                            "status":
                                CoordinatedTaskStatus
                                .READY,
                            "blocked_reason":
                                None,
                        }
                    )
                )
                continue

            refreshed.append(
                task.model_copy(
                    update={
                        "blocked_reason":
                            "waiting for dependencies",
                    }
                )
            )

        refreshed_workflow = (
            workflow.model_copy(
                update={
                    "tasks":
                        refreshed,
                }
            )
        )

        return self._repository.replace(
            refreshed_workflow
        )

    def _evaluate_workflow_status(
        self,
        workflow: TaskCoordinationWorkflow,
    ) -> TaskCoordinationWorkflow:
        if (
            workflow.status
            is CoordinationStatus.CANCELLED
        ):
            return workflow

        if workflow.tasks and all(
            task.status
            in {
                CoordinatedTaskStatus
                .COMPLETED,
                CoordinatedTaskStatus
                .SKIPPED,
            }
            for task in workflow.tasks
        ):
            completed = workflow.model_copy(
                update={
                    "status":
                        CoordinationStatus
                        .COMPLETED,
                    "completed_at":
                        datetime.now(
                            timezone.utc
                        ),
                }
            )

            return self._repository.replace(
                completed
            )

        stop_failures = [
            task
            for task in workflow.tasks
            if (
                task.status
                is CoordinatedTaskStatus
                .FAILED
                and task.failure_policy
                in {
                    TaskFailurePolicy
                    .STOP_WORKFLOW,
                    TaskFailurePolicy
                    .ESCALATE,
                }
            )
        ]

        if stop_failures:
            failed = workflow.model_copy(
                update={
                    "status":
                        CoordinationStatus.FAILED,
                    "completed_at":
                        datetime.now(
                            timezone.utc
                        ),
                }
            )

            return self._repository.replace(
                failed
            )

        failed_task_ids = {
            task.task_id
            for task in workflow.tasks
            if (
                task.status
                is CoordinatedTaskStatus
                .FAILED
            )
        }

        unresolved_blocked = [
            task
            for task in workflow.tasks
            if (
                task.status
                is CoordinatedTaskStatus
                .BLOCKED
                and bool(
                    task.dependencies
                    .intersection(
                        failed_task_ids
                    )
                )
            )
        ]

        if unresolved_blocked:
            blocked = workflow.model_copy(
                update={
                    "status":
                        CoordinationStatus.BLOCKED,
                }
            )

            return self._repository.replace(
                blocked
            )

        if workflow.status in {
            CoordinationStatus.READY,
            CoordinationStatus.RUNNING,
            CoordinationStatus.BLOCKED,
        }:
            running = workflow.model_copy(
                update={
                    "status":
                        CoordinationStatus.RUNNING,
                }
            )

            return self._repository.replace(
                running
            )

        return workflow

    def _complete_execution_record(
        self,
        *,
        workflow: TaskCoordinationWorkflow,
        task: CoordinatedTask,
        successful: bool,
        result: dict[str, object],
        error_message: str | None,
        completed_at: datetime,
    ) -> list[
        TaskExecutionRecord
    ]:
        updated_records: list[
            TaskExecutionRecord
        ] = []

        record_found = False

        for record in (
            workflow.execution_records
        ):
            if (
                record.task_id
                == task.task_id
                and record.attempt_number
                == task.attempt_count
                and record.completed_at
                is None
            ):
                updated_records.append(
                    record.model_copy(
                        update={
                            "completed_at":
                                completed_at,
                            "successful":
                                successful,
                            "result":
                                result,
                            "error_message":
                                error_message,
                        }
                    )
                )

                record_found = True
            else:
                updated_records.append(
                    record
                )

        if not record_found:
            raise ValueError(
                "active execution record not found"
            )

        return updated_records

    def _replace_task(
        self,
        *,
        workflow: TaskCoordinationWorkflow,
        task: CoordinatedTask,
        assignments: (
            list[TaskAssignment]
            | None
        ) = None,
        execution_records: (
            list[TaskExecutionRecord]
            | None
        ) = None,
    ) -> TaskCoordinationWorkflow:
        tasks = [
            (
                task
                if existing.task_id
                == task.task_id
                else existing
            )
            for existing in workflow.tasks
        ]

        updated = workflow.model_copy(
            update={
                "tasks":
                    tasks,
                "assignments": (
                    assignments
                    if assignments
                    is not None
                    else workflow.assignments
                ),
                "execution_records": (
                    execution_records
                    if execution_records
                    is not None
                    else workflow
                    .execution_records
                ),
            }
        )

        return self._repository.replace(
            updated
        )

    def _require_workflow(
        self,
        workflow_id: str,
    ) -> TaskCoordinationWorkflow:
        workflow = (
            self._repository.get(
                workflow_id
            )
        )

        if workflow is None:
            raise ValueError(
                "coordination workflow not found"
            )

        return workflow

    @staticmethod
    def _require_task(
        *,
        workflow: TaskCoordinationWorkflow,
        task_id: str,
    ) -> CoordinatedTask:
        for task in workflow.tasks:
            if task.task_id == task_id:
                return task

        raise ValueError(
            "coordinated task not found"
        )

    @staticmethod
    def _validate_unique_task_ids(
        tasks: list[
            CoordinatedTask
        ],
    ) -> None:
        task_ids = [
            task.task_id
            for task in tasks
        ]

        if (
            len(task_ids)
            != len(set(task_ids))
        ):
            raise ValueError(
                "workflow contains duplicate task IDs"
            )

    @staticmethod
    def _task_ids_by_status(
        workflow: TaskCoordinationWorkflow,
        status: CoordinatedTaskStatus,
    ) -> list[str]:
        return [
            task.task_id
            for task in workflow.tasks
            if task.status is status
        ]

    @property
    def workflow_count(self) -> int:
        return self._repository.count
