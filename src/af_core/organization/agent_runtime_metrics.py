from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class AgentAvailabilityStatus(str, Enum):
    AVAILABLE = "available"
    BUSY = "busy"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    SUSPENDED = "suspended"


class AgentRuntimeMetrics(BaseModel):
    """
    Runtime operational metrics used during dynamic role selection.

    Ratios use the inclusive range 0.0 to 1.0.
    Scores use the inclusive range 0.0 to 100.0.
    """

    agent_id: str

    availability: AgentAvailabilityStatus = (
        AgentAvailabilityStatus.AVAILABLE
    )

    current_assignments: int = 0
    maximum_assignments: int = 1

    workload_ratio: float = 0.0

    success_rate: float = 1.0
    quality_score: float = 100.0
    reliability_score: float = 100.0

    average_response_ms: float = 0.0

    consecutive_failures: int = 0

    last_heartbeat_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    measured_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    metadata: dict[str, str] = Field(
        default_factory=dict
    )

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "agent_id must not be empty"
            )

        return normalized

    @field_validator(
        "current_assignments",
        "maximum_assignments",
        "consecutive_failures",
    )
    @classmethod
    def validate_non_negative_integer(
        cls,
        value: int,
    ) -> int:
        if value < 0:
            raise ValueError(
                "integer metric must not be negative"
            )

        return value

    @field_validator(
        "workload_ratio",
        "success_rate",
    )
    @classmethod
    def validate_ratio(
        cls,
        value: float,
    ) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError(
                "ratio must be between 0.0 and 1.0"
            )

        return value

    @field_validator(
        "quality_score",
        "reliability_score",
    )
    @classmethod
    def validate_percentage_score(
        cls,
        value: float,
    ) -> float:
        if not 0.0 <= value <= 100.0:
            raise ValueError(
                "score must be between 0 and 100"
            )

        return value

    @field_validator("average_response_ms")
    @classmethod
    def validate_response_time(
        cls,
        value: float,
    ) -> float:
        if value < 0:
            raise ValueError(
                "average_response_ms must not be negative"
            )

        return value

    def model_post_init(
        self,
        __context: object,
    ) -> None:
        if self.maximum_assignments < 1:
            raise ValueError(
                "maximum_assignments must be at least 1"
            )

        if (
            self.current_assignments
            > self.maximum_assignments
        ):
            raise ValueError(
                "current_assignments must not exceed "
                "maximum_assignments"
            )

    @property
    def has_capacity(self) -> bool:
        return (
            self.current_assignments
            < self.maximum_assignments
            and self.workload_ratio < 1.0
        )

    @property
    def operational(self) -> bool:
        return self.availability in {
            AgentAvailabilityStatus.AVAILABLE,
            AgentAvailabilityStatus.BUSY,
            AgentAvailabilityStatus.DEGRADED,
        }


class RuntimeScoringWeights(BaseModel):
    """
    Dynamic operational score weights.

    Positive values add suitability.
    Penalty values subtract suitability.
    """

    availability: float = 20.0
    capacity: float = 15.0
    low_workload: float = 15.0

    success_rate: float = 15.0
    quality: float = 10.0
    reliability: float = 10.0
    response_speed: float = 5.0

    busy_penalty: float = 5.0
    degraded_penalty: float = 12.0
    consecutive_failure_penalty: float = 3.0

    @field_validator("*")
    @classmethod
    def validate_weight(
        cls,
        value: float,
    ) -> float:
        if value < 0:
            raise ValueError(
                "runtime scoring weights "
                "must not be negative"
            )

        return value


class RuntimeScoreBreakdown(BaseModel):
    agent_id: str

    eligible: bool

    availability_score: float = 0.0
    capacity_score: float = 0.0
    workload_score: float = 0.0

    success_score: float = 0.0
    quality_score: float = 0.0
    reliability_score: float = 0.0
    response_score: float = 0.0

    penalty_score: float = 0.0

    total_score: float = 0.0

    reasons: list[str] = Field(
        default_factory=list
    )
