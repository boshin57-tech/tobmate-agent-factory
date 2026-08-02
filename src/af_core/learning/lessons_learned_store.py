from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field

from .learning_models import (
    LearningEvent,
    LearningEventType,
)


class LessonRecord(BaseModel):
    lesson_id: str

    learning_event_id: str

    category: LearningEventType

    summary: str

    reusable: bool = False

    created_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    metadata: dict[str, str] = (
        Field(default_factory=dict)
    )


class LessonsLearnedStore:
    """
    Persistent-style experience memory.

    Stores extracted lessons from
    execution history.
    """

    def __init__(self) -> None:
        self._lessons: list[
            LessonRecord
        ] = []

    def add(
        self,
        event: LearningEvent,
        *,
        reusable: bool = False,
        metadata: dict[str, str] | None = None,
    ) -> LessonRecord:

        lesson = LessonRecord(
            lesson_id=str(uuid4()),
            learning_event_id=(
                event.event_id
            ),
            category=(
                event.event_type
            ),
            summary=(
                event.summary
            ),
            reusable=reusable,
            metadata=(
                metadata or {}
            ),
        )

        self._lessons.append(
            lesson
        )

        return lesson

    def all(
        self,
    ) -> tuple[
        LessonRecord,
        ...
    ]:
        return tuple(
            self._lessons
        )

    def reusable(
        self,
    ) -> tuple[
        LessonRecord,
        ...
    ]:

        return tuple(
            lesson
            for lesson
            in self._lessons
            if lesson.reusable
        )

    def by_category(
        self,
        category: LearningEventType,
    ) -> tuple[
        LessonRecord,
        ...
    ]:

        return tuple(
            lesson
            for lesson
            in self._lessons
            if lesson.category is category
        )

    @property
    def count(self) -> int:
        return len(
            self._lessons
        )
