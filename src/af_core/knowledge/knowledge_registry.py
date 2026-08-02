from __future__ import annotations

from .knowledge_models import (
    KnowledgeRecord,
    KnowledgeQuery,
)


class KnowledgeRegistryEngine:
    """
    Central registry for reusable
    agent knowledge assets.
    """

    def __init__(self) -> None:

        self._records: list[
            KnowledgeRecord
        ] = []


    def register(
        self,
        record: KnowledgeRecord,
    ) -> KnowledgeRecord:

        self._records.append(
            record
        )

        return record


    def get(
        self,
        knowledge_id: str,
    ) -> KnowledgeRecord | None:

        for record in self._records:

            if record.knowledge_id == knowledge_id:
                return record

        return None


    def search(
        self,
        query: KnowledgeQuery,
    ) -> tuple[
        KnowledgeRecord,
        ...
    ]:

        results = []

        for record in self._records:

            if (
                query.knowledge_type
                is not None
                and record.knowledge_type
                != query.knowledge_type
            ):
                continue


            if (
                query.keyword
                is not None
            ):

                keyword = (
                    query.keyword.lower()
                )

                text = (
                    record.title
                    + " "
                    + record.description
                ).lower()


                if keyword not in text:
                    continue


            results.append(
                record
            )


            if len(results) >= query.limit:
                break


        return tuple(results)


    def increment_usage(
        self,
        knowledge_id: str,
    ) -> None:

        record = self.get(
            knowledge_id
        )

        if record is not None:

            record.usage_count += 1


    def all_records(
        self,
    ) -> tuple[
        KnowledgeRecord,
        ...
    ]:

        return tuple(
            self._records
        )


    @property
    def count(
        self,
    ) -> int:

        return len(
            self._records
        )
