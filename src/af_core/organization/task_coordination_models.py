from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class CoordinatedTaskStatus(str, Enum):
    CREATED = "created"
    READY = "ready"
    ASSIGNED = "assigned"
    RUNNING = "running"
    BLOCKED = "blocked"
    RETRY_PENDING = "retry_pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class TaskExecutionMode(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    EXCLUSIVE = "exclusive"


class TaskPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {
            TaskPriority.LOW: 1,
            TaskPriority.NORMAL: 5,
            TaskPriority.HIGH: 8,
            TaskPriority.CRITICAL: 10,
        }[self]


class TaskFailurePolicy(str, Enum):
    STOP_WORKFLOW = "stop_workflow"
    RETRY = "retry"
    CONTINUE = "continue"
    SKIP_DEPENDENTS = "skip_dependents"
    ESCALATE = "escalate"


class CoordinationStatus(str, Enum):
    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CoordinatedTask(BaseModel):
    task_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    workflow_id: str

    title: str
    description: str

    required_capabilities: set[str] = Field(
        default_factory=set
    )

    required_tasks: set[str] = Field(
        default_factory=set
    )

    dependencies: set[str] = Field(
        default_factory=set
    )

    assigned_agent_id: str | None = None

    status: CoordinatedTaskStatus = (
        CoordinatedTaskStatus.CREATED
    )

    priority: TaskPriority = (
        TaskPriority.NORMAL
    )

    execution_mode: TaskExecutionMode = (
        TaskExecutionMode.SEQUENTIAL
    )

    failure_policy: TaskFailurePolicy = (
        TaskFailurePolicy.STOP_WORKFLOW
    )

    maximum_attempts: int = 1
    attempt_count: int = 0

    estimated_duration_minutes: int = 0

    result: dict[str, object] = Field(
        default_factory=dict
    )

    error_message: str | None = None
    blocked_reason: str | None = None

    created_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    assigned_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    metadata: dict[str, str] = Field(
        default_factory=dict
    )

    @field_validator(
        "workflow_id",
        "title",
        "description",
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
        "estimated_duration_minutes",
    )
    @classmethod
    def validate_non_negative(
        cls,
        value: int,
    ) -> int:
        if value < 0:
            raise ValueError(
                "value must not be negative"
            )

        return value


class TaskAssignment(BaseModel):
    assignment_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    workflow_id: str
    task_id: str

    agent_id: str

    assignment_score: float = 0.0

    matched_capabilities: set[str] = Field(
        default_factory=set
    )

    matched_tasks: set[str] = Field(
        default_factory=set
    )

    assigned_by: str

    assigned_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    metadata: dict[str, str] = Field(
        default_factory=dict
    )


class TaskExecutionRecord(BaseModel):
    execution_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    workflow_id: str
    task_id: str
    agent_id: str

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


class TaskCoordinationWorkflow(BaseModel):
    workflow_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    workspace_id: str
    team_id: str

    name: str
    objective: str

    status: CoordinationStatus = (
        CoordinationStatus.CREATED
    )

    tasks: list[CoordinatedTask] = Field(
        default_factory=list
    )

    assignments: list[TaskAssignment] = Field(
        default_factory=list
    )

    execution_records: list[
        TaskExecutionRecord
    ] = Field(
        default_factory=list
    )

    created_by: str

    created_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    started_at: datetime | None = None
    completed_at: datetime | None = None

    metadata: dict[str, str] = Field(
        default_factory=dict
    )

    @field_validator(
        "workspace_id",
        "team_id",
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
    def task_count(self) -> int:
        return len(self.tasks)

    @property
    def completed_task_count(self) -> int:
        return sum(
            task.status
            is CoordinatedTaskStatus.COMPLETED
            for task in self.tasks
        )

    @property
    def failed_task_count(self) -> int:
        return sum(
            task.status
            is CoordinatedTaskStatus.FAILED
            for task in self.tasks
        )

    @property
    def progress_ratio(self) -> float:
        if not self.tasks:
            return 0.0

        terminal = sum(
            task.status
            in {
                CoordinatedTaskStatus.COMPLETED,
                CoordinatedTaskStatus.FAILED,
                CoordinatedTaskStatus.CANCELLED,
                CoordinatedTaskStatus.SKIPPED,
            }
            for task in self.tasks
        )

        return terminal / len(self.tasks)


class TaskCoordinationResult(BaseModel):
    workflow: TaskCoordinationWorkflow

    ready_task_ids: list[str] = Field(
        default_factory=list
    )

    blocked_task_ids: list[str] = Field(
        default_factory=list
    )

    running_task_ids: list[str] = Field(
        default_factory=list
    )

    completed_task_ids: list[str] = Field(
        default_factory=list
    )

    failed_task_ids: list[str] = Field(
        default_factory=list
    )
