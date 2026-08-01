from pathlib import Path

import pytest

from af_core.runtime.file_tools import (
    WorkspaceFileTools,
    WorkspaceToolError,
)


def test_file_tools_read_write_list_and_search(
    tmp_path: Path,
) -> None:
    tools = WorkspaceFileTools(tmp_path)

    result = tools.write_file(
        path="src/app.py",
        content="VALUE = 1\n",
    )

    assert result.created is True
    assert result.path == "src/app.py"

    read = tools.read_file(
        path="src/app.py",
    )

    assert read.content == "VALUE = 1\n"
    assert tools.list_files() == ["src/app.py"]

    search = tools.search_text(
        query="VALUE",
    )

    assert len(search.matches) == 1
    assert search.matches[0].path == "src/app.py"
    assert search.matches[0].line_number == 1


def test_file_tools_prevent_workspace_escape(
    tmp_path: Path,
) -> None:
    tools = WorkspaceFileTools(tmp_path)

    with pytest.raises(WorkspaceToolError):
        tools.write_file(
            path="../outside.txt",
            content="unsafe",
        )

    with pytest.raises(WorkspaceToolError):
        tools.read_file(
            path="/etc/passwd",
        )


def test_file_tools_block_protected_paths(
    tmp_path: Path,
) -> None:
    tools = WorkspaceFileTools(tmp_path)

    with pytest.raises(WorkspaceToolError):
        tools.write_file(
            path=".git/config",
            content="unsafe",
        )

    with pytest.raises(WorkspaceToolError):
        tools.list_files(
            path=".venv",
        )


def test_file_tools_enforce_size_limits(
    tmp_path: Path,
) -> None:
    tools = WorkspaceFileTools(
        tmp_path,
        maximum_read_bytes=5,
        maximum_write_bytes=5,
    )

    with pytest.raises(WorkspaceToolError):
        tools.write_file(
            path="large.txt",
            content="123456",
        )

    target = tmp_path / "existing.txt"
    target.write_text(
        "123456",
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceToolError):
        tools.read_file(
            path="existing.txt",
        )
