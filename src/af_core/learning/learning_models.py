from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class LearningEventType(StrEnum):
    SUCCESS_PATTERN = "success_pattern"
    FAILURE_PATTERN = "failure_pattern"
    PERFORMANCE_INSIGHT = "performance_insight"
    RECOVERY_LESSON = "recovery_lesson"


class LearningConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LearningEvent(BaseModel):
    event_id: str

    source_run_id: str
    source_step_id: str

    event_type: LearningEventType

    confidence: LearningConfidence = (
        LearningConfidence.MEDIUM
    )

    summary: str

    tags: tuple[str, ...] = ()

    metadata: dict[str, str] = (
        Field(default_factory=dict)
    )


class KnowledgeCandidate(BaseModel):
    candidate_id: str

    learning_event_id: str

    category: str

    content: str

    reusable: bool = False
