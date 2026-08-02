from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class WorkspaceStatus:

    ACTIVE = "active"

    PAUSED = "paused"

    COMPLETED = "completed"



class Workspace(BaseModel):

    workspace_id: str = Field(
        default_factory=lambda:
        str(uuid4())
    )

    project_name: str

    description: str

    status: str = (
        WorkspaceStatus.ACTIVE
    )

    agents: list[str] = Field(
        default_factory=list
    )

    artifacts: list[str] = Field(
        default_factory=list
    )

    knowledge_scope: list[str] = Field(
        default_factory=list
    )

    created_at: datetime = Field(
        default_factory=lambda:
        datetime.now(timezone.utc)
    )
