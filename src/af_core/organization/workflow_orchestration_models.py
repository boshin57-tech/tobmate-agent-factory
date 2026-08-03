from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class OrchestrationStatus(str, Enum):
    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    BLOCKED = "blocked"
    RECOVERING = "recovering"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OrchestratedWorkflowStatus(str, Enum):
    REGISTERED = "registered"
    WAITING = "waiting"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class WorkflowExecutionPolicy(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"
    EXCLUSIVE = "exclusive"


class WorkflowFailurePolicy(str, Enum):
    STOP_ORCHESTRATION = "stop_orchestration"
    RETRY_WORKFLOW = "retry_workflow"
    CONTINUE = "continue"
    SKIP_DEPENDENTS = "skip_dependents"
    COMPENSATE = "compensate"
    ESCALATE = "escalate"


class WorkflowTriggerType(str, Enum):
    MANUAL = "manual"
    DEPENDENCY_COMPLETED = "dependency_completed"
    EVENT = "event"
    CONDITION = "condition"
    SCHEDULE = "schedule"
    IMMEDIATE = "immediate"


class WorkflowPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {
            WorkflowPriority.LOW: 1,
            WorkflowPriority.NORMAL: 5,
            WorkflowPriority.HIGH: 8,
            WorkflowPriority.CRITICAL: 10,
        }[self]


class OrchestratedWorkflow(BaseModel):
    orchestration_workflow_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    orchestration_id: str

    workflow_id: str
    workspace_id: str
    team_id: str

    name: str
    objective: str

    status: OrchestratedWorkflowStatus = (
        OrchestratedWorkflowStatus.REGISTERED
    )

    execution_policy: WorkflowExecutionPolicy = (
        WorkflowExecutionPolicy.SEQUENTIAL
    )

    failure_policy: WorkflowFailurePolicy = (
        WorkflowFailurePolicy.STOP_ORCHESTRATION
    )

    trigger_type: WorkflowTriggerType = (
        WorkflowTriggerType.DEPENDENCY_COMPLETED
    )

    priority: WorkflowPriority = (
        WorkflowPriority.NORMAL
    )

    dependencies: set[str] = Field(
        default_factory=set
    )

    condition_name: str | None = None
    trigger_topic: str | None = None

    maximum_attempts: int = 1
    attempt_count: int = 0

    timeout_seconds: int | None = None

    started_at: datetime | None = None
    completed_at: datetime | None = None

    error_message: str | None = None
    blocked_reason: str | None = None

    result: dict[str, object] = Field(
        default_factory=dict
    )

    metadata: dict[str, str] = Field(
        default_factory=dict
    )

    @field_validator(
        "orchestration_id",
        "workflow_id",
        "workspace_id",
        "team_id",
        "name",
        "objective",
    )
    @classmethod
    def validate_required_text(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "value must not be empty"
            )

        return normalized

    @field_validator(
        "maximum_attempts",
    )
    @classmethod
    def validate_maximum_attempts(
        cls,
        value: int,
    ) -> int:
        if value < 1:
            raise ValueError(
                "maximum_attempts must be at least 1"
            )

        return value

    @field_validator(
        "attempt_count",
    )
    @classmethod
    def validate_attempt_count(
        cls,
        value: int,
    ) -> int:
        if value < 0:
            raise ValueError(
                "attempt_count must not be negative"
            )

        return value

    @field_validator(
        "timeout_seconds",
    )
    @classmethod
    def validate_timeout(
        cls,
        value: int | None,
    ) -> int | None:
        if value is not None and value < 1:
            raise ValueError(
                "timeout_seconds must be positive"
            )

        return value


class WorkflowOrchestration(BaseModel):
    orchestration_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    workspace_id: str

    name: str
    objective: str

    created_by: str

    status: OrchestrationStatus = (
        OrchestrationStatus.CREATED
    )

    workflows: list[
        OrchestratedWorkflow
    ] = Field(
        default_factory=list
    )

    created_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    started_at: datetime | None = None
    completed_at: datetime | None = None

    pause_reason: str | None = None
    failure_reason: str | None = None

    metadata: dict[str, str] = Field(
        default_factory=dict
    )

    @field_validator(
        "workspace_id",
        "name",
        "objective",
        "created_by",
    )
    @classmethod
    def validate_required_text(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "value must not be empty"
            )

        return normalized

    @property
    def workflow_count(self) -> int:
        return len(self.workflows)

    @property
    def completed_workflow_count(self) -> int:
        return sum(
            workflow.status
            is OrchestratedWorkflowStatus.COMPLETED
            for workflow in self.workflows
        )

    @property
    def failed_workflow_count(self) -> int:
        return sum(
            workflow.status
            is OrchestratedWorkflowStatus.FAILED
            for workflow in self.workflows
        )

    @property
    def progress_ratio(self) -> float:
        if not self.workflows:
            return 0.0

        terminal_count = sum(
            workflow.status
            in {
                OrchestratedWorkflowStatus.COMPLETED,
                OrchestratedWorkflowStatus.FAILED,
                OrchestratedWorkflowStatus.CANCELLED,
                OrchestratedWorkflowStatus.SKIPPED,
            }
            for workflow in self.workflows
        )

        return terminal_count / len(
            self.workflows
        )


class WorkflowExecutionRecord(BaseModel):
    execution_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    orchestration_id: str
    workflow_id: str

    attempt_number: int

    started_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    completed_at: datetime | None = None

    successful: bool | None = None

    result: dict[str, object] = Field(
        default_factory=dict
    )

    error_message: str | None = None


class OrchestrationCheckpoint(BaseModel):
    checkpoint_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    orchestration_id: str

    orchestration_status: OrchestrationStatus

    workflow_statuses: dict[
        str,
        OrchestratedWorkflowStatus,
    ] = Field(
        default_factory=dict
    )

    completed_workflow_ids: list[str] = Field(
        default_factory=list
    )

    active_workflow_ids: list[str] = Field(
        default_factory=list
    )

    failed_workflow_ids: list[str] = Field(
        default_factory=list
    )

    metadata: dict[str, str] = Field(
        default_factory=dict
    )

    created_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )


class WorkflowOrchestrationResult(BaseModel):
    orchestration: WorkflowOrchestration

    ready_workflow_ids: list[str] = Field(
        default_factory=list
    )

    running_workflow_ids: list[str] = Field(
        default_factory=list
    )

    blocked_workflow_ids: list[str] = Field(
        default_factory=list
    )

    completed_workflow_ids: list[str] = Field(
        default_factory=list
    )

    failed_workflow_ids: list[str] = Field(
        default_factory=list
    )
