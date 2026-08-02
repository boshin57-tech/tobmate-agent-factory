from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class PatternCategory:

    EXECUTION = "execution"

    RECOVERY = "recovery"

    ARCHITECTURE = "architecture"

    TEAM = "team"

    DEPLOYMENT = "deployment"


class PatternRecord(BaseModel):

    pattern_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    name: str

    category: str

    description: str

    source_knowledge_id: str

    version: int = 1

    success_count: int = 0

    failure_count: int = 0

    usage_count: int = 0

    created_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    metadata: dict[str, str] = Field(
        default_factory=dict
    )


class PatternLibraryEngine:
    """
    Stores and manages reusable
    execution patterns.
    """


    def __init__(self) -> None:

        self._patterns: list[
            PatternRecord
        ] = []


    def register(
        self,
        pattern: PatternRecord,
    ) -> PatternRecord:

        self._patterns.append(
            pattern
        )

        return pattern


    def get(
        self,
        pattern_id: str,
    ) -> PatternRecord | None:

        for pattern in self._patterns:

            if pattern.pattern_id == pattern_id:
                return pattern

        return None


    def find_by_category(
        self,
        category: str,
    ) -> tuple[
        PatternRecord,
        ...
    ]:

        return tuple(
            pattern
            for pattern
            in self._patterns
            if pattern.category
            == category
        )


    def record_usage(
        self,
        pattern_id: str,
        success: bool,
    ) -> None:

        pattern = self.get(
            pattern_id
        )

        if pattern is None:
            return


        pattern.usage_count += 1


        if success:

            pattern.success_count += 1

        else:

            pattern.failure_count += 1


    def patterns(
        self,
    ) -> tuple[
        PatternRecord,
        ...
    ]:

        return tuple(
            self._patterns
        )


    @property
    def count(
        self,
    ) -> int:

        return len(
            self._patterns
        )
