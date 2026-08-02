from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class PlanningObjective(BaseModel):

    objective_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    name: str

    description: str

    priority: int = 1



class ImprovementTarget(BaseModel):

    target_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    component: str

    current_state: str

    desired_state: str



class AutonomousPlan(BaseModel):

    plan_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    project_name: str

    objectives: list[
        PlanningObjective
    ]

    improvements: list[
        ImprovementTarget
    ]

    created_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )
