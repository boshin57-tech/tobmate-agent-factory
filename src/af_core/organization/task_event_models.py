from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .task_coordination_models import (
    CoordinatedTask,
    TaskAssignment,
    TaskCoordinationWorkflow,
    TaskExecutionRecord,
)
from .task_workload_models import (
    TaskReassignmentResult,
)


class TaskCoordinationEventType(str, Enum):
    WORKFLOW_CREATED = (
        "task.workflow.created"
    )
    WORKFLOW_PREPARED = (
        "task.workflow.prepared"
    )
    WORKFLOW_STARTED = (
        "task.workflow.started"
    )
    WORKFLOW_COMPLETED = (
        "task.workflow.completed"
    )
    WORKFLOW_FAILED = (
        "task.workflow.failed"
    )
    WORKFLOW_CANCELLED = (
        "task.workflow.cancelled"
    )

    TASK_ADDED = (
        "task.added"
    )
    TASK_ASSIGNED = (
        "task.assigned"
    )
    TASK_STARTED = (
        "task.started"
    )
    TASK_COMPLETED = (
        "task.completed"
    )
    TASK_FAILED = (
        "task.failed"
    )
    TASK_RETRY_PENDING = (
        "task.retry.pending"
    )
    TASK_BLOCKED = (
        "task.blocked"
    )
    TASK_SKIPPED = (
        "task.skipped"
    )

    TASK_REASSIGNED = (
        "task.reassigned"
    )
    REASSIGNMENT_BLOCKED = (
        "task.reassignment.blocked"
    )
    REASSIGNMENT_ESCALATED = (
        "task.reassignment.escalated"
    )


class TaskWorkflowEventPayload(BaseModel):
    event_type: TaskCoordinationEventType

    workflow_id: str
    workspace_id: str
    team_id: str

    name: str
    objective: str
    status: str

    task_count: int = 0
    completed_task_count: int = 0
    failed_task_count: int = 0

    progress_ratio: float = 0.0

    created_by: str

    reasons: list[str] = Field(
        default_factory=list
    )

    metadata: dict[str, object] = Field(
        default_factory=dict
    )

    @classmethod
    def from_workflow(
        cls,
        *,
        event_type: TaskCoordinationEventType,
        workflow: TaskCoordinationWorkflow,
        reasons: list[str] | None = None,
    ) -> "TaskWorkflowEventPayload":
        return cls(
            event_type=event_type,
            workflow_id=(
                workflow.workflow_id
            ),
            workspace_id=(
                workflow.workspace_id
            ),
            team_id=workflow.team_id,
            name=workflow.name,
            objective=workflow.objective,
            status=workflow.status.value,
            task_count=workflow.task_count,
            completed_task_count=(
                workflow.completed_task_count
            ),
            failed_task_count=(
                workflow.failed_task_count
            ),
            progress_ratio=round(
                workflow.progress_ratio,
                4,
            ),
            created_by=workflow.created_by,
            reasons=list(
                reasons or []
            ),
            metadata=dict(
                workflow.metadata
            ),
        )


class CoordinatedTaskEventPayload(BaseModel):
    event_type: TaskCoordinationEventType

    workflow_id: str
    task_id: str

    title: str
    description: str

    status: str
    priority: str
    execution_mode: str
    failure_policy: str

    assigned_agent_id: str | None = None

    required_capabilities: list[str] = Field(
        default_factory=list
    )

    required_tasks: list[str] = Field(
        default_factory=list
    )

    dependencies: list[str] = Field(
        default_factory=list
    )

    attempt_count: int = 0
    maximum_attempts: int = 1

    estimated_duration_minutes: int = 0

    error_message: str | None = None
    blocked_reason: str | None = None

    result: dict[str, object] = Field(
        default_factory=dict
    )

    metadata: dict[str, object] = Field(
        default_factory=dict
    )

    @classmethod
    def from_task(
        cls,
        *,
        event_type: TaskCoordinationEventType,
        task: CoordinatedTask,
    ) -> "CoordinatedTaskEventPayload":
        return cls(
            event_type=event_type,
            workflow_id=task.workflow_id,
            task_id=task.task_id,
            title=task.title,
            description=task.description,
            status=task.status.value,
            priority=task.priority.value,
            execution_mode=(
                task.execution_mode.value
            ),
            failure_policy=(
                task.failure_policy.value
            ),
            assigned_agent_id=(
                task.assigned_agent_id
            ),
            required_capabilities=sorted(
                task.required_capabilities
            ),
            required_tasks=sorted(
                task.required_tasks
            ),
            dependencies=sorted(
                task.dependencies
            ),
            attempt_count=(
                task.attempt_count
            ),
            maximum_attempts=(
                task.maximum_attempts
            ),
            estimated_duration_minutes=(
                task
                .estimated_duration_minutes
            ),
            error_message=(
                task.error_message
            ),
            blocked_reason=(
                task.blocked_reason
            ),
            result=dict(task.result),
            metadata=dict(task.metadata),
        )


