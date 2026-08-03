from __future__ import annotations

from .team_models import AgentTeam


class TeamRepository:
    """
    In-memory repository for generated Agent teams.

    A persistent adapter can later replace this repository without
    changing the Team Builder contract.
    """

    def __init__(self) -> None:
        self._teams: dict[
            str,
            AgentTeam,
        ] = {}

    def save(
        self,
        team: AgentTeam,
    ) -> AgentTeam:
        if team.team_id in self._teams:
            raise ValueError(
                "team already exists"
            )

        self._teams[team.team_id] = team

        return team

    def get(
        self,
        team_id: str,
    ) -> AgentTeam | None:
        return self._teams.get(
            team_id
        )

    def by_workspace(
        self,
        workspace_id: str,
    ) -> tuple[AgentTeam, ...]:
        return tuple(
            team
            for team in self._teams.values()
            if team.workspace_id == workspace_id
        )

    def all(
        self,
    ) -> tuple[AgentTeam, ...]:
        return tuple(
            self._teams.values()
        )

    @property
    def count(self) -> int:
        return len(self._teams)
