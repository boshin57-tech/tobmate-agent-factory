from __future__ import annotations

from .dashboard_snapshot import (
    DashboardSnapshotBuilder,
)



class DashboardService:
    """
    Service layer for dashboard data.
    """


    def __init__(
        self,
        builder=None,
    ) -> None:

        self.builder = (
            builder
            or DashboardSnapshotBuilder()
        )



    def get_snapshot(
        self,
        projects=None,
        agents=None,
    ):

        return (
            self.builder.build(
                projects,
                agents,
            )
        )
