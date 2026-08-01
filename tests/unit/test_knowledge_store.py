from pathlib import Path

import pytest

from af_core.knowledge.store import (
    FileKnowledgeStore,
    KnowledgeRecord,
    KnowledgeStoreError,
)


def test_knowledge_store_saves_gets_and_lists(
    tmp_path: Path,
) -> None:
    store = FileKnowledgeStore(tmp_path / "knowledge")

    record = KnowledgeRecord(
        category="patterns",
        title="Safe worktree changes",
        summary="Perform changes only in an isolated worktree.",
        repository_fingerprint="repo-1",
        tags=["git", "worktree"],
        evidence_refs=["validation.json"],
    )

    path = store.save(record)

    assert path.is_file()
    assert store.get("patterns", record.id) == record
    assert store.list("patterns") == [record]


def test_knowledge_store_rejects_duplicate_id(
    tmp_path: Path,
) -> None:
    store = FileKnowledgeStore(tmp_path / "knowledge")

    record = KnowledgeRecord(
        id="knw_fixed",
        category="patterns",
        title="Pattern",
        summary="Summary",
    )

    store.save(record)

    with pytest.raises(KnowledgeStoreError):
        store.save(record)


def test_knowledge_store_searches_by_text_and_repository(
    tmp_path: Path,
) -> None:
    store = FileKnowledgeStore(tmp_path / "knowledge")

    matching = KnowledgeRecord(
        category="failures",
        title="Pytest timeout",
        summary="Increase timeout only after confirming no deadlock.",
        repository_fingerprint="repo-a",
        tags=["pytest"],
    )

    other = KnowledgeRecord(
        category="failures",
        title="Build error",
        summary="Cargo build failed.",
        repository_fingerprint="repo-b",
    )

    store.save(matching)
    store.save(other)

    result = store.search(
        text="pytest",
        category="failures",
        repository_fingerprint="repo-a",
    )

    assert result == [matching]
