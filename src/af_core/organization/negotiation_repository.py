from __future__ import annotations

from .negotiation_models import (
    NegotiationSession,
)


class NegotiationRepository:
    """
    In-memory repository for Agent negotiation sessions.
    """

    def __init__(self) -> None:
        self._sessions: dict[
            str,
            NegotiationSession,
        ] = {}

    def save(
        self,
        session: NegotiationSession,
    ) -> NegotiationSession:
        if (
            session.session_id
            in self._sessions
        ):
            raise ValueError(
                "negotiation session already exists"
            )

        self._sessions[
            session.session_id
        ] = session

        return session

    def replace(
        self,
        session: NegotiationSession,
    ) -> NegotiationSession:
        if (
            session.session_id
            not in self._sessions
        ):
            raise ValueError(
                "negotiation session does not exist"
            )

        self._sessions[
            session.session_id
        ] = session

        return session

    def get(
        self,
        session_id: str,
    ) -> NegotiationSession | None:
        return self._sessions.get(
            session_id
        )

    def by_workspace(
        self,
        workspace_id: str,
    ) -> tuple[
        NegotiationSession,
        ...
    ]:
        return tuple(
            session
            for session
            in self._sessions.values()
            if (
                session.workspace_id
                == workspace_id
            )
        )

    def by_team(
        self,
        team_id: str,
    ) -> tuple[
        NegotiationSession,
        ...
    ]:
        return tuple(
            session
            for session
            in self._sessions.values()
            if session.team_id == team_id
        )

    def all(
        self,
    ) -> tuple[
        NegotiationSession,
        ...
    ]:
        return tuple(
            self._sessions.values()
        )

    @property
    def count(self) -> int:
        return len(
            self._sessions
        )
