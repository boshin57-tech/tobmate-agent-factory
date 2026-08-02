from af_core.workspace.workspace_manager import (
    WorkspaceManager,
)


def test_workspace_creation():

    manager = (
        WorkspaceManager()
    )


    workspace = (
        manager.create_workspace(
            "TOBMATE GSOS",
            "Spatial OS Project",
        )
    )


    assert (
        workspace.project_name
        ==
        "TOBMATE GSOS"
    )


    assert (
        manager.registry.count
        ==
        1
    )



def test_agent_assignment():

    manager = (
        WorkspaceManager()
    )


    workspace = (
        manager.create_workspace(
            "Blockchain",
            "Sui Platform",
        )
    )


    manager.assign_agent(
        workspace.workspace_id,
        "Blockchain Agent",
    )


    assert (
        "Blockchain Agent"
        in workspace.agents
    )
