from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class ADRType:

    ARCHITECTURE = "architecture"

    SECURITY = "security"

    PERFORMANCE = "performance"

    TECHNOLOGY = "technology"

    GOVERNANCE = "governance"



class ADRRecord(BaseModel):

    adr_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    title: str

    decision_type: str

    context: str

    decision: str

    consequence: str

    related_ids: list[str] = Field(
        default_factory=list
    )

    version: int = 1

    created_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    metadata: dict[str, str] = Field(
        default_factory=dict
    )
