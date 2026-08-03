from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from .task_coordination_models import (
    CoordinatedTask,
    TaskPriority,
)


class TaskDependencyNode(BaseModel):
    task_id: str

    dependencies: set[str] = Field(
        default_factory=set
    )

    dependents: set[str] = Field(
        default_factory=set
    )

    depth: int = 0

    estimated_duration_minutes: int = 0

    priority: TaskPriority = (
        TaskPriority.NORMAL
    )

    @field_validator("task_id")
    @classmethod
    def validate_task_id(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "task_id must not be empty"
            )

        return normalized


class TaskDependencyGraph(BaseModel):
    workflow_id: str

    nodes: dict[
        str,
        TaskDependencyNode,
    ] = Field(
        default_factory=dict
    )

    topological_order: list[str] = Field(
        default_factory=list
    )

    execution_waves: list[
        list[str]
    ] = Field(
        default_factory=list
    )

    critical_path: list[str] = Field(
        default_factory=list
    )

    critical_path_duration_minutes: int = 0

    has_cycle: bool = False

    cycle_task_ids: list[str] = Field(
        default_factory=list
    )


class TaskExecutionWave(BaseModel):
    wave_number: int

    task_ids: list[str] = Field(
        default_factory=list
    )

    parallel_task_ids: list[str] = Field(
        default_factory=list
    )

    exclusive_task_ids: list[str] = Field(
        default_factory=list
    )

    estimated_duration_minutes: int = 0

    @field_validator("wave_number")
    @classmethod
    def validate_wave_number(
        cls,
        value: int,
    ) -> int:
        if value < 0:
            raise ValueError(
                "wave_number must not be negative"
            )

        return value


class ParallelSchedule(BaseModel):
    workflow_id: str

    waves: list[
        TaskExecutionWave
    ] = Field(
        default_factory=list
    )

    total_task_count: int = 0

    maximum_parallelism: int = 0

    estimated_duration_minutes: int = 0

    critical_path: list[str] = Field(
        default_factory=list
    )

    critical_path_duration_minutes: int = 0


class ReadyTaskRanking(BaseModel):
    task_id: str

    priority_rank: int

    dependency_depth: int

    dependent_count: int

    estimated_duration_minutes: int

    scheduling_score: float


class ReadyTaskQueue(BaseModel):
    workflow_id: str

    ranked_tasks: list[
        ReadyTaskRanking
    ] = Field(
        default_factory=list
    )

    @property
    def task_ids(self) -> list[str]:
        return [
            item.task_id
            for item in self.ranked_tasks
        ]


class GraphValidationResult(BaseModel):
    valid: bool

    unknown_dependencies: dict[
        str,
        list[str],
    ] = Field(
        default_factory=dict
    )

    self_dependencies: list[str] = Field(
        default_factory=list
    )

    duplicate_task_ids: list[str] = Field(
        default_factory=list
    )

    cycle_task_ids: list[str] = Field(
        default_factory=list
    )

    reasons: list[str] = Field(
        default_factory=list
    )


class TaskGraphBuildRequest(BaseModel):
    workflow_id: str

    tasks: list[
        CoordinatedTask
    ] = Field(
        default_factory=list
    )
