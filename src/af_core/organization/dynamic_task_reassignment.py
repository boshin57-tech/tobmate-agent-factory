from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone

from .task_coordination_models import (
    CoordinatedTask,
    CoordinatedTaskStatus,
    TaskAssignment,
    TaskCoordinationWorkflow,
)
from .task_workload_balancer import (
    TaskWorkloadBalancingEngine,
)
from .task_workload_models import (
    TaskAgentAvailability,
    TaskAgentRuntimeProfile,
    TaskReassignmentAssessment,
    TaskReassignmentDecision,
    TaskReassignmentReason,
    TaskReassignmentRecord,
    TaskReassignmentRequest,
    TaskReassignmentResult,
)


class DynamicTaskReassignmentEngine:
    """
    Evaluates and executes coordinated task reassignment.

    Reassignment is fail-safe:
    - The current Agent is excluded from replacement selection.
    - Offline, overloaded, degraded, or failed Agents can be replaced.
    - A replacement assignment is created before completion is reported.
    - If no eligible replacement exists, the task becomes BLOCKED.
    - Every reassignment attempt produces an immutable-style record.
    """

    def __init__(
        self,
        *,
        workload_balancer: (
            TaskWorkloadBalancingEngine
        ),
        agent_provider: Callable[
            [],
            Iterable[TaskAgentRuntimeProfile],
        ],
    ) -> None:
        self._workload_balancer = (
            workload_balancer
        )

        self._agent_provider = (
            agent_provider
        )

        self._history: list[
            TaskReassignmentRecord
        ] = []

    def assess(
        self,
        *,
        workflow: TaskCoordinationWorkflow,
        task: CoordinatedTask,
        reason: (
            TaskReassignmentReason
            | None
        ) = None,
        force: bool = False,
    ) -> TaskReassignmentAssessment:
        current_agent_id = (
            task.assigned_agent_id
        )

        reasons: list[
            TaskReassignmentReason
        ] = []

        details: list[str] = []

        profile = self._profile(
            current_agent_id
        )

        if current_agent_id is None:
            reasons.append(
                TaskReassignmentReason
                .CAPABILITY_MISMATCH
            )

            details.append(
                "task has no assigned Agent"
            )

        elif profile is None:
            reasons.append(
                TaskReassignmentReason
                .AGENT_OFFLINE
            )

            details.append(
                "assigned Agent runtime profile "
                "is unavailable"
            )

        else:
            if (
                profile.availability
                is TaskAgentAvailability.OFFLINE
            ):
                reasons.append(
                    TaskReassignmentReason
                    .AGENT_OFFLINE
                )

                details.append(
                    "assigned Agent is offline"
                )

            if (
                profile.availability
                is TaskAgentAvailability
                .OVERLOADED
                or profile.workload_ratio
                >= 0.90
                or not profile.has_capacity
            ):
                reasons.append(
                    TaskReassignmentReason
                    .AGENT_OVERLOADED
                )

                details.append(
                    "assigned Agent exceeds "
                    "workload or capacity policy"
                )

            if (
                profile.availability
                is TaskAgentAvailability
                .DEGRADED
            ):
                reasons.append(
                    TaskReassignmentReason
                    .AGENT_DEGRADED
                )

                details.append(
                    "assigned Agent is degraded"
                )

            if (
                profile.consecutive_failures
                >= 3
            ):
                reasons.append(
                    TaskReassignmentReason
                    .TASK_FAILURE
                )

                details.append(
                    "assigned Agent has repeated failures"
                )

            if (
                not task.required_capabilities
                .issubset(
                    profile.capabilities
                )
            ):
                reasons.append(
                    TaskReassignmentReason
                    .CAPABILITY_MISMATCH
                )

                details.append(
                    "assigned Agent no longer satisfies "
                    "required capabilities"
                )

            if (
                not task.required_tasks
                .issubset(
                    profile.supported_tasks
                )
            ):
                reasons.append(
                    TaskReassignmentReason
                    .CAPABILITY_MISMATCH
                )

                details.append(
                    "assigned Agent no longer supports "
                    "required task types"
                )

        if reason is not None:
            reasons.append(reason)

            details.append(
                f"explicit reassignment reason: "
                f"{reason.value}"
            )

        reasons = self._unique_reasons(
            reasons
        )

        replacement_required = (
            force
            or bool(reasons)
        )

        decision = (
            TaskReassignmentDecision.REASSIGN
            if replacement_required
            else TaskReassignmentDecision
            .NOT_REQUIRED
        )

        return TaskReassignmentAssessment(
            workflow_id=(
                workflow.workflow_id
            ),
            task_id=task.task_id,
            current_agent_id=(
                current_agent_id
            ),
            decision=decision,
            reasons=reasons,
            details=details,
            replacement_required=(
                replacement_required
            ),
        )

    def execute(
        self,
        *,
        workflow: TaskCoordinationWorkflow,
        request: TaskReassignmentRequest,
    ) -> tuple[
        TaskCoordinationWorkflow,
        TaskReassignmentResult,
    ]:
        task = self._require_task(
            workflow=workflow,
            task_id=request.task_id,
        )

        assessment = self.assess(
            workflow=workflow,
            task=task,
            reason=request.reason,
            force=request.force,
        )

        previous_agent_id = (
            task.assigned_agent_id
        )

        if (
            assessment.decision
            is TaskReassignmentDecision
            .NOT_REQUIRED
        ):
            record = TaskReassignmentRecord(
                request_id=request.request_id,
                workflow_id=(
                    workflow.workflow_id
                ),
                task_id=task.task_id,
                previous_agent_id=(
                    previous_agent_id
                ),
                replacement_agent_id=None,
                reason=request.reason,
                decision=(
                    TaskReassignmentDecision
                    .NOT_REQUIRED
                ),
                details=[
                    "task reassignment was not required"
                ],
            )

            self._history.append(record)

            return (
                workflow,
                TaskReassignmentResult(
                    assessment=assessment,
                    record=record,
                    task=task,
                    completed=False,
                    previous_agent_id=(
                        previous_agent_id
                    ),
                    replacement_agent_id=None,
                    reasons=[
                        "reassignment not required"
                    ],
                ),
            )

        excluded = set(
            request.excluded_agent_ids
        )

        if previous_agent_id is not None:
            excluded.add(
                previous_agent_id
            )

        selection = (
            self._workload_balancer
            .select_agent(
                task=task,
                excluded_agent_ids=(
                    excluded
                ),
            )
        )

        if (
            not selection.fulfilled
            or selection.selected_agent_id
            is None
        ):
            blocked_task = task.model_copy(
                update={
                    "status":
                        CoordinatedTaskStatus
                        .BLOCKED,
                    "blocked_reason": (
                        "no eligible replacement "
                        "Agent available"
                    ),
                    "error_message": (
                        task.error_message
                        or "task reassignment blocked"
                    ),
                }
            )

            updated_workflow = (
                self._replace_task(
                    workflow=workflow,
                    task=blocked_task,
                )
            )

            decision = (
                TaskReassignmentDecision
                .ESCALATE
                if (
                    request.reason
                    is TaskReassignmentReason
                    .TASK_FAILURE
                )
                else TaskReassignmentDecision
                .BLOCKED
            )

            blocked_assessment = (
                assessment.model_copy(
                    update={
                        "decision":
                            decision,
                        "details": [
                            *assessment.details,
                            (
                                "no eligible replacement "
                                "Agent was found"
                            ),
                        ],
                    }
                )
            )

            record = TaskReassignmentRecord(
                request_id=request.request_id,
                workflow_id=(
                    workflow.workflow_id
                ),
                task_id=task.task_id,
                previous_agent_id=(
                    previous_agent_id
                ),
                replacement_agent_id=None,
                reason=request.reason,
                decision=decision,
                previous_assignment_released=False,
                replacement_assignment_created=False,
                replacement_score=0.0,
                details=[
                    "replacement selection failed",
                    *selection.reasons,
                ],
            )

            self._history.append(record)

            return (
                updated_workflow,
                TaskReassignmentResult(
                    assessment=(
                        blocked_assessment
                    ),
                    record=record,
                    task=blocked_task,
                    completed=False,
                    previous_agent_id=(
                        previous_agent_id
                    ),
                    replacement_agent_id=None,
                    reasons=[
                        (
                            "task reassignment blocked "
                            "because no replacement "
                            "Agent is available"
                        )
                    ],
                ),
            )

        replacement_agent_id = (
            selection.selected_agent_id
        )

        selected_score = next(
            score
            for score
            in selection.ranked_candidates
            if (
                score.agent_id
                == replacement_agent_id
            )
        )

        replacement_assignment = (
            TaskAssignment(
                workflow_id=(
                    workflow.workflow_id
                ),
                task_id=task.task_id,
                agent_id=(
                    replacement_agent_id
                ),
                assignment_score=(
                    selected_score.total_score
                ),
                matched_capabilities=set(
                    selected_score
                    .matched_capabilities
                ),
                matched_tasks=set(
                    selected_score
                    .matched_tasks
                ),
                assigned_by=(
                    request.requested_by
                ),
                metadata={
                    "reassignment_request_id":
                        request.request_id,
                    "reassignment_reason":
                        request.reason.value,
                    "previous_agent_id":
                        previous_agent_id or "",
                },
            )
        )

        replacement_task = task.model_copy(
            update={
                "assigned_agent_id":
                    replacement_agent_id,
                "status":
                    CoordinatedTaskStatus
                    .ASSIGNED,
                "assigned_at":
                    replacement_assignment
                    .assigned_at,
                "started_at":
                    None,
                "completed_at":
                    None,
                "blocked_reason":
                    None,
                "error_message":
                    None,
            }
        )

        assignments = [
            assignment
            for assignment
            in workflow.assignments
            if (
                assignment.task_id
                != task.task_id
            )
        ]

        assignments.append(
            replacement_assignment
        )

        updated_workflow = (
            self._replace_task(
                workflow=workflow,
                task=replacement_task,
                assignments=assignments,
            )
        )

        record = TaskReassignmentRecord(
            request_id=request.request_id,
            workflow_id=(
                workflow.workflow_id
            ),
            task_id=task.task_id,
            previous_agent_id=(
                previous_agent_id
            ),
            replacement_agent_id=(
                replacement_agent_id
            ),
            reason=request.reason,
            decision=(
                TaskReassignmentDecision
                .REASSIGN
            ),
            previous_assignment_released=(
                previous_agent_id
                is not None
            ),
            replacement_assignment_created=True,
            replacement_score=(
                selected_score.total_score
            ),
            details=[
                (
                    "replacement Agent selected "
                    "by workload balancing policy"
                ),
                (
                    f"replacement Agent: "
                    f"{replacement_agent_id}"
                ),
            ],
        )

        self._history.append(record)

        return (
            updated_workflow,
            TaskReassignmentResult(
                assessment=assessment,
                record=record,
                task=replacement_task,
                completed=True,
                previous_agent_id=(
                    previous_agent_id
                ),
                replacement_agent_id=(
                    replacement_agent_id
                ),
                reasons=[
                    (
                        "task successfully reassigned "
                        "to an eligible replacement Agent"
                    )
                ],
            ),
        )

    def reassign_unhealthy_tasks(
        self,
        *,
        workflow: TaskCoordinationWorkflow,
        requested_by: str,
    ) -> tuple[
        TaskCoordinationWorkflow,
        list[TaskReassignmentResult],
    ]:
        current_workflow = workflow

        results: list[
            TaskReassignmentResult
        ] = []

        candidate_task_ids = [
            task.task_id
            for task in workflow.tasks
            if (
                task.assigned_agent_id
                is not None
                and task.status
                in {
                    CoordinatedTaskStatus
                    .ASSIGNED,
                    CoordinatedTaskStatus
                    .RUNNING,
                    CoordinatedTaskStatus
                    .RETRY_PENDING,
                }
            )
        ]

        for task_id in candidate_task_ids:
            current_task = self._require_task(
                workflow=current_workflow,
                task_id=task_id,
            )

            assessment = self.assess(
                workflow=current_workflow,
                task=current_task,
            )

            if (
                not assessment
                .replacement_required
            ):
                continue

            primary_reason = (
                assessment.reasons[0]
                if assessment.reasons
                else TaskReassignmentReason
                .MANUAL_REQUEST
            )

            current_workflow, result = (
                self.execute(
                    workflow=current_workflow,
                    request=(
                        TaskReassignmentRequest(
                            workflow_id=(
                                current_workflow
                                .workflow_id
                            ),
                            task_id=task_id,
                            requested_by=(
                                requested_by
                            ),
                            reason=(
                                primary_reason
                            ),
                            force=True,
                        )
                    ),
                )
            )

            results.append(result)

        return (
            current_workflow,
            results,
        )

    def history(
        self,
        *,
        workflow_id: str | None = None,
        task_id: str | None = None,
    ) -> tuple[
        TaskReassignmentRecord,
        ...
    ]:
        records = self._history

        if workflow_id is not None:
            records = [
                record
                for record in records
                if (
                    record.workflow_id
                    == workflow_id
                )
            ]

        if task_id is not None:
            records = [
                record
                for record in records
                if record.task_id == task_id
            ]

        return tuple(records)

    def _profile(
        self,
        agent_id: str | None,
    ) -> TaskAgentRuntimeProfile | None:
        if agent_id is None:
            return None

        for profile in (
            self._agent_provider()
        ):
            if profile.agent_id == agent_id:
                return profile

        return None

    @staticmethod
    def _replace_task(
        *,
        workflow: TaskCoordinationWorkflow,
        task: CoordinatedTask,
        assignments: (
            list[TaskAssignment]
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

        return workflow.model_copy(
            update={
                "tasks": tasks,
                "assignments": (
                    assignments
                    if assignments is not None
                    else workflow.assignments
                ),
            }
        )

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
    def _unique_reasons(
        reasons: list[
            TaskReassignmentReason
        ],
    ) -> list[
        TaskReassignmentReason
    ]:
        seen: set[
            TaskReassignmentReason
        ] = set()

        ordered: list[
            TaskReassignmentReason
        ] = []

        for reason in reasons:
            if reason in seen:
                continue

            seen.add(reason)
            ordered.append(reason)

        return ordered

    @property
    def history_count(self) -> int:
        return len(self._history)
