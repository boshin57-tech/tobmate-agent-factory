from __future__ import annotations

from typing import Any

from af_core.communication import (
    AgentCommunicationBus,
    AgentMessage,
    MessageType,
)

from .task_coordination_models import (
    CoordinatedTask,
    TaskAssignment,
    TaskCoordinationWorkflow,
    TaskExecutionRecord,
)
from .task_event_models import (
    CoordinatedTaskEventPayload,
    TaskAssignmentEventPayload,
    TaskCoordinationEventType,
    TaskExecutionEventPayload,
    TaskReassignmentEventPayload,
    TaskWorkflowEventPayload,
)
from .task_workload_models import (
    TaskReassignmentResult,
)


class TaskCoordinationEventPublisher:
    """
    Publishes Task Coordination lifecycle events through the
    Agent Communication Bus.

    Authority enforcement and immutable communication auditing are
    delegated to the existing secure Communication Bus.
    """

    def __init__(
        self,
        bus: AgentCommunicationBus,
        *,
        sender_agent_id: str = (
            "multi-agent-task-coordinator"
        ),
    ) -> None:
        self._bus = bus
        self._sender_agent_id = (
            sender_agent_id
        )

    def publish_workflow(
        self,
        *,
        event_type: TaskCoordinationEventType,
        workflow: TaskCoordinationWorkflow,
        reasons: list[str] | None = None,
        protected: bool = False,
        environment: str = "runtime",
        permission: str = (
            "task_workflow_manage"
        ),
    ):
        payload = (
            TaskWorkflowEventPayload
            .from_workflow(
                event_type=event_type,
                workflow=workflow,
                reasons=reasons,
            )
        )

        return self._publish(
            topic=event_type.value,
            workspace_id=(
                workflow.workspace_id
            ),
            correlation_id=(
                workflow.workflow_id
            ),
            payload=payload.model_dump(
                mode="json"
            ),
            metadata={
                "workflow_id":
                    workflow.workflow_id,
                "team_id":
                    workflow.team_id,
                "workflow_status":
                    workflow.status.value,
            },
            protected=protected,
            permission=permission,
            environment=environment,
            resource_scope=(
                workflow.team_id
            ),
        )

    def publish_task(
        self,
        *,
        event_type: TaskCoordinationEventType,
        workflow: TaskCoordinationWorkflow,
        task: CoordinatedTask,
        protected: bool = False,
        environment: str = "runtime",
        permission: str = (
            "task_execution_manage"
        ),
    ):
        payload = (
            CoordinatedTaskEventPayload
            .from_task(
                event_type=event_type,
                task=task,
            )
        )

        return self._publish(
            topic=event_type.value,
            workspace_id=(
                workflow.workspace_id
            ),
            correlation_id=(
                workflow.workflow_id
            ),
            payload=payload.model_dump(
                mode="json"
            ),
            metadata={
                "workflow_id":
                    workflow.workflow_id,
                "task_id":
                    task.task_id,
                "task_status":
                    task.status.value,
                "assigned_agent_id":
                    task.assigned_agent_id
                    or "",
            },
            protected=protected,
            permission=permission,
            environment=environment,
            resource_scope=(
                workflow.team_id
            ),
        )

    def publish_assignment(
        self,
        *,
        workflow: TaskCoordinationWorkflow,
        assignment: TaskAssignment,
        protected: bool = False,
        environment: str = "runtime",
    ):
        payload = (
            TaskAssignmentEventPayload
            .from_assignment(
                event_type=(
                    TaskCoordinationEventType
                    .TASK_ASSIGNED
                ),
                assignment=assignment,
            )
        )

        return self._publish(
            topic=(
                TaskCoordinationEventType
                .TASK_ASSIGNED.value
            ),
            workspace_id=(
                workflow.workspace_id
            ),
            correlation_id=(
                workflow.workflow_id
            ),
            payload=payload.model_dump(
                mode="json"
            ),
            metadata={
                "workflow_id":
                    workflow.workflow_id,
                "task_id":
                    assignment.task_id,
                "assignment_id":
                    assignment.assignment_id,
                "agent_id":
                    assignment.agent_id,
            },
            protected=protected,
            permission=(
                "task_assignment_manage"
            ),
            environment=environment,
            resource_scope=(
                workflow.team_id
            ),
        )

    def publish_execution(
        self,
        *,
        event_type: TaskCoordinationEventType,
        workflow: TaskCoordinationWorkflow,
        execution: TaskExecutionRecord,
        protected: bool = False,
        environment: str = "runtime",
    ):
        payload = (
            TaskExecutionEventPayload
            .from_execution(
                event_type=event_type,
                execution=execution,
            )
        )

        return self._publish(
            topic=event_type.value,
            workspace_id=(
                workflow.workspace_id
            ),
            correlation_id=(
                workflow.workflow_id
            ),
            payload=payload.model_dump(
                mode="json"
            ),
            metadata={
                "workflow_id":
                    workflow.workflow_id,
                "task_id":
                    execution.task_id,
                "execution_id":
                    execution.execution_id,
                "agent_id":
                    execution.agent_id,
                "attempt_number":
                    str(
                        execution
                        .attempt_number
                    ),
            },
            protected=protected,
            permission=(
                "task_execution_manage"
            ),
            environment=environment,
            resource_scope=(
                workflow.team_id
            ),
        )

    def publish_reassignment(
        self,
        *,
        event_type: TaskCoordinationEventType,
        workflow: TaskCoordinationWorkflow,
        result: TaskReassignmentResult,
        protected: bool = False,
        environment: str = "runtime",
    ):
        payload = (
            TaskReassignmentEventPayload
            .from_result(
                event_type=event_type,
                result=result,
            )
        )

        return self._publish(
            topic=event_type.value,
            workspace_id=(
                workflow.workspace_id
            ),
            correlation_id=(
                workflow.workflow_id
            ),
            payload=payload.model_dump(
                mode="json"
            ),
            metadata={
                "workflow_id":
                    workflow.workflow_id,
                "task_id":
                    result.task.task_id,
                "reassignment_id":
                    result.record
                    .reassignment_id,
                "decision":
                    result.record
                    .decision.value,
                "replacement_agent_id":
                    result
                    .replacement_agent_id
                    or "",
            },
            protected=protected,
            permission=(
                "task_reassignment_manage"
            ),
            environment=environment,
            resource_scope=(
                workflow.team_id
            ),
        )

    def _publish(
        self,
        *,
        topic: str,
        workspace_id: str,
        correlation_id: str,
        payload: dict[str, Any],
        metadata: dict[str, str],
        protected: bool,
        permission: str,
        environment: str,
        resource_scope: str,
    ):
        message_metadata = dict(
            metadata
        )

        if protected:
            message_metadata.update(
                {
                    "required_permission":
                        permission,
                    "environment":
                        environment,
                    "resource_scope":
                        resource_scope,
                }
            )

        message = AgentMessage(
            topic=topic,
            message_type=(
                MessageType.EVENT_PUBLISHED
            ),
            sender_agent_id=(
                self._sender_agent_id
            ),
            workspace_id=(
                workspace_id
            ),
            correlation_id=(
                correlation_id
            ),
            payload=payload,
            metadata=message_metadata,
        )

        return self._bus.publish(
            message
        )
