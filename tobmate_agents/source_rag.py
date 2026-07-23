from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_INDEX = Path("workspace/index/source_chunks.jsonl")

TOKEN_PATTERN = re.compile(
    r"[가-힣]{2,}|[A-Za-z][A-Za-z0-9_-]{1,}|\d+(?:\.\d+)*"
)


def tokenize(text: str) -> list[str]:
    return [
        token.lower()
        for token in TOKEN_PATTERN.findall(text)
    ]


class SourceRAG:
    def __init__(self, index_path: Path | str = DEFAULT_INDEX):
        self.index_path = Path(index_path)
        self.records: list[dict[str, Any]] = []

        if not self.index_path.exists():
            raise FileNotFoundError(
                f"Source index not found: {self.index_path}. "
                "Run scripts/build_source_index.py first."
            )

        with self.index_path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if line:
                    self.records.append(json.loads(line))

        self.document_frequency: Counter[str] = Counter()

        for record in self.records:
            terms = set(tokenize(record["text"]))
            self.document_frequency.update(terms)

        self.record_count = max(len(self.records), 1)

    def _idf(self, term: str) -> float:
        frequency = self.document_frequency.get(term, 0)

        return math.log(
            (self.record_count + 1) / (frequency + 1)
        ) + 1.0

    def search(
        self,
        query: str,
        limit: int = 8,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        query_terms = tokenize(query)

        if not query_terms:
            return []

        query_counts = Counter(query_terms)
        query_lower = query.lower()
        scored: list[tuple[float, dict[str, Any]]] = []

        for record in self.records:
            if category and record.get("category") != category:
                continue

            text = record["text"]
            text_lower = text.lower()
            text_counts = Counter(tokenize(text))
            score = 0.0

            for term, query_frequency in query_counts.items():
                term_frequency = text_counts.get(term, 0)

                if term_frequency:
                    score += (
                        (1.0 + math.log(term_frequency))
                        * self._idf(term)
                        * query_frequency
                    )

            if query_lower in text_lower:
                score += 12.0

            file_name_lower = record["file_name"].lower()

            for term in query_terms:
                if term in file_name_lower:
                    score += 2.5

            if score > 0:
                result = dict(record)
                result["score"] = round(score, 4)
                scored.append((score, result))

        scored.sort(
            key=lambda item: (
                item[0],
                -item[1]["document_number"],
            ),
            reverse=True,
        )

        return [record for _, record in scored[:limit]]

    def build_context(
        self,
        query: str,
        limit: int = 8,
        max_characters: int = 14000,
        category: str | None = None,
    ) -> str:
        results = self.search(
            query=query,
            limit=limit,
            category=category,
        )

        context_blocks: list[str] = []
        current_length = 0

        for result in results:
            block = (
                f"[SOURCE: {result['source_path']} | "
                f"CHUNK: {result['chunk_number']} | "
                f"SCORE: {result['score']}]\n"
                f"{result['text']}"
            )

            if current_length + len(block) > max_characters:
                break

            context_blocks.append(block)
            current_length += len(block)

        return "\n\n---\n\n".join(context_blocks)


def get_source_context(
    query: str,
    limit: int = 8,
    max_characters: int = 14000,
    category: str | None = None,
) -> str:
    rag = SourceRAG()

    return rag.build_context(
        query=query,
        limit=limit,
        max_characters=max_characters,
        category=category,
    )
