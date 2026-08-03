from __future__ import annotations

from datetime import datetime, timezone

from .workflow_orchestration_models import (
    OrchestratedWorkflow,
    OrchestratedWorkflowStatus,
    OrchestrationCheckpoint,
    OrchestrationStatus,
    WorkflowExecutionRecord,
    WorkflowFailurePolicy,
    WorkflowOrchestration,
    WorkflowOrchestrationResult,
)
from .workflow_orchestration_repository import (
    WorkflowOrchestrationRepository,
)


class MultiAgentWorkflowOrchestrationEngine:
    """
    Manages lifecycle state across multiple coordinated workflows.
    """

    def __init__(
        self,
        repository: (
            WorkflowOrchestrationRepository
            | None
        ) = None,
    ) -> None:
        self._repository = (
            repository
            or WorkflowOrchestrationRepository()
        )

    def create_orchestration(
        self,
        orchestration: WorkflowOrchestration,
    ) -> WorkflowOrchestration:
        if (
            orchestration.status
            is not OrchestrationStatus.CREATED
        ):
            raise ValueError(
                "new orchestration must have CREATED status"
            )

        self._validate_unique_workflow_ids(
            orchestration.workflows
        )

        return self._repository.save(
            orchestration
        )

    def register_workflow(
        self,
        *,
        orchestration_id: str,
        workflow: OrchestratedWorkflow,
    ) -> WorkflowOrchestration:
        orchestration = (
            self._require_orchestration(
                orchestration_id
            )
        )

        if orchestration.status not in {
            OrchestrationStatus.CREATED,
            OrchestrationStatus.READY,
        }:
            raise ValueError(
                "workflows cannot be registered "
                "after orchestration start"
            )

        if (
            workflow.orchestration_id
            != orchestration_id
        ):
            raise ValueError(
                "workflow orchestration_id mismatch"
            )

        if any(
            existing.workflow_id
            == workflow.workflow_id
            for existing
            in orchestration.workflows
        ):
            raise ValueError(
                "workflow already registered"
            )

        updated = orchestration.model_copy(
            update={
                "workflows": [
                    *orchestration.workflows,
                    workflow,
                ]
            }
        )

        return self._repository.replace(
            updated
        )

    def prepare_orchestration(
        self,
        orchestration_id: str,
    ) -> WorkflowOrchestration:
        orchestration = (
            self._require_orchestration(
                orchestration_id
            )
        )

        if (
            orchestration.status
            is not OrchestrationStatus.CREATED
        ):
            raise ValueError(
                "only CREATED orchestration "
                "can be prepared"
            )

        if not orchestration.workflows:
            raise ValueError(
                "orchestration requires "
                "at least one workflow"
            )

        workflow_ids = {
            workflow.workflow_id
            for workflow
            in orchestration.workflows
        }

        prepared_workflows: list[
            OrchestratedWorkflow
        ] = []

        for workflow in orchestration.workflows:
            unknown = (
                workflow.dependencies
                - workflow_ids
            )

            if unknown:
                raise ValueError(
                    "workflow contains unknown "
                    "dependencies: "
                    + ", ".join(
                        sorted(unknown)
                    )
                )

            if (
                workflow.workflow_id
                in workflow.dependencies
            ):
                raise ValueError(
                    "workflow cannot depend on itself"
                )

            status = (
                OrchestratedWorkflowStatus.READY
                if not workflow.dependencies
                else OrchestratedWorkflowStatus
                .WAITING
            )

            prepared_workflows.append(
                workflow.model_copy(
                    update={
                        "status":
                            status,
                        "blocked_reason": (
                            None
                            if not workflow.dependencies
                            else (
                                "waiting for workflow "
                                "dependencies"
                            )
                        ),
                    }
                )
            )

        prepared = orchestration.model_copy(
            update={
                "status":
                    OrchestrationStatus.READY,
                "workflows":
                    prepared_workflows,
            }
        )

        return self._repository.replace(
            prepared
        )

    def start_orchestration(
        self,
        orchestration_id: str,
    ) -> WorkflowOrchestration:
        orchestration = (
            self._require_orchestration(
                orchestration_id
            )
        )

        if (
            orchestration.status
            is not OrchestrationStatus.READY
        ):
            raise ValueError(
                "only READY orchestration "
                "can be started"
            )

        started = orchestration.model_copy(
            update={
                "status":
                    OrchestrationStatus.RUNNING,
                "started_at":
                    datetime.now(
                        timezone.utc
                    ),
                "pause_reason":
                    None,
            }
        )

        return self._repository.replace(
            started
        )

    def start_workflow(
        self,
        *,
        orchestration_id: str,
        workflow_id: str,
    ) -> WorkflowOrchestration:
        orchestration = (
            self._require_orchestration(
                orchestration_id
            )
        )

        if (
            orchestration.status
            is not OrchestrationStatus.RUNNING
        ):
            raise ValueError(
                "orchestration must be RUNNING"
            )

        workflow = self._require_workflow(
            orchestration=orchestration,
            workflow_id=workflow_id,
        )

        if (
            workflow.status
            is not OrchestratedWorkflowStatus
            .READY
        ):
            raise ValueError(
                "only READY workflows can be started"
            )

        attempt_number = (
            workflow.attempt_count + 1
        )

        record = WorkflowExecutionRecord(
            orchestration_id=(
                orchestration_id
            ),
            workflow_id=workflow_id,
            attempt_number=attempt_number,
        )

        self._repository.add_execution_record(
            record
        )

        running_workflow = (
            workflow.model_copy(
                update={
                    "status":
                        OrchestratedWorkflowStatus
                        .RUNNING,
                    "attempt_count":
                        attempt_number,
                    "started_at":
                        record.started_at,
                    "completed_at":
                        None,
                    "error_message":
                        None,
                    "blocked_reason":
                        None,
                }
            )
        )

        return self._replace_workflow(
            orchestration=orchestration,
            workflow=running_workflow,
        )

    def complete_workflow(
        self,
        *,
        orchestration_id: str,
        workflow_id: str,
        result: (
            dict[str, object] | None
        ) = None,
    ) -> WorkflowOrchestration:
        orchestration = (
            self._require_orchestration(
                orchestration_id
            )
        )

        workflow = self._require_workflow(
            orchestration=orchestration,
            workflow_id=workflow_id,
        )

        if (
            workflow.status
            is not OrchestratedWorkflowStatus
            .RUNNING
        ):
            raise ValueError(
                "only RUNNING workflows "
                "can be completed"
            )

        completed_at = datetime.now(
            timezone.utc
        )

        workflow_result = result or {}

        completed_workflow = (
            workflow.model_copy(
                update={
                    "status":
                        OrchestratedWorkflowStatus
                        .COMPLETED,
                    "result":
                        workflow_result,
                    "completed_at":
                        completed_at,
                    "error_message":
                        None,
                }
            )
        )

        self._complete_execution_record(
            orchestration_id=(
                orchestration_id
            ),
            workflow=workflow,
            successful=True,
            result=workflow_result,
            error_message=None,
            completed_at=completed_at,
        )

        updated = self._replace_workflow(
            orchestration=orchestration,
            workflow=completed_workflow,
        )

        updated = (
            self._refresh_workflow_states(
                updated
            )
        )

        return self._evaluate_status(
            updated
        )

    def fail_workflow(
        self,
        *,
        orchestration_id: str,
        workflow_id: str,
        error_message: str,
    ) -> WorkflowOrchestration:
        orchestration = (
            self._require_orchestration(
                orchestration_id
            )
        )

        workflow = self._require_workflow(
            orchestration=orchestration,
            workflow_id=workflow_id,
        )

        if (
            workflow.status
            is not OrchestratedWorkflowStatus
            .RUNNING
        ):
            raise ValueError(
                "only RUNNING workflows can fail"
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
            workflow.failure_policy
            is WorkflowFailurePolicy
            .RETRY_WORKFLOW
            and workflow.attempt_count
            < workflow.maximum_attempts
        )

        next_status = (
            OrchestratedWorkflowStatus.READY
            if can_retry
            else OrchestratedWorkflowStatus
            .FAILED
        )

        failed_workflow = workflow.model_copy(
            update={
                "status":
                    next_status,
                "error_message":
                    normalized_error,
                "completed_at": (
                    None
                    if can_retry
                    else completed_at
                ),
                "blocked_reason": (
                    "retry pending"
                    if can_retry
                    else None
                ),
            }
        )

        self._complete_execution_record(
            orchestration_id=(
                orchestration_id
            ),
            workflow=workflow,
            successful=False,
            result={},
            error_message=normalized_error,
            completed_at=completed_at,
        )

        updated = self._replace_workflow(
            orchestration=orchestration,
            workflow=failed_workflow,
        )

        updated = (
            self._refresh_workflow_states(
                updated
            )
        )

        return self._evaluate_status(
            updated
        )

    def pause_orchestration(
        self,
        orchestration_id: str,
        *,
        reason: str,
    ) -> WorkflowOrchestration:
        orchestration = (
            self._require_orchestration(
                orchestration_id
            )
        )

        if (
            orchestration.status
            is not OrchestrationStatus.RUNNING
        ):
            raise ValueError(
                "only RUNNING orchestration "
                "can be paused"
            )

        reason = reason.strip()

        if not reason:
            raise ValueError(
                "pause reason must not be empty"
            )

        workflows = [
            (
                workflow.model_copy(
                    update={
                        "status":
                            OrchestratedWorkflowStatus
                            .PAUSED,
                    }
                )
                if (
                    workflow.status
                    is OrchestratedWorkflowStatus
                    .RUNNING
                )
                else workflow
            )
            for workflow
            in orchestration.workflows
        ]

        paused = orchestration.model_copy(
            update={
                "status":
                    OrchestrationStatus.PAUSED,
                "pause_reason":
                    reason,
                "workflows":
                    workflows,
            }
        )

        return self._repository.replace(
            paused
        )

    def resume_orchestration(
        self,
        orchestration_id: str,
    ) -> WorkflowOrchestration:
        orchestration = (
            self._require_orchestration(
                orchestration_id
            )
        )

        if (
            orchestration.status
            is not OrchestrationStatus.PAUSED
        ):
            raise ValueError(
                "only PAUSED orchestration "
                "can be resumed"
            )

        workflows = [
            (
                workflow.model_copy(
                    update={
                        "status":
                            OrchestratedWorkflowStatus
                            .READY,
                    }
                )
                if (
                    workflow.status
                    is OrchestratedWorkflowStatus
                    .PAUSED
                )
                else workflow
            )
            for workflow
            in orchestration.workflows
        ]

        resumed = orchestration.model_copy(
            update={
                "status":
                    OrchestrationStatus.RUNNING,
                "pause_reason":
                    None,
                "workflows":
                    workflows,
            }
        )

        return self._repository.replace(
            resumed
        )

    def cancel_orchestration(
        self,
        orchestration_id: str,
    ) -> WorkflowOrchestration:
        orchestration = (
            self._require_orchestration(
                orchestration_id
            )
        )

        if orchestration.status in {
            OrchestrationStatus.COMPLETED,
            OrchestrationStatus.FAILED,
            OrchestrationStatus.CANCELLED,
        }:
            raise ValueError(
                "orchestration is already finalized"
            )

        workflows = [
            (
                workflow.model_copy(
                    update={
                        "status":
                            OrchestratedWorkflowStatus
                            .CANCELLED,
                    }
                )
                if workflow.status not in {
                    OrchestratedWorkflowStatus
                    .COMPLETED,
                    OrchestratedWorkflowStatus
                    .FAILED,
                    OrchestratedWorkflowStatus
                    .CANCELLED,
                    OrchestratedWorkflowStatus
                    .SKIPPED,
                }
                else workflow
            )
            for workflow
            in orchestration.workflows
        ]

        cancelled = orchestration.model_copy(
            update={
                "status":
                    OrchestrationStatus.CANCELLED,
                "workflows":
                    workflows,
                "completed_at":
                    datetime.now(
                        timezone.utc
                    ),
            }
        )

        return self._repository.replace(
            cancelled
        )

    def create_checkpoint(
        self,
        orchestration_id: str,
        *,
        metadata: (
            dict[str, str] | None
        ) = None,
    ) -> OrchestrationCheckpoint:
        orchestration = (
            self._require_orchestration(
                orchestration_id
            )
        )

        checkpoint = OrchestrationCheckpoint(
            orchestration_id=(
                orchestration_id
            ),
            orchestration_status=(
                orchestration.status
            ),
            workflow_statuses={
                workflow.workflow_id:
                    workflow.status
                for workflow
                in orchestration.workflows
            },
            completed_workflow_ids=[
                workflow.workflow_id
                for workflow
                in orchestration.workflows
                if (
                    workflow.status
                    is OrchestratedWorkflowStatus
                    .COMPLETED
                )
            ],
            active_workflow_ids=[
                workflow.workflow_id
                for workflow
                in orchestration.workflows
                if workflow.status in {
                    OrchestratedWorkflowStatus
                    .RUNNING,
                    OrchestratedWorkflowStatus
                    .PAUSED,
                }
            ],
            failed_workflow_ids=[
                workflow.workflow_id
                for workflow
                in orchestration.workflows
                if (
                    workflow.status
                    is OrchestratedWorkflowStatus
                    .FAILED
                )
            ],
            metadata=metadata or {},
        )

        return self._repository.add_checkpoint(
            checkpoint
        )

    def orchestration_result(
        self,
        orchestration_id: str,
    ) -> WorkflowOrchestrationResult:
        orchestration = (
            self._require_orchestration(
                orchestration_id
            )
        )

        return WorkflowOrchestrationResult(
            orchestration=orchestration,
            ready_workflow_ids=self._workflow_ids_by_status(
                orchestration,
                OrchestratedWorkflowStatus.READY,
            ),
            running_workflow_ids=self._workflow_ids_by_status(
                orchestration,
                OrchestratedWorkflowStatus.RUNNING,
            ),
            blocked_workflow_ids=self._workflow_ids_by_status(
                orchestration,
                OrchestratedWorkflowStatus.BLOCKED,
            ),
            completed_workflow_ids=self._workflow_ids_by_status(
                orchestration,
                OrchestratedWorkflowStatus.COMPLETED,
            ),
            failed_workflow_ids=self._workflow_ids_by_status(
                orchestration,
                OrchestratedWorkflowStatus.FAILED,
            ),
        )

    def get_orchestration(
        self,
        orchestration_id: str,
    ) -> WorkflowOrchestration | None:
        return self._repository.get(
            orchestration_id
        )

    def latest_checkpoint(
        self,
        orchestration_id: str,
    ) -> OrchestrationCheckpoint | None:
        return self._repository.latest_checkpoint(
            orchestration_id
        )

    def execution_records(
        self,
        orchestration_id: str,
    ) -> tuple[
        WorkflowExecutionRecord,
        ...
    ]:
        return self._repository.execution_records(
            orchestration_id
        )

    @staticmethod
    def _workflow_ids_by_status(
        orchestration: WorkflowOrchestration,
        status: OrchestratedWorkflowStatus,
    ) -> list[str]:
        return [
            workflow.workflow_id
            for workflow
            in orchestration.workflows
            if workflow.status is status
        ]

    def _require_orchestration(
        self,
        orchestration_id: str,
    ) -> WorkflowOrchestration:
        orchestration = (
            self._repository.get(
                orchestration_id
            )
        )

        if orchestration is None:
            raise ValueError(
                "workflow orchestration not found"
            )

        return orchestration

    @staticmethod
    def _require_workflow(
        *,
        orchestration: WorkflowOrchestration,
        workflow_id: str,
    ) -> OrchestratedWorkflow:
        for workflow in orchestration.workflows:
            if workflow.workflow_id == workflow_id:
                return workflow

        raise ValueError(
            "orchestrated workflow not found"
        )

    @staticmethod
    def _validate_unique_workflow_ids(
        workflows: list[
            OrchestratedWorkflow
        ],
    ) -> None:
        workflow_ids = [
            workflow.workflow_id
            for workflow in workflows
        ]

        if len(workflow_ids) != len(
            set(workflow_ids)
        ):
            raise ValueError(
                "orchestration contains duplicate workflow IDs"
            )

    @property
    def orchestration_count(self) -> int:
        return self._repository.count

    def _refresh_workflow_states(
        self,
        orchestration: WorkflowOrchestration,
    ) -> WorkflowOrchestration:
        completed_ids = {
            workflow.workflow_id
            for workflow
            in orchestration.workflows
            if (
                workflow.status
                is OrchestratedWorkflowStatus
                .COMPLETED
            )
        }

        failed_ids = {
            workflow.workflow_id
            for workflow
            in orchestration.workflows
            if (
                workflow.status
                is OrchestratedWorkflowStatus
                .FAILED
            )
        }

        refreshed: list[
            OrchestratedWorkflow
        ] = []

        for workflow in orchestration.workflows:
            if workflow.status not in {
                OrchestratedWorkflowStatus.WAITING,
                OrchestratedWorkflowStatus.BLOCKED,
            }:
                refreshed.append(workflow)
                continue

            failed_dependencies = (
                workflow.dependencies
                .intersection(failed_ids)
            )

            if failed_dependencies:
                refreshed.append(
                    workflow.model_copy(
                        update={
                            "status":
                                OrchestratedWorkflowStatus
                                .BLOCKED,
                            "blocked_reason": (
                                "workflow dependency failed: "
                                + ", ".join(
                                    sorted(
                                        failed_dependencies
                                    )
                                )
                            ),
                        }
                    )
                )
                continue

            if workflow.dependencies.issubset(
                completed_ids
            ):
                refreshed.append(
                    workflow.model_copy(
                        update={
                            "status":
                                OrchestratedWorkflowStatus
                                .READY,
                            "blocked_reason":
                                None,
                        }
                    )
                )
                continue

            refreshed.append(
                workflow.model_copy(
                    update={
                        "blocked_reason": (
                            "waiting for workflow "
                            "dependencies"
                        ),
                    }
                )
            )

        updated = orchestration.model_copy(
            update={
                "workflows": refreshed,
            }
        )

        return self._repository.replace(
            updated
        )

    def _evaluate_status(
        self,
        orchestration: WorkflowOrchestration,
    ) -> WorkflowOrchestration:
        if orchestration.status in {
            OrchestrationStatus.CANCELLED,
            OrchestrationStatus.PAUSED,
        }:
            return orchestration

        if orchestration.workflows and all(
            workflow.status in {
                OrchestratedWorkflowStatus.COMPLETED,
                OrchestratedWorkflowStatus.SKIPPED,
            }
            for workflow
            in orchestration.workflows
        ):
            completed = orchestration.model_copy(
                update={
                    "status":
                        OrchestrationStatus.COMPLETED,
                    "completed_at":
                        datetime.now(timezone.utc),
                    "failure_reason":
                        None,
                }
            )

            return self._repository.replace(
                completed
            )

        stop_failures = [
            workflow
            for workflow
            in orchestration.workflows
            if (
                workflow.status
                is OrchestratedWorkflowStatus.FAILED
                and workflow.failure_policy
                in {
                    WorkflowFailurePolicy
                    .STOP_ORCHESTRATION,
                    WorkflowFailurePolicy
                    .ESCALATE,
                }
            )
        ]

        if stop_failures:
            failed = orchestration.model_copy(
                update={
                    "status":
                        OrchestrationStatus.FAILED,
                    "failure_reason": (
                        stop_failures[0]
                        .error_message
                        or "workflow failed"
                    ),
                    "completed_at":
                        datetime.now(timezone.utc),
                }
            )

            return self._repository.replace(
                failed
            )

        blocked_exists = any(
            workflow.status
            is OrchestratedWorkflowStatus.BLOCKED
            for workflow
            in orchestration.workflows
        )

        next_status = (
            OrchestrationStatus.BLOCKED
            if blocked_exists
            else OrchestrationStatus.RUNNING
        )

        updated = orchestration.model_copy(
            update={
                "status": next_status,
                "completed_at": None,
            }
        )

        return self._repository.replace(
            updated
        )

    def _complete_execution_record(
        self,
        *,
        orchestration_id: str,
        workflow: OrchestratedWorkflow,
        successful: bool,
        result: dict[str, object],
        error_message: str | None,
        completed_at: datetime,
    ) -> WorkflowExecutionRecord:
        active_records = [
            record
            for record
            in self._repository.execution_records(
                orchestration_id
            )
            if (
                record.workflow_id
                == workflow.workflow_id
                and record.attempt_number
                == workflow.attempt_count
                and record.completed_at
                is None
            )
        ]

        if not active_records:
            raise ValueError(
                "active workflow execution "
                "record not found"
            )

        record = active_records[-1]

        completed_record = record.model_copy(
            update={
                "completed_at": completed_at,
                "successful": successful,
                "result": result,
                "error_message":
                    error_message,
            }
        )

        return (
            self._repository
            .replace_execution_record(
                completed_record
            )
        )

    def _replace_workflow(
        self,
        *,
        orchestration: WorkflowOrchestration,
        workflow: OrchestratedWorkflow,
    ) -> WorkflowOrchestration:
        workflows = [
            (
                workflow
                if existing.workflow_id
                == workflow.workflow_id
                else existing
            )
            for existing
            in orchestration.workflows
        ]

        updated = orchestration.model_copy(
            update={
                "workflows": workflows,
            }
        )

        return self._repository.replace(
            updated
        )
