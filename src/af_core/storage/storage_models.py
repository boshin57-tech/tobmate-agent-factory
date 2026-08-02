from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class StoredKnowledge(BaseModel):

    knowledge_id: str

    knowledge_type: str

    title: str

    description: str

    source_id: str

    version: int

    usage_count: int

    created_at: datetime

    metadata: dict[str, str]
