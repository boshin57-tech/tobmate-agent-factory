from af_core.dashboard.dashboard_service import (
    DashboardService,
)

from af_core.dashboard.dashboard_models import (
    DashboardProject,
    DashboardAgent,
)



def test_dashboard_snapshot():

    service = (
        DashboardService()
    )


    snapshot = (
        service.get_snapshot(
            projects=[
                DashboardProject(
                    project_id="001",
                    project_name=
                    "TOBMATE GSOS",
                    status="active",
                )
            ],

            agents=[
                DashboardAgent(
                    agent_id="agent-001",
                    agent_name=
                    "Spatial Agent",
                    status="active",
                    capabilities=[
                        "GSAP"
                    ],
                )
            ],
        )
    )


    assert (
        snapshot.health.status
        ==
        "healthy"
    )


    assert (
        snapshot.health.active_projects
        ==
        1
    )


    assert (
        snapshot.health.active_agents
        ==
        1
    )
