from __future__ import annotations

from .dashboard_models import (
    DashboardSnapshot,
    DashboardHealth,
)


class DashboardSnapshotBuilder:
    """
    Creates operational dashboard view.
    """


    def build(
        self,
        projects=None,
        agents=None,
    ) -> DashboardSnapshot:


        projects = (
            projects
            or []
        )

        agents = (
            agents
            or []
        )


        return DashboardSnapshot(

            projects=projects,

            agents=agents,

            health=
            DashboardHealth(

                status="healthy",

                active_projects=
                len(projects),

                active_agents=
                len(agents),
            ),
        )
