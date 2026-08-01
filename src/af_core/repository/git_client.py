from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


class GitError(RuntimeError):
    """Raised when a Git command fails."""


@dataclass(frozen=True)
class GitResult:
    args: tuple[str, ...]
    stdout: str
    stderr: str
    returncode: int


class GitClient:
    """Restricted Git command wrapper."""

    def __init__(self, repository_path: str | Path) -> None:
        self.repository_path = Path(repository_path).expanduser().resolve()

        if not self.repository_path.is_dir():
            raise ValueError(
                f"Repository path does not exist: {self.repository_path}"
            )

        if not (self.repository_path / ".git").exists():
            result = self.run(
                ["rev-parse", "--is-inside-work-tree"],
                check=False,
            )
            if result.returncode != 0:
                raise ValueError(
                    f"Not a Git repository: {self.repository_path}"
                )

    def run(
        self,
        args: Sequence[str],
        *,
        check: bool = True,
        timeout: int = 30,
    ) -> GitResult:
        command = ["git", "-C", str(self.repository_path), *args]

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitError(
                f"Git command timed out after {timeout}s: {' '.join(command)}"
            ) from exc

        result = GitResult(
            args=tuple(args),
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
            returncode=completed.returncode,
        )

        if check and result.returncode != 0:
            detail = result.stderr or result.stdout or "unknown Git error"
            raise GitError(
                f"Git command failed: git {' '.join(args)}: {detail}"
            )

        return result

    def branch(self) -> str:
        return self.run(["branch", "--show-current"]).stdout

    def head_commit(self) -> str:
        return self.run(["rev-parse", "HEAD"]).stdout

    def head_summary(self) -> str:
        return self.run(["log", "-1", "--oneline"]).stdout

    def status_porcelain(self) -> list[str]:
        output = self.run(
            ["status", "--porcelain=v1", "--untracked-files=all"]
        ).stdout
        return output.splitlines() if output else []

    def tracked_files(self) -> list[str]:
        output = self.run(["ls-files"]).stdout
        return output.splitlines() if output else []

    def top_level(self) -> Path:
        return Path(
            self.run(["rev-parse", "--show-toplevel"]).stdout
        ).resolve()

    def branch_exists(self, branch_name: str) -> bool:
        result = self.run(
            [
                "show-ref",
                "--verify",
                "--quiet",
                f"refs/heads/{branch_name}",
            ],
            check=False,
        )
        return result.returncode == 0

    def worktree_list(self) -> list[dict[str, str]]:
        output = self.run(["worktree", "list", "--porcelain"]).stdout
        records: list[dict[str, str]] = []
        current: dict[str, str] = {}

        for line in output.splitlines():
            if not line:
                if current:
                    records.append(current)
                    current = {}
                continue

            key, _, value = line.partition(" ")
            current[key] = value

        if current:
            records.append(current)

        return records
