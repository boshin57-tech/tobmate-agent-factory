from __future__ import annotations

from .workspace_models import (
    Workspace,
)


class WorkspaceRegistry:
    """
    Stores active project workspaces.
    """


    def __init__(self) -> None:

        self._workspaces: dict[
            str,
            Workspace
        ] = {}



    def register(
        self,
        workspace: Workspace,
    ) -> Workspace:

        if (
            workspace.workspace_id
            in self._workspaces
        ):
            raise ValueError(
                "Workspace already exists"
            )


        self._workspaces[
            workspace.workspace_id
        ] = workspace


        return workspace



    def get(
        self,
        workspace_id: str,
    ) -> Workspace | None:

        return self._workspaces.get(
            workspace_id
        )



    def all(
        self,
    ) -> tuple[Workspace, ...]:

        return tuple(
            self._workspaces.values()
        )



    @property
    def count(
        self,
    ) -> int:

        return len(
            self._workspaces
        )
