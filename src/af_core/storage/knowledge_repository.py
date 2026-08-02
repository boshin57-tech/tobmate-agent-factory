from __future__ import annotations

from af_core.knowledge.knowledge_models import (
    KnowledgeRecord,
)

from .storage_models import (
    StoredKnowledge,
)

from .storage_interface import (
    KnowledgeStorage,
)


class KnowledgeRepository:
    """
    Connects Knowledge Engine
    with persistent storage.
    """


    def __init__(
        self,
        storage:
        KnowledgeStorage,
    ) -> None:

        self.storage = storage



    def save(
        self,
        record: KnowledgeRecord,
    ) -> None:

        self.storage.save(
            StoredKnowledge(
                knowledge_id=
                record.knowledge_id,

                knowledge_type=
                record.knowledge_type,

                title=
                record.title,

                description=
                record.description,

                source_id=
                record.source_id,

                version=
                record.version,

                usage_count=
                record.usage_count,

                created_at=
                record.created_at,

                metadata=
                record.metadata,
            )
        )



    def get(
        self,
        knowledge_id: str,
    ):

        return self.storage.get(
            knowledge_id
        )
