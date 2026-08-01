from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, Field

from .analyzer import RepositoryAnalysis


DEFAULT_MAX_FILE_BYTES = 64 * 1024
DEFAULT_MAX_TOTAL_BYTES = 256 * 1024

IGNORED_PARTS = {
    ".git",
    ".venv",
    ".venv-af-core",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "target",
    "dist",
    "build",
}

TEXT_SUFFIXES = {
    ".py",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".md",
    ".txt",
    ".rs",
    ".move",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".sh",
    ".go",
    ".java",
}


class ContextFile(BaseModel):
    path: str
    content: str
    size_bytes: int
    reason: str


class ContextPackage(BaseModel):
    objective: str
    repository_summary: str
    relevant_files: list[ContextFile] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    prior_knowledge: list[str] = Field(default_factory=list)
    omitted_files: list[str] = Field(default_factory=list)
    total_bytes: int = 0


@dataclass(frozen=True)
class ContextCandidate:
    path: Path
    score: int
    reason: str


class ContextBuilder:
    def __init__(
        self,
        *,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
        max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    ) -> None:
        if max_file_bytes <= 0:
            raise ValueError("max_file_bytes must be positive")

        if max_total_bytes <= 0:
            raise ValueError("max_total_bytes must be positive")

        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes

    def build(
        self,
        *,
        analysis: RepositoryAnalysis,
        objective: str,
        constraints: list[str] | None = None,
        prior_knowledge: list[str] | None = None,
        explicit_files: list[str] | None = None,
    ) -> ContextPackage:
        root = Path(analysis.repository_path).resolve()

        candidates = self._collect_candidates(
            root=root,
            objective=objective,
            analysis=analysis,
            explicit_files=explicit_files or [],
        )

        selected: list[ContextFile] = []
        omitted: list[str] = []
        total_bytes = 0

        for candidate in candidates:
            try:
                size = candidate.path.stat().st_size
            except OSError:
                omitted.append(str(candidate.path.relative_to(root)))
                continue

            relative = str(candidate.path.relative_to(root))

            if size > self.max_file_bytes:
                omitted.append(relative)
                continue

            if total_bytes + size > self.max_total_bytes:
                omitted.append(relative)
                continue

            try:
                content = candidate.path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                omitted.append(relative)
                continue

            selected.append(
                ContextFile(
                    path=relative,
                    content=content,
                    size_bytes=size,
                    reason=candidate.reason,
                )
            )
            total_bytes += size

        summary = (
            f"Repository: {analysis.repository_path}\n"
            f"Branch: {analysis.branch or '(detached)'}\n"
            f"HEAD: {analysis.head_summary}\n"
            f"Languages: {', '.join(analysis.languages) or 'unknown'}\n"
            f"Dirty: {analysis.dirty}\n"
            f"Build commands: {', '.join(analysis.build_commands) or 'none'}\n"
            f"Test commands: {', '.join(analysis.test_commands) or 'none'}"
        )

        return ContextPackage(
            objective=objective,
            repository_summary=summary,
            relevant_files=selected,
            constraints=list(constraints or []),
            prior_knowledge=list(prior_knowledge or []),
            omitted_files=omitted,
            total_bytes=total_bytes,
        )

    def _collect_candidates(
        self,
        *,
        root: Path,
        objective: str,
        analysis: RepositoryAnalysis,
        explicit_files: list[str],
    ) -> list[ContextCandidate]:
        candidates: dict[Path, ContextCandidate] = {}
        keywords = self._keywords(objective)

        def add(path: Path, score: int, reason: str) -> None:
            resolved = path.resolve()

            if not self._inside_root(root, resolved):
                return

            if not resolved.is_file():
                return

            if self._ignored(resolved):
                return

            current = candidates.get(resolved)

            if current is None or score > current.score:
                candidates[resolved] = ContextCandidate(
                    path=resolved,
                    score=score,
                    reason=reason,
                )

        for relative in explicit_files:
            add(root / relative, 100, "explicitly requested")

        for relative in analysis.important_files:
            path = root / relative

            if path.is_file():
                add(path, 80, "important repository file")

        for dirty_line in analysis.dirty_files:
            relative = self._status_path(dirty_line)
            if relative:
                add(root / relative, 90, "currently changed file")

        for path in self._walk_text_files(root):
            relative_lower = str(path.relative_to(root)).lower()
            name_lower = path.name.lower()

            score = 0
            reasons: list[str] = []

            for keyword in keywords:
                if keyword in relative_lower:
                    score += 20
                    reasons.append(f"path matches '{keyword}'")

            if "test" in name_lower or "tests/" in relative_lower:
                score += 5
                reasons.append("test file")

            if name_lower in {
                "readme.md",
                "pyproject.toml",
                "package.json",
                "cargo.toml",
                "move.toml",
            }:
                score += 15
                reasons.append("project configuration")

            if score > 0:
                add(
                    path,
                    score,
                    ", ".join(reasons),
                )

        return sorted(
            candidates.values(),
            key=lambda item: (-item.score, str(item.path)),
        )

    def _walk_text_files(self, root: Path) -> Iterable[Path]:
        for path in root.rglob("*"):
            if not path.is_file():
                continue

            if self._ignored(path):
                continue

            if path.suffix.lower() in TEXT_SUFFIXES:
                yield path

    def _ignored(self, path: Path) -> bool:
        return any(part in IGNORED_PARTS for part in path.parts)

    def _keywords(self, objective: str) -> set[str]:
        tokens = {
            token.strip(".,:;()[]{}").lower()
            for token in objective.split()
        }

        return {
            token
            for token in tokens
            if len(token) >= 3
        }

    def _inside_root(self, root: Path, path: Path) -> bool:
        return path == root or root in path.parents

    def _status_path(self, line: str) -> str | None:
        if len(line) < 4:
            return None

        value = line[3:].strip()

        if " -> " in value:
            value = value.split(" -> ", 1)[1]

        return value or None
