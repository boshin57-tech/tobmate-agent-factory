from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from .worktree import GitWorktreeService


_SAFE_ID = re.compile(r"[^A-Za-z0-9._-]+")


class WorkspaceRecord(BaseModel):
    project_id: str
    run_id: str
    source_repository: str
    workspace_path: str
    branch: str
    base_revision: str


class WorkspaceManager:
    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace_root = (
            Path(workspace_root).expanduser().resolve()
        )
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        *,
        source_repository: str | Path,
        project_id: str,
        run_id: str,
        base_revision: str = "HEAD",
    ) -> WorkspaceRecord:
        safe_project = self._safe_identifier(project_id)
        safe_run = self._safe_identifier(run_id)

        destination = (
            self.workspace_root
            / safe_project
            / safe_run
            / "repo"
        )

        branch = f"af/{safe_project}/{safe_run}"
        service = GitWorktreeService(source_repository)

        worktree = service.create(
            destination=destination,
            branch=branch,
            base_revision=base_revision,
        )

        return WorkspaceRecord(
            project_id=project_id,
            run_id=run_id,
            source_repository=str(service.source_repository),
            workspace_path=str(worktree.path),
            branch=worktree.branch,
            base_revision=worktree.base_revision,
        )

    def status(self, record: WorkspaceRecord) -> list[str]:
        service = GitWorktreeService(record.source_repository)
        return service.status(record.workspace_path)

    def diff(self, record: WorkspaceRecord) -> str:
        service = GitWorktreeService(record.source_repository)
        return service.diff(record.workspace_path)

    def cleanup(
        self,
        record: WorkspaceRecord,
        *,
        force: bool = False,
    ) -> None:
        service = GitWorktreeService(record.source_repository)
        service.remove(record.workspace_path, force=force)

    def _safe_identifier(self, value: str) -> str:
        normalized = _SAFE_ID.sub("-", value).strip("-.")

        if not normalized:
            raise ValueError(f"Invalid identifier: {value!r}")

        return normalized
