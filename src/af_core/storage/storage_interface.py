from __future__ import annotations

from abc import ABC, abstractmethod

from .storage_models import (
    StoredKnowledge,
)


class KnowledgeStorage(ABC):
    """
    Persistent knowledge storage contract.
    """


    @abstractmethod
    def save(
        self,
        knowledge: StoredKnowledge,
    ) -> None:
        ...


    @abstractmethod
    def get(
        self,
        knowledge_id: str,
    ) -> StoredKnowledge | None:
        ...


    @abstractmethod
    def all(
        self,
    ) -> list[StoredKnowledge]:
        ...
