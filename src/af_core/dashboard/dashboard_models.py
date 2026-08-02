from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field



class DashboardProject(BaseModel):

    project_id: str

    project_name: str

    status: str



class DashboardAgent(BaseModel):

    agent_id: str

    agent_name: str

    status: str

    capabilities: list[str]



class DashboardHealth(BaseModel):

    status: str

    active_projects: int

    active_agents: int



class DashboardSnapshot(BaseModel):

    generated_at: datetime = Field(
        default_factory=lambda:
        datetime.now(timezone.utc)
    )

    projects: list[
        DashboardProject
    ]

    agents: list[
        DashboardAgent
    ]

    health: DashboardHealth
