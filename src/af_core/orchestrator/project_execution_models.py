"""Autonomous project execution runtime lifecycle models."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Mapping
from uuid import uuid4


class ProjectExecutionError(ValueError):
    """Raised when a project execution invariant is violated."""


class ProjectRunStatus(str, Enum):
    """Lifecycle states for one autonomous project run."""

    CREATED = "created"
    PLANNING = "planning"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    RECOVERING = "recovering"
    VALIDATING = "validating"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProjectTaskStatus(str, Enum):
    """Runtime states for one task inside a project run."""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class ProjectRunEventKind(str, Enum):
    """Immutable project execution audit events."""

    RUN_CREATED = "run_created"
    RUN_TRANSITIONED = "run_transitioned"
    RUN_RESUMED = "run_resumed"
    TASK_REGISTERED = "task_registered"
    TASK_TRANSITIONED = "task_transitioned"
    TASK_ASSIGNED = "task_assigned"
    TASK_OUTPUT_RECORDED = "task_output_recorded"
    CHECKPOINT_SAVED = "checkpoint_saved"
    DELIVERY_CREATED = "delivery_created"


TERMINAL_RUN_STATUSES = frozenset(
    {
        ProjectRunStatus.COMPLETED,
        ProjectRunStatus.PARTIAL,
        ProjectRunStatus.FAILED,
        ProjectRunStatus.CANCELLED,
    }
)

TERMINAL_TASK_STATUSES = frozenset(
    {
        ProjectTaskStatus.SUCCEEDED,
        ProjectTaskStatus.FAILED,
        ProjectTaskStatus.SKIPPED,
        ProjectTaskStatus.CANCELLED,
    }
)


_ALLOWED_RUN_TRANSITIONS = {
    ProjectRunStatus.CREATED: frozenset(
        {
            ProjectRunStatus.PLANNING,
            ProjectRunStatus.CANCELLED,
        }
    ),
    ProjectRunStatus.PLANNING: frozenset(
        {
            ProjectRunStatus.READY,
            ProjectRunStatus.FAILED,
            ProjectRunStatus.CANCELLED,
        }
    ),
    ProjectRunStatus.READY: frozenset(
        {
            ProjectRunStatus.RUNNING,
            ProjectRunStatus.CANCELLED,
        }
    ),
    ProjectRunStatus.RUNNING: frozenset(
        {
            ProjectRunStatus.PAUSED,
            ProjectRunStatus.RECOVERING,
            ProjectRunStatus.VALIDATING,
            ProjectRunStatus.FAILED,
            ProjectRunStatus.CANCELLED,
        }
    ),
    ProjectRunStatus.PAUSED: frozenset(
        {
            ProjectRunStatus.RUNNING,
            ProjectRunStatus.RECOVERING,
            ProjectRunStatus.CANCELLED,
        }
    ),
    ProjectRunStatus.RECOVERING: frozenset(
        {
            ProjectRunStatus.RUNNING,
            ProjectRunStatus.PAUSED,
            ProjectRunStatus.FAILED,
            ProjectRunStatus.CANCELLED,
        }
    ),
    ProjectRunStatus.VALIDATING: frozenset(
        {
            ProjectRunStatus.COMPLETED,
            ProjectRunStatus.PARTIAL,
            ProjectRunStatus.FAILED,
            ProjectRunStatus.RUNNING,
        }
    ),
    ProjectRunStatus.COMPLETED: frozenset(),
    ProjectRunStatus.PARTIAL: frozenset(),
    ProjectRunStatus.FAILED: frozenset(),
    ProjectRunStatus.CANCELLED: frozenset(),
}


_ALLOWED_TASK_TRANSITIONS = {
    ProjectTaskStatus.PENDING: frozenset(
        {
            ProjectTaskStatus.READY,
            ProjectTaskStatus.BLOCKED,
            ProjectTaskStatus.SKIPPED,
            ProjectTaskStatus.CANCELLED,
        }
    ),
    ProjectTaskStatus.READY: frozenset(
        {
            ProjectTaskStatus.RUNNING,
            ProjectTaskStatus.BLOCKED,
            ProjectTaskStatus.CANCELLED,
        }
    ),
    ProjectTaskStatus.RUNNING: frozenset(
        {
            ProjectTaskStatus.SUCCEEDED,
            ProjectTaskStatus.FAILED,
            ProjectTaskStatus.BLOCKED,
            ProjectTaskStatus.CANCELLED,
        }
    ),
    ProjectTaskStatus.FAILED: frozenset(
        {
            ProjectTaskStatus.READY,
            ProjectTaskStatus.SKIPPED,
        }
    ),
    ProjectTaskStatus.BLOCKED: frozenset(
        {
            ProjectTaskStatus.READY,
            ProjectTaskStatus.SKIPPED,
            ProjectTaskStatus.CANCELLED,
        }
    ),
    ProjectTaskStatus.SUCCEEDED: frozenset(),
    ProjectTaskStatus.SKIPPED: frozenset(),
    ProjectTaskStatus.CANCELLED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class ProjectTaskRuntimeState:
    """Persistent execution state for one planned task."""

    task_id: str
    status: ProjectTaskStatus = ProjectTaskStatus.PENDING
    attempts: int = 0
    assigned_agent_id: str | None = None
    assigned_team_id: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    last_error: str = ""
    output_reference: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise ProjectExecutionError(
                "task_id must not be empty"
            )

        if self.attempts < 0:
            raise ProjectExecutionError(
                "attempts must not be negative"
            )

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_TASK_STATUSES

    def transition(
        self,
        target: ProjectTaskStatus,
        *,
        now: float,
        error: str = "",
    ) -> ProjectTaskRuntimeState:
        """Return a new task state after an allowed transition."""

        if target not in _ALLOWED_TASK_TRANSITIONS[self.status]:
            raise ProjectExecutionError(
                "invalid task transition: "
                f"{self.status.value} -> {target.value}"
            )

        started_at = self.started_at
        finished_at = self.finished_at
        attempts = self.attempts

        if target is ProjectTaskStatus.RUNNING:
            attempts += 1
            started_at = now
            finished_at = None

        if target in TERMINAL_TASK_STATUSES:
            finished_at = now

        return replace(
            self,
            status=target,
            attempts=attempts,
            started_at=started_at,
            finished_at=finished_at,
            last_error=error,
        )


@dataclass(frozen=True, slots=True)
class ProjectRunState:
    """Persistent state for one autonomous project execution."""

    run_id: str
    project_id: str
    repository_path: str
    status: ProjectRunStatus
    created_at: float
    updated_at: float
    version: int = 1
    workflow_id: str | None = None
    tasks: Mapping[str, ProjectTaskRuntimeState] = field(
        default_factory=dict
    )
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ProjectExecutionError(
                "run_id must not be empty"
            )

        if not self.project_id.strip():
            raise ProjectExecutionError(
                "project_id must not be empty"
            )

        if not self.repository_path.strip():
            raise ProjectExecutionError(
                "repository_path must not be empty"
            )

        if self.version < 1:
            raise ProjectExecutionError(
                "version must be at least one"
            )

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        repository_path: str,
        now: float,
        workflow_id: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> ProjectRunState:
        """Create a new uniquely identified project run."""

        return cls(
            run_id=f"run-{uuid4().hex}",
            project_id=project_id,
            repository_path=repository_path,
            status=ProjectRunStatus.CREATED,
            created_at=now,
            updated_at=now,
            workflow_id=workflow_id,
            metadata=dict(metadata or {}),
        )

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_RUN_STATUSES

    def transition(
        self,
        target: ProjectRunStatus,
        *,
        now: float,
    ) -> ProjectRunState:
        """Return a new run state after an allowed transition."""

        if target not in _ALLOWED_RUN_TRANSITIONS[self.status]:
            raise ProjectExecutionError(
                "invalid run transition: "
                f"{self.status.value} -> {target.value}"
            )

        return replace(
            self,
            status=target,
            updated_at=now,
            version=self.version + 1,
        )

    def with_task(
        self,
        task: ProjectTaskRuntimeState,
        *,
        now: float,
    ) -> ProjectRunState:
        """Add or replace one task state immutably."""

        tasks = dict(self.tasks)
        tasks[task.task_id] = task

        return replace(
            self,
            tasks=tasks,
            updated_at=now,
            version=self.version + 1,
        )


@dataclass(frozen=True, slots=True)
class ProjectRunEvent:
    """Immutable project execution audit record."""

    sequence: int
    run_id: str
    kind: ProjectRunEventKind
    occurred_at: float
    task_id: str | None = None
    detail: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ProjectExecutionError(
                "event sequence must be at least one"
            )

        if not self.run_id.strip():
            raise ProjectExecutionError(
                "event run_id must not be empty"
            )


@dataclass(frozen=True, slots=True)
class ProjectRunSnapshot:
    """Persistent state and audit history for one project run."""

    state: ProjectRunState
    events: tuple[ProjectRunEvent, ...]