class TaskAssignmentEventPayload(BaseModel):
    event_type: TaskCoordinationEventType

    workflow_id: str
    task_id: str

    assignment_id: str
    agent_id: str

    assignment_score: float = 0.0

    matched_capabilities: list[str] = Field(
        default_factory=list
    )

    matched_tasks: list[str] = Field(
        default_factory=list
    )

    assigned_by: str

    metadata: dict[str, object] = Field(
        default_factory=dict
    )

    @classmethod
    def from_assignment(
        cls,
        *,
        event_type: TaskCoordinationEventType,
        assignment: TaskAssignment,
    ) -> "TaskAssignmentEventPayload":
        return cls(
            event_type=event_type,
            workflow_id=(
                assignment.workflow_id
            ),
            task_id=assignment.task_id,
            assignment_id=(
                assignment.assignment_id
            ),
            agent_id=assignment.agent_id,
            assignment_score=(
                assignment.assignment_score
            ),
            matched_capabilities=sorted(
                assignment
                .matched_capabilities
            ),
            matched_tasks=sorted(
                assignment.matched_tasks
            ),
            assigned_by=(
                assignment.assigned_by
            ),
            metadata=dict(
                assignment.metadata
            ),
        )


class TaskExecutionEventPayload(BaseModel):
    event_type: TaskCoordinationEventType

    workflow_id: str
    task_id: str

    execution_id: str
    agent_id: str
    attempt_number: int

    successful: bool | None = None

    error_message: str | None = None

    result: dict[str, object] = Field(
        default_factory=dict
    )

    @classmethod
    def from_execution(
        cls,
        *,
        event_type: TaskCoordinationEventType,
        execution: TaskExecutionRecord,
    ) -> "TaskExecutionEventPayload":
        return cls(
            event_type=event_type,
            workflow_id=(
                execution.workflow_id
            ),
            task_id=execution.task_id,
            execution_id=(
                execution.execution_id
            ),
            agent_id=execution.agent_id,
            attempt_number=(
                execution.attempt_number
            ),
            successful=(
                execution.successful
            ),
            error_message=(
                execution.error_message
            ),
            result=dict(
                execution.result
            ),
        )


class TaskReassignmentEventPayload(BaseModel):
    event_type: TaskCoordinationEventType

    workflow_id: str
    task_id: str

    reassignment_id: str
    request_id: str

    previous_agent_id: str | None = None
    replacement_agent_id: str | None = None

    reason: str
    decision: str

    completed: bool = False

    replacement_score: float = 0.0

    details: list[str] = Field(
        default_factory=list
    )

    @classmethod
    def from_result(
        cls,
        *,
        event_type: TaskCoordinationEventType,
        result: TaskReassignmentResult,
    ) -> "TaskReassignmentEventPayload":
        return cls(
            event_type=event_type,
            workflow_id=(
                result.record.workflow_id
            ),
            task_id=result.record.task_id,
            reassignment_id=(
                result.record
                .reassignment_id
            ),
            request_id=(
                result.record.request_id
            ),
            previous_agent_id=(
                result.previous_agent_id
            ),
            replacement_agent_id=(
                result.replacement_agent_id
            ),
            reason=(
                result.record.reason.value
            ),
            decision=(
                result.record.decision.value
            ),
            completed=result.completed,
            replacement_score=(
                result.record
                .replacement_score
            ),
            details=[
                *result.record.details,
                *result.reasons,
            ],
        )
