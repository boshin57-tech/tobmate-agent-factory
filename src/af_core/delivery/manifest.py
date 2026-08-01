from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()

    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)

    return digest.hexdigest()


class DeliveryArtifact(BaseModel):
    name: str
    relative_path: str
    sha256: str
    size_bytes: int


class DeliveryManifest(BaseModel):
    delivery_id: str = Field(
        default_factory=lambda: f"dlv_{uuid4().hex}"
    )
    project_id: str
    run_id: str
    repository_path: str
    base_revision: str
    branch: str
    changed_files: list[str] = Field(default_factory=list)
    validation_passed: bool
    review_decision: str
    completion_status: str
    artifacts: list[DeliveryArtifact] = Field(default_factory=list)
    known_risks: list[str] = Field(default_factory=list)
    recommended_commit_message: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
