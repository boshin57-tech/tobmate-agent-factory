from __future__ import annotations

from .task_coordination_models import (
    TaskCoordinationWorkflow,
)


class TaskCoordinationRepository:
    """
    In-memory repository for coordinated multi-Agent workflows.
    """

    def __init__(self) -> None:
        self._workflows: dict[
            str,
            TaskCoordinationWorkflow,
        ] = {}

    def save(
        self,
        workflow: TaskCoordinationWorkflow,
    ) -> TaskCoordinationWorkflow:
        if workflow.workflow_id in self._workflows:
            raise ValueError(
                "coordination workflow already exists"
            )

        self._workflows[
            workflow.workflow_id
        ] = workflow

        return workflow

    def replace(
        self,
        workflow: TaskCoordinationWorkflow,
    ) -> TaskCoordinationWorkflow:
        if workflow.workflow_id not in self._workflows:
            raise ValueError(
                "coordination workflow does not exist"
            )

        self._workflows[
            workflow.workflow_id
        ] = workflow

        return workflow

    def get(
        self,
        workflow_id: str,
    ) -> TaskCoordinationWorkflow | None:
        return self._workflows.get(
            workflow_id
        )

    def by_workspace(
        self,
        workspace_id: str,
    ) -> tuple[
        TaskCoordinationWorkflow,
        ...
    ]:
        return tuple(
            workflow
            for workflow in self._workflows.values()
            if workflow.workspace_id == workspace_id
        )

    def by_team(
        self,
        team_id: str,
    ) -> tuple[
        TaskCoordinationWorkflow,
        ...
    ]:
        return tuple(
            workflow
            for workflow in self._workflows.values()
            if workflow.team_id == team_id
        )

    def all(
        self,
    ) -> tuple[
        TaskCoordinationWorkflow,
        ...
    ]:
        return tuple(
            self._workflows.values()
        )

    @property
    def count(self) -> int:
        return len(self._workflows)
