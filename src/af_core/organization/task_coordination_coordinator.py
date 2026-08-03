from __future__ import annotations

from .task_coordination_engine import (
    MultiAgentTaskCoordinationEngine,
)
from .task_coordination_models import (
    CoordinatedTask,
    CoordinatedTaskStatus,
    CoordinationStatus,
    TaskAssignment,
    TaskCoordinationWorkflow,
    TaskExecutionRecord,
)
from .task_event_models import (
    TaskCoordinationEventType,
)
from .task_event_publisher import (
    TaskCoordinationEventPublisher,
)
from .task_workload_models import (
    TaskAgentRuntimeProfile,
    TaskAgentSelectionResult,
    TaskReassignmentDecision,
    TaskReassignmentRequest,
    TaskReassignmentResult,
)


class TaskCoordinationCoordinator:
    """
    Coordinates task state transitions and Communication Bus events.

    The underlying engine remains the state authority. This coordinator
    publishes an event only after the requested state transition has
    completed successfully.
    """

    def __init__(
        self,
        *,
        engine: MultiAgentTaskCoordinationEngine,
        publisher: TaskCoordinationEventPublisher,
    ) -> None:
        self._engine = engine
        self._publisher = publisher

    def register_runtime_profile(
        self,
        profile: TaskAgentRuntimeProfile,
    ) -> TaskAgentRuntimeProfile:
        return (
            self._engine
            .register_runtime_profile(
                profile
            )
        )

    def create_workflow(
        self,
        workflow: TaskCoordinationWorkflow,
        *,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> TaskCoordinationWorkflow:
        created = self._engine.create_workflow(
            workflow
        )

        self._publisher.publish_workflow(
            event_type=(
                TaskCoordinationEventType
                .WORKFLOW_CREATED
            ),
            workflow=created,
            protected=protected_event,
            environment=environment,
        )

        return created

    def add_task(
        self,
        *,
        workflow_id: str,
        task: CoordinatedTask,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> TaskCoordinationWorkflow:
        updated = self._engine.add_task(
            workflow_id=workflow_id,
            task=task,
        )

        stored_task = self._require_task(
            workflow=updated,
            task_id=task.task_id,
        )

        self._publisher.publish_task(
            event_type=(
                TaskCoordinationEventType
                .TASK_ADDED
            ),
            workflow=updated,
            task=stored_task,
            protected=protected_event,
            environment=environment,
        )

        return updated

    def prepare_workflow(
        self,
        workflow_id: str,
        *,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> TaskCoordinationWorkflow:
        prepared = (
            self._engine
            .prepare_workflow(
                workflow_id
            )
        )

        self._publisher.publish_workflow(
            event_type=(
                TaskCoordinationEventType
                .WORKFLOW_PREPARED
            ),
            workflow=prepared,
            protected=protected_event,
            environment=environment,
        )

        for task in prepared.tasks:
            if (
                task.status
                is CoordinatedTaskStatus.BLOCKED
            ):
                self._publisher.publish_task(
                    event_type=(
                        TaskCoordinationEventType
                        .TASK_BLOCKED
                    ),
                    workflow=prepared,
                    task=task,
                    protected=protected_event,
                    environment=environment,
                )

        return prepared

    def assign_task(
        self,
        *,
        workflow_id: str,
        task_id: str,
        agent_id: str,
        assigned_by: str,
        assignment_score: float = 0.0,
        matched_capabilities: (
            set[str] | None
        ) = None,
        matched_tasks: (
            set[str] | None
        ) = None,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> TaskCoordinationWorkflow:
        updated = self._engine.assign_task(
            workflow_id=workflow_id,
            task_id=task_id,
            agent_id=agent_id,
            assigned_by=assigned_by,
            assignment_score=(
                assignment_score
            ),
            matched_capabilities=(
                matched_capabilities
            ),
            matched_tasks=matched_tasks,
        )

        assignment = (
            self._latest_assignment(
                workflow=updated,
                task_id=task_id,
            )
        )

        self._publisher.publish_assignment(
            workflow=updated,
            assignment=assignment,
            protected=protected_event,
            environment=environment,
        )

        return updated

    def automatically_assign_task(
        self,
        *,
        workflow_id: str,
        task_id: str,
        assigned_by: str,
        excluded_agent_ids: (
            set[str] | None
        ) = None,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> tuple[
        TaskCoordinationWorkflow,
        TaskAgentSelectionResult,
    ]:
        updated, selection = (
            self._engine
            .automatically_assign_task(
                workflow_id=workflow_id,
                task_id=task_id,
                assigned_by=assigned_by,
                excluded_agent_ids=(
                    excluded_agent_ids
                ),
            )
        )

        if (
            selection.fulfilled
            and selection.selected_agent_id
            is not None
        ):
            assignment = (
                self._latest_assignment(
                    workflow=updated,
                    task_id=task_id,
                )
            )

            self._publisher.publish_assignment(
                workflow=updated,
                assignment=assignment,
                protected=protected_event,
                environment=environment,
            )

        return updated, selection

    def start_workflow(
        self,
        workflow_id: str,
        *,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> TaskCoordinationWorkflow:
        started = (
            self._engine
            .start_workflow(
                workflow_id
            )
        )

        self._publisher.publish_workflow(
            event_type=(
                TaskCoordinationEventType
                .WORKFLOW_STARTED
            ),
            workflow=started,
            protected=protected_event,
            environment=environment,
        )

        return started

    def start_task(
        self,
        *,
        workflow_id: str,
        task_id: str,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> TaskCoordinationWorkflow:
        updated = self._engine.start_task(
            workflow_id=workflow_id,
            task_id=task_id,
        )

        execution = (
            self._active_execution(
                workflow=updated,
                task_id=task_id,
            )
        )

        self._publisher.publish_execution(
            event_type=(
                TaskCoordinationEventType
                .TASK_STARTED
            ),
            workflow=updated,
            execution=execution,
            protected=protected_event,
            environment=environment,
        )

        return updated

    def complete_task(
        self,
        *,
        workflow_id: str,
        task_id: str,
        result: (
            dict[str, object] | None
        ) = None,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> TaskCoordinationWorkflow:
        updated = self._engine.complete_task(
            workflow_id=workflow_id,
            task_id=task_id,
            result=result,
        )

        execution = (
            self._latest_execution(
                workflow=updated,
                task_id=task_id,
            )
        )

        self._publisher.publish_execution(
            event_type=(
                TaskCoordinationEventType
                .TASK_COMPLETED
            ),
            workflow=updated,
            execution=execution,
            protected=protected_event,
            environment=environment,
        )

        if (
            updated.status
            is CoordinationStatus.COMPLETED
        ):
            self._publisher.publish_workflow(
                event_type=(
                    TaskCoordinationEventType
                    .WORKFLOW_COMPLETED
                ),
                workflow=updated,
                protected=protected_event,
                environment=environment,
            )

        return updated

    def fail_task(
        self,
        *,
        workflow_id: str,
        task_id: str,
        error_message: str,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> TaskCoordinationWorkflow:
        updated = self._engine.fail_task(
            workflow_id=workflow_id,
            task_id=task_id,
            error_message=error_message,
        )

        execution = (
            self._latest_execution(
                workflow=updated,
                task_id=task_id,
            )
        )

        task = self._require_task(
            workflow=updated,
            task_id=task_id,
        )

        if (
            task.status
            is CoordinatedTaskStatus
            .RETRY_PENDING
        ):
            event_type = (
                TaskCoordinationEventType
                .TASK_RETRY_PENDING
            )
        else:
            event_type = (
                TaskCoordinationEventType
                .TASK_FAILED
            )

        self._publisher.publish_execution(
            event_type=event_type,
            workflow=updated,
            execution=execution,
            protected=protected_event,
            environment=environment,
        )

        if (
            updated.status
            is CoordinationStatus.FAILED
        ):
            self._publisher.publish_workflow(
                event_type=(
                    TaskCoordinationEventType
                    .WORKFLOW_FAILED
                ),
                workflow=updated,
                reasons=[
                    error_message,
                ],
                protected=protected_event,
                environment=environment,
            )

        return updated

    def reassign_task(
        self,
        request: TaskReassignmentRequest,
        *,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> TaskReassignmentResult:
        result = self._engine.reassign_task(
            request
        )

        workflow = self._require_workflow(
            request.workflow_id
        )

        event_type = (
            self._reassignment_event_type(
                result
            )
        )

        self._publisher.publish_reassignment(
            event_type=event_type,
            workflow=workflow,
            result=result,
            protected=protected_event,
            environment=environment,
        )

        if (
            result.task.status
            is CoordinatedTaskStatus.BLOCKED
        ):
            self._publisher.publish_task(
                event_type=(
                    TaskCoordinationEventType
                    .TASK_BLOCKED
                ),
                workflow=workflow,
                task=result.task,
                protected=protected_event,
                environment=environment,
            )

        return result

    def reassign_unhealthy_tasks(
        self,
        *,
        workflow_id: str,
        requested_by: str,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> list[
        TaskReassignmentResult
    ]:
        results = (
            self._engine
            .reassign_unhealthy_tasks(
                workflow_id=workflow_id,
                requested_by=requested_by,
            )
        )

        workflow = self._require_workflow(
            workflow_id
        )

        for result in results:
            event_type = (
                self._reassignment_event_type(
                    result
                )
            )

            self._publisher.publish_reassignment(
                event_type=event_type,
                workflow=workflow,
                result=result,
                protected=protected_event,
                environment=environment,
            )

        return results

    def cancel_workflow(
        self,
        workflow_id: str,
        *,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> TaskCoordinationWorkflow:
        cancelled = (
            self._engine
            .cancel_workflow(
                workflow_id
            )
        )

        self._publisher.publish_workflow(
            event_type=(
                TaskCoordinationEventType
                .WORKFLOW_CANCELLED
            ),
            workflow=cancelled,
            protected=protected_event,
            environment=environment,
        )

        return cancelled

    def get_workflow(
        self,
        workflow_id: str,
    ) -> TaskCoordinationWorkflow | None:
        return self._engine.get_workflow(
            workflow_id
        )

    def _require_workflow(
        self,
        workflow_id: str,
    ) -> TaskCoordinationWorkflow:
        workflow = self._engine.get_workflow(
            workflow_id
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
    def _latest_assignment(
        *,
        workflow: TaskCoordinationWorkflow,
        task_id: str,
    ) -> TaskAssignment:
        assignments = [
            assignment
            for assignment
            in workflow.assignments
            if assignment.task_id == task_id
        ]

        if not assignments:
            raise ValueError(
                "task assignment not found"
            )

        return max(
            assignments,
            key=lambda assignment:
                assignment.assigned_at,
        )

    @staticmethod
    def _active_execution(
        *,
        workflow: TaskCoordinationWorkflow,
        task_id: str,
    ) -> TaskExecutionRecord:
        records = [
            record
            for record
            in workflow.execution_records
            if (
                record.task_id == task_id
                and record.completed_at
                is None
            )
        ]

        if not records:
            raise ValueError(
                "active task execution not found"
            )

        return max(
            records,
            key=lambda record:
                record.started_at,
        )

    @staticmethod
    def _latest_execution(
        *,
        workflow: TaskCoordinationWorkflow,
        task_id: str,
    ) -> TaskExecutionRecord:
        records = [
            record
            for record
            in workflow.execution_records
            if record.task_id == task_id
        ]

        if not records:
            raise ValueError(
                "task execution record not found"
            )

        return max(
            records,
            key=lambda record:
                record.started_at,
        )

    @staticmethod
    def _reassignment_event_type(
        result: TaskReassignmentResult,
    ) -> TaskCoordinationEventType:
        if result.completed:
            return (
                TaskCoordinationEventType
                .TASK_REASSIGNED
            )

        if (
            result.record.decision
            is TaskReassignmentDecision
            .ESCALATE
        ):
            return (
                TaskCoordinationEventType
                .REASSIGNMENT_ESCALATED
            )

        return (
            TaskCoordinationEventType
            .REASSIGNMENT_BLOCKED
        )
