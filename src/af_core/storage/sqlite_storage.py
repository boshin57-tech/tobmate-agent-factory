from __future__ import annotations

import json
import sqlite3

from .storage_interface import (
    KnowledgeStorage,
)

from .storage_models import (
    StoredKnowledge,
)


class SQLiteKnowledgeStorage(
    KnowledgeStorage
):
    """
    SQLite persistent storage adapter.
    """


    def __init__(
        self,
        database_path: str = "knowledge.db",
    ) -> None:

        self.connection = sqlite3.connect(
            database_path
        )

        self._create_table()



    def _create_table(
        self,
    ) -> None:

        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge (
                knowledge_id TEXT PRIMARY KEY,
                knowledge_type TEXT,
                title TEXT,
                description TEXT,
                source_id TEXT,
                version INTEGER,
                usage_count INTEGER,
                created_at TEXT,
                metadata TEXT
            )
            """
        )

        self.connection.commit()



    def save(
        self,
        knowledge:
        StoredKnowledge,
    ) -> None:

        self.connection.execute(
            """
            INSERT OR REPLACE INTO knowledge
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                knowledge.knowledge_id,
                knowledge.knowledge_type,
                knowledge.title,
                knowledge.description,
                knowledge.source_id,
                knowledge.version,
                knowledge.usage_count,
                knowledge.created_at.isoformat(),
                json.dumps(
                    knowledge.metadata
                ),
            ),
        )

        self.connection.commit()



    def get(
        self,
        knowledge_id: str,
    ) -> StoredKnowledge | None:

        cursor = (
            self.connection.execute(
                """
                SELECT *
                FROM knowledge
                WHERE knowledge_id = ?
                """,
                (knowledge_id,),
            )
        )


        row = cursor.fetchone()


        if row is None:
            return None


        return StoredKnowledge(
            knowledge_id=row[0],
            knowledge_type=row[1],
            title=row[2],
            description=row[3],
            source_id=row[4],
            version=row[5],
            usage_count=row[6],
            created_at=row[7],
            metadata=json.loads(row[8]),
        )



    def all(
        self,
    ) -> list[StoredKnowledge]:

        cursor = self.connection.execute(
            """
            SELECT *
            FROM knowledge
            """
        )

        return [
            StoredKnowledge(
                knowledge_id=row[0],
                knowledge_type=row[1],
                title=row[2],
                description=row[3],
                source_id=row[4],
                version=row[5],
                usage_count=row[6],
                created_at=row[7],
                metadata=json.loads(row[8]),
            )
            for row in cursor.fetchall()
        ]
