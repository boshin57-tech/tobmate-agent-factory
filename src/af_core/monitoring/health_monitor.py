from __future__ import annotations

from pydantic import BaseModel


class SystemHealth(BaseModel):

    status: str

    active_agents: int

    active_workspaces: int

    message: str



class HealthMonitor:
    """
    Runtime health observer.
    """


    def check(
        self,
        active_agents: int = 0,
        active_workspaces: int = 0,
    ) -> SystemHealth:


        return SystemHealth(

            status="healthy",

            active_agents=
            active_agents,

            active_workspaces=
            active_workspaces,

            message=
            "Agent Factory runtime healthy",
        )
