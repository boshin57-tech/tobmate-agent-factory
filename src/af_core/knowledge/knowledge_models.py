from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class KnowledgeType:

    LESSON = "lesson"

    PATTERN = "pattern"

    ARCHITECTURE = "architecture"

    CODE = "code"

    ADR = "adr"

    SOLUTION = "solution"


class KnowledgeRecord(BaseModel):

    knowledge_id: str = Field(
        default_factory=lambda: str(uuid4())
    )

    knowledge_type: str

    title: str

    description: str

    source_id: str

    version: int = 1

    usage_count: int = 0

    created_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    metadata: dict[str, str] = Field(
        default_factory=dict
    )


class KnowledgeQuery(BaseModel):

    knowledge_type: str | None = None

    keyword: str | None = None

    limit: int = 10
