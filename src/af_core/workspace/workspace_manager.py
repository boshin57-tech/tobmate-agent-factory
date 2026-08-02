from __future__ import annotations

from .workspace_models import (
    Workspace,
)

from .workspace_registry import (
    WorkspaceRegistry,
)



class WorkspaceManager:
    """
    Manages isolated project
    execution environments.
    """


    def __init__(
        self,
        registry:
        WorkspaceRegistry | None = None,
    ) -> None:

        self.registry = (
            registry
            or WorkspaceRegistry()
        )



    def create_workspace(
        self,
        project_name: str,
        description: str,
    ) -> Workspace:


        workspace = Workspace(
            project_name=
            project_name,

            description=
            description,
        )


        return (
            self.registry
            .register(
                workspace
            )
        )



    def assign_agent(
        self,
        workspace_id: str,
        agent_name: str,
    ) -> Workspace:


        workspace = (
            self.registry.get(
                workspace_id
            )
        )


        if workspace is None:
            raise ValueError(
                "Workspace not found"
            )


        workspace.agents.append(
            agent_name
        )


        return workspace



    def add_artifact(
        self,
        workspace_id: str,
        artifact: str,
    ) -> Workspace:


        workspace = (
            self.registry.get(
                workspace_id
            )
        )


        if workspace is None:
            raise ValueError(
                "Workspace not found"
            )


        workspace.artifacts.append(
            artifact
        )


        return workspace
