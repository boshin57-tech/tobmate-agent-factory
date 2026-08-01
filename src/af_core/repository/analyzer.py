from __future__ import annotations

from collections import Counter
from pathlib import Path

from pydantic import BaseModel, Field

from .git_client import GitClient


LANGUAGE_BY_SUFFIX = {
    ".py": "Python",
    ".rs": "Rust",
    ".move": "Move",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".c": "C",
    ".h": "C/C++",
    ".cpp": "C++",
    ".hpp": "C++",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".sh": "Shell",
    ".sol": "Solidity",
}


class RepositoryAnalysis(BaseModel):
    repository_path: str
    branch: str
    head_commit: str
    head_summary: str
    dirty: bool
    dirty_files: list[str] = Field(default_factory=list)
    tracked_file_count: int
    languages: list[str] = Field(default_factory=list)
    build_commands: list[str] = Field(default_factory=list)
    test_commands: list[str] = Field(default_factory=list)
    important_files: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class RepositoryAnalyzer:
    def analyze(self, repository_path: str | Path) -> RepositoryAnalysis:
        client = GitClient(repository_path)
        root = client.top_level()

        dirty_files = client.status_porcelain()
        tracked_files = client.tracked_files()
        languages = self._detect_languages(tracked_files)
        build_commands, test_commands = self._detect_commands(root)
        important_files = self._important_files(root)

        risks: list[str] = []

        if dirty_files:
            risks.append(
                "Repository contains uncommitted or untracked changes."
            )

        if not client.branch():
            risks.append("Repository is in detached HEAD state.")

        return RepositoryAnalysis(
            repository_path=str(root),
            branch=client.branch(),
            head_commit=client.head_commit(),
            head_summary=client.head_summary(),
            dirty=bool(dirty_files),
            dirty_files=dirty_files,
            tracked_file_count=len(tracked_files),
            languages=languages,
            build_commands=build_commands,
            test_commands=test_commands,
            important_files=important_files,
            risks=risks,
        )

    def _detect_languages(self, files: list[str]) -> list[str]:
        counts: Counter[str] = Counter()

        for name in files:
            language = LANGUAGE_BY_SUFFIX.get(Path(name).suffix.lower())
            if language:
                counts[language] += 1

        return [
            language
            for language, _count in counts.most_common()
        ]

    def _detect_commands(
        self,
        root: Path,
    ) -> tuple[list[str], list[str]]:
        builds: list[str] = []
        tests: list[str] = []

        if (root / "pyproject.toml").exists():
            builds.append("python -m build")
            tests.append("pytest")

        if (root / "package.json").exists():
            builds.append("npm run build")
            tests.append("npm test")

        if (root / "Cargo.toml").exists():
            builds.append("cargo build")
            tests.append("cargo test")

        if (root / "Move.toml").exists():
            builds.append("sui move build")
            tests.append("sui move test")

        if (root / "go.mod").exists():
            builds.append("go build ./...")
            tests.append("go test ./...")

        return builds, tests

    def _important_files(self, root: Path) -> list[str]:
        candidates = [
            "README.md",
            "pyproject.toml",
            "package.json",
            "Cargo.toml",
            "Move.toml",
            "go.mod",
            "Dockerfile",
            "docker-compose.yml",
            ".github/workflows",
        ]

        return [
            name
            for name in candidates
            if (root / name).exists()
        ]
