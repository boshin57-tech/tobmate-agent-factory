from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from af_core.repository.git_client import GitClient, GitError


_SAFE_BRANCH = re.compile(r"^[A-Za-z0-9._/-]+$")


@dataclass(frozen=True)
class Worktree:
    path: Path
    branch: str
    base_revision: str


class WorktreeError(RuntimeError):
    """Raised when an isolated worktree operation fails."""


class GitWorktreeService:
    def __init__(self, source_repository: str | Path) -> None:
        self.client = GitClient(source_repository)
        self.source_repository = self.client.top_level()

    def create(
        self,
        *,
        destination: str | Path,
        branch: str,
        base_revision: str = "HEAD",
    ) -> Worktree:
        destination_path = Path(destination).expanduser().resolve()

        self._validate_branch(branch)
        self._validate_destination(destination_path)

        if self.client.branch_exists(branch):
            raise WorktreeError(f"Branch already exists: {branch}")

        try:
            self.client.run(
                [
                    "worktree",
                    "add",
                    "-b",
                    branch,
                    str(destination_path),
                    base_revision,
                ],
                timeout=120,
            )
        except GitError as exc:
            raise WorktreeError(str(exc)) from exc

        return Worktree(
            path=destination_path,
            branch=branch,
            base_revision=self._resolve_revision(base_revision),
        )

    def remove(
        self,
        worktree_path: str | Path,
        *,
        force: bool = False,
    ) -> None:
        path = Path(worktree_path).expanduser().resolve()
        self._require_registered_worktree(path)

        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(path))

        try:
            self.client.run(args, timeout=120)
        except GitError as exc:
            raise WorktreeError(str(exc)) from exc

    def diff(self, worktree_path: str | Path) -> str:
        path = Path(worktree_path).expanduser().resolve()
        self._require_registered_worktree(path)
        return GitClient(path).run(["diff", "--binary"]).stdout

    def status(self, worktree_path: str | Path) -> list[str]:
        path = Path(worktree_path).expanduser().resolve()
        self._require_registered_worktree(path)
        return GitClient(path).status_porcelain()

    def _resolve_revision(self, revision: str) -> str:
        return self.client.run(
            ["rev-parse", revision]
        ).stdout

    def _validate_branch(self, branch: str) -> None:
        if not branch or not _SAFE_BRANCH.fullmatch(branch):
            raise WorktreeError(f"Unsafe branch name: {branch!r}")

        if branch.startswith("-") or ".." in branch:
            raise WorktreeError(f"Unsafe branch name: {branch!r}")

    def _validate_destination(self, destination: Path) -> None:
        source = self.source_repository

        if destination == source:
            raise WorktreeError(
                "Worktree destination cannot be the source repository."
            )

        if source in destination.parents:
            raise WorktreeError(
                "Worktree must not be created inside the source repository."
            )

        if destination.exists():
            if not destination.is_dir():
                raise WorktreeError(
                    f"Destination already exists: {destination}"
                )

            if any(destination.iterdir()):
                raise WorktreeError(
                    f"Destination is not empty: {destination}"
                )

    def _require_registered_worktree(self, path: Path) -> None:
        registered = {
            Path(item["worktree"]).resolve()
            for item in self.client.worktree_list()
            if "worktree" in item
        }

        if path not in registered:
            raise WorktreeError(
                f"Not a registered worktree: {path}"
            )
