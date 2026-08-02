from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field

from .learning_models import (
    LearningEventType,
)

from .lessons_learned_store import (
    LessonRecord,
)


class PatternType:
    SUCCESS = "success"
    FAILURE = "failure"
    RECOVERY = "recovery"


class AgentPattern(BaseModel):

    pattern_id: str

    pattern_type: str

    source_lesson_id: str

    description: str

    usage_count: int = 0

    version: int = 1

    created_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    metadata: dict[str, str] = (
        Field(default_factory=dict)
    )


class PatternUpdateEngine:

    def __init__(self) -> None:
        self._patterns: list[
            AgentPattern
        ] = []

    def update(
        self,
        lesson: LessonRecord,
    ) -> AgentPattern:

        pattern_type = (
            PatternType.FAILURE
        )

        if (
            lesson.category
            is LearningEventType.SUCCESS_PATTERN
        ):
            pattern_type = (
                PatternType.SUCCESS
            )

        elif (
            lesson.category
            is LearningEventType.RECOVERY_LESSON
        ):
            pattern_type = (
                PatternType.RECOVERY
            )

        pattern = AgentPattern(
            pattern_id=str(uuid4()),
            pattern_type=pattern_type,
            source_lesson_id=(
                lesson.lesson_id
            ),
            description=(
                lesson.summary
            ),
        )

        self._patterns.append(
            pattern
        )

        return pattern

    def patterns(
        self,
    ) -> tuple[AgentPattern, ...]:

        return tuple(
            self._patterns
        )

    def find_by_type(
        self,
        pattern_type: str,
    ) -> tuple[AgentPattern, ...]:

        return tuple(
            pattern
            for pattern
            in self._patterns
            if pattern.pattern_type
            == pattern_type
        )

    @property
    def count(self) -> int:

        return len(
            self._patterns
        )
