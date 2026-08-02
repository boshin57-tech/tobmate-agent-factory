from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class MetricType:

    EXECUTION = "execution"

    TOKEN = "token"

    ERROR = "error"

    HEALTH = "health"



class ExecutionMetric(BaseModel):

    metric_id: str = Field(
        default_factory=lambda:
        str(uuid4())
    )

    project_id: str

    agent_id: str

    metric_type: str

    value: float

    unit: str

    created_at: datetime = Field(
        default_factory=lambda:
        datetime.now(timezone.utc)
    )

    metadata: dict[str, str] = Field(
        default_factory=dict
    )
