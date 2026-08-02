from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class AgentStatus:

    ACTIVE = "active"

    INACTIVE = "inactive"



class AgentCapability(BaseModel):

    capability_id: str = Field(
        default_factory=lambda:
        str(uuid4())
    )

    agent_id: str

    agent_name: str

    capabilities: list[str] = Field(
        default_factory=list
    )

    supported_tasks: list[str] = Field(
        default_factory=list
    )

    skill_level: int = 1

    status: str = (
        AgentStatus.ACTIVE
    )

    version: int = 1

    created_at: datetime = Field(
        default_factory=lambda:
        datetime.now(timezone.utc)
    )
