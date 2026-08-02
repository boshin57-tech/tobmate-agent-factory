from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field

from .execution_audit_models import (
    AuditEventType,
)


class GovernanceHistoryEvent(BaseModel):
    """
    Immutable governance lifecycle event.
    """

    event_id: str

    run_id: str
    step_id: str

    event_type: AuditEventType

    message: str

    created_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    metadata: dict[str, str] = (
        Field(default_factory=dict)
    )


class GovernanceHistoryStore:
    """
    Stores execution governance timeline.

    The store provides append-only behavior:
    existing events are never modified.
    """

    def __init__(self) -> None:
        self._events: list[
            GovernanceHistoryEvent
        ] = []

    def append(
        self,
        *,
        run_id: str,
        step_id: str,
        event_type: AuditEventType,
        message: str,
        metadata: dict[str, str] | None = None,
    ) -> GovernanceHistoryEvent:

        event = GovernanceHistoryEvent(
            event_id=str(uuid4()),
            run_id=run_id,
            step_id=step_id,
            event_type=event_type,
            message=message,
            metadata=(
                metadata or {}
            ),
        )

        self._events.append(
            event
        )

        return event

    def timeline(
        self,
        *,
        run_id: str | None = None,
    ) -> tuple[
        GovernanceHistoryEvent,
        ...
    ]:

        if run_id is None:
            return tuple(
                self._events
            )

        return tuple(
            event
            for event in self._events
            if event.run_id == run_id
        )

    def find_step_history(
        self,
        *,
        run_id: str,
        step_id: str,
    ) -> tuple[
        GovernanceHistoryEvent,
        ...
    ]:

        return tuple(
            event
            for event in self._events
            if (
                event.run_id == run_id
                and event.step_id == step_id
            )
        )

    @property
    def count(self) -> int:
        return len(
            self._events
        )
