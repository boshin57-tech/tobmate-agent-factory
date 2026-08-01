from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgeRecord(BaseModel):
    id: str = Field(
        default_factory=lambda: f"knw_{uuid4().hex}"
    )
    category: str
    title: str
    summary: str
    repository_fingerprint: str | None = None
    tags: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=utc_now)


class KnowledgeStoreError(RuntimeError):
    """Raised when a knowledge record cannot be stored."""


_SAFE_PART = re.compile(r"[^A-Za-z0-9._-]+")


class FileKnowledgeStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, record: KnowledgeRecord) -> Path:
        category = self._safe_part(record.category)
        target_dir = self.root / category
        target_dir.mkdir(parents=True, exist_ok=True)

        target = target_dir / f"{record.id}.json"

        if target.exists():
            raise KnowledgeStoreError(
                f"Knowledge record already exists: {record.id}"
            )

        temporary = target.with_suffix(".json.tmp")
        payload = record.model_dump(
            mode="json",
        )

        temporary.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)

        return target

    def get(
        self,
        category: str,
        record_id: str,
    ) -> KnowledgeRecord:
        target = (
            self.root
            / self._safe_part(category)
            / f"{self._safe_part(record_id)}.json"
        )

        if not target.is_file():
            raise KnowledgeStoreError(
                f"Knowledge record not found: {record_id}"
            )

        return KnowledgeRecord.model_validate_json(
            target.read_text(encoding="utf-8")
        )

    def list(
        self,
        category: str | None = None,
    ) -> list[KnowledgeRecord]:
        if category is None:
            paths = sorted(self.root.glob("*/*.json"))
        else:
            paths = sorted(
                (
                    self.root
                    / self._safe_part(category)
                ).glob("*.json")
            )

        return [
            KnowledgeRecord.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            for path in paths
        ]

    def search(
        self,
        *,
        text: str,
        category: str | None = None,
        repository_fingerprint: str | None = None,
        limit: int = 20,
    ) -> list[KnowledgeRecord]:
        query = text.strip().lower()

        if not query:
            return []

        scored: list[tuple[int, KnowledgeRecord]] = []

        for record in self.list(category):
            if (
                repository_fingerprint is not None
                and record.repository_fingerprint
                != repository_fingerprint
            ):
                continue

            searchable = " ".join(
                [
                    record.title,
                    record.summary,
                    *record.tags,
                ]
            ).lower()

            score = searchable.count(query)

            if score > 0:
                scored.append((score, record))

        scored.sort(
            key=lambda item: (
                -item[0],
                -item[1].confidence,
                item[1].created_at,
            )
        )

        return [
            record
            for _score, record in scored[:limit]
        ]

    def _safe_part(self, value: str) -> str:
        normalized = _SAFE_PART.sub("-", value).strip("-.")

        if not normalized:
            raise KnowledgeStoreError(
                f"Invalid knowledge path value: {value!r}"
            )

        return normalized
