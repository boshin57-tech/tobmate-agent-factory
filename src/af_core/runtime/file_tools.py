from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class WorkspaceToolError(RuntimeError):
    """Raised when a workspace file operation is unsafe."""


class FileReadResult(BaseModel):
    path: str
    content: str
    size_bytes: int


class FileWriteResult(BaseModel):
    path: str
    created: bool
    size_bytes: int


class TextSearchMatch(BaseModel):
    path: str
    line_number: int
    line: str


class TextSearchResult(BaseModel):
    query: str
    matches: list[TextSearchMatch] = Field(
        default_factory=list
    )
    truncated: bool = False


class WorkspaceFileTools:
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

    def __init__(
        self,
        workspace_path: str | Path,
        *,
        maximum_read_bytes: int = 256 * 1024,
        maximum_write_bytes: int = 256 * 1024,
    ) -> None:
        self.workspace = Path(
            workspace_path
        ).expanduser().resolve()

        if not self.workspace.is_dir():
            raise ValueError(
                f"Workspace does not exist: {self.workspace}"
            )

        self.maximum_read_bytes = maximum_read_bytes
        self.maximum_write_bytes = maximum_write_bytes

    def read_file(
        self,
        *,
        path: str,
    ) -> FileReadResult:
        target = self._resolve(path)

        if not target.is_file():
            raise WorkspaceToolError(
                f"File does not exist: {path}"
            )

        size = target.stat().st_size

        if size > self.maximum_read_bytes:
            raise WorkspaceToolError(
                f"File exceeds read limit: {path}"
            )

        try:
            content = target.read_text(
                encoding="utf-8"
            )
        except UnicodeDecodeError as exc:
            raise WorkspaceToolError(
                f"File is not UTF-8 text: {path}"
            ) from exc

        return FileReadResult(
            path=str(
                target.relative_to(self.workspace)
            ),
            content=content,
            size_bytes=size,
        )

    def write_file(
        self,
        *,
        path: str,
        content: str,
    ) -> FileWriteResult:
        target = self._resolve(path)
        content_bytes = content.encode("utf-8")

        if len(content_bytes) > self.maximum_write_bytes:
            raise WorkspaceToolError(
                f"Content exceeds write limit: {path}"
            )

        created = not target.exists()
        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary = target.with_name(
            target.name + ".af-tmp"
        )
        temporary.write_text(
            content,
            encoding="utf-8",
        )
        temporary.replace(target)

        self._invalidate_python_cache(target)

        return FileWriteResult(
            path=str(
                target.relative_to(self.workspace)
            ),
            created=created,
            size_bytes=len(content_bytes),
        )

    def list_files(
        self,
        *,
        path: str = ".",
        maximum_results: int = 200,
    ) -> list[str]:
        root = self._resolve(path)

        if not root.is_dir():
            raise WorkspaceToolError(
                f"Directory does not exist: {path}"
            )

        results: list[str] = []

        for candidate in sorted(root.rglob("*")):
            if len(results) >= maximum_results:
                break

            if not candidate.is_file():
                continue

            if self._ignored(candidate):
                continue

            results.append(
                str(
                    candidate.relative_to(
                        self.workspace
                    )
                )
            )

        return results

    def search_text(
        self,
        *,
        query: str,
        path: str = ".",
        maximum_matches: int = 100,
    ) -> TextSearchResult:
        if not query:
            raise WorkspaceToolError(
                "Search query cannot be empty."
            )

        root = self._resolve(path)
        matcher = re.compile(re.escape(query))
        matches: list[TextSearchMatch] = []

        files = (
            [root]
            if root.is_file()
            else sorted(root.rglob("*"))
        )

        for candidate in files:
            if not candidate.is_file():
                continue

            if self._ignored(candidate):
                continue

            if (
                candidate.stat().st_size
                > self.maximum_read_bytes
            ):
                continue

            try:
                lines = candidate.read_text(
                    encoding="utf-8"
                ).splitlines()
            except UnicodeDecodeError:
                continue

            for number, line in enumerate(
                lines,
                start=1,
            ):
                if not matcher.search(line):
                    continue

                matches.append(
                    TextSearchMatch(
                        path=str(
                            candidate.relative_to(
                                self.workspace
                            )
                        ),
                        line_number=number,
                        line=line,
                    )
                )

                if len(matches) >= maximum_matches:
                    return TextSearchResult(
                        query=query,
                        matches=matches,
                        truncated=True,
                    )

        return TextSearchResult(
            query=query,
            matches=matches,
            truncated=False,
        )

    def _invalidate_python_cache(
        self,
        target: Path,
    ) -> None:
        if target.suffix != ".py":
            return

        cache_dir = target.parent / "__pycache__"

        if not cache_dir.is_dir():
            return

        pattern = f"{target.stem}.*.pyc"

        for cached in cache_dir.glob(pattern):
            try:
                cached.unlink()
            except OSError as exc:
                raise WorkspaceToolError(
                    f"Unable to invalidate Python cache: {cached}"
                ) from exc

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        handlers = {
            "read_file": self.read_file,
            "write_file": self.write_file,
            "list_files": self.list_files,
            "search_text": self.search_text,
        }

        try:
            handler = handlers[tool_name]
        except KeyError as exc:
            raise WorkspaceToolError(
                f"Unknown file tool: {tool_name}"
            ) from exc

        return handler(**arguments)

    def _resolve(self, value: str) -> Path:
        if not value:
            raise WorkspaceToolError(
                "Path cannot be empty."
            )

        relative = Path(value)

        if relative.is_absolute():
            raise WorkspaceToolError(
                "Absolute paths are not allowed."
            )

        target = (
            self.workspace / relative
        ).resolve()

        if (
            target != self.workspace
            and self.workspace not in target.parents
        ):
            raise WorkspaceToolError(
                "Path escapes the workspace."
            )

        if self._ignored(target):
            raise WorkspaceToolError(
                f"Protected path: {value}"
            )

        return target

    def _ignored(self, path: Path) -> bool:
        try:
            relative = path.relative_to(
                self.workspace
            )
        except ValueError:
            return True

        return any(
            part in self.IGNORED_PARTS
            for part in relative.parts
        )
