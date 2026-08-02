from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field

from .lessons_learned_store import (
    LessonsLearnedStore,
)

from .pattern_update_engine import (
    PatternUpdateEngine,
)


class KnowledgeFeedbackSnapshot(BaseModel):
    snapshot_id: str

    lesson_count: int

    pattern_count: int

    created_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    metadata: dict[str, str] = (
        Field(default_factory=dict)
    )


class KnowledgeFeedbackEngine:
    """
    Connects learned experience back into
    Agent Factory improvement loop.
    """

    def __init__(
        self,
        *,
        lessons_store: LessonsLearnedStore,
        pattern_engine: PatternUpdateEngine,
    ) -> None:

        self.lessons_store = (
            lessons_store
        )

        self.pattern_engine = (
            pattern_engine
        )

        self._snapshots: list[
            KnowledgeFeedbackSnapshot
        ] = []

    def generate_snapshot(
        self,
    ) -> KnowledgeFeedbackSnapshot:

        snapshot = (
            KnowledgeFeedbackSnapshot(
                snapshot_id=str(uuid4()),
                lesson_count=(
                    self.lessons_store.count
                ),
                pattern_count=(
                    self.pattern_engine.count
                ),
            )
        )

        self._snapshots.append(
            snapshot
        )

        return snapshot

    def latest(
        self,
    ) -> KnowledgeFeedbackSnapshot | None:

        if not self._snapshots:
            return None

        return self._snapshots[-1]

    def snapshots(
        self,
    ) -> tuple[
        KnowledgeFeedbackSnapshot,
        ...
    ]:

        return tuple(
            self._snapshots
        )
