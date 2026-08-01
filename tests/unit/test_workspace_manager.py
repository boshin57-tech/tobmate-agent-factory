from pathlib import Path
import subprocess

import pytest

from af_core.repository.git_client import GitClient
from af_core.workspace.manager import WorkspaceManager
from af_core.workspace.worktree import WorktreeError


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def create_repo(path: Path) -> Path:
    path.mkdir()
    git(path, "init")
    git(path, "config", "user.name", "AF Test")
    git(path, "config", "user.email", "af@example.com")

    (path / "app.py").write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )

    git(path, "add", ".")
    git(path, "commit", "-m", "initial")
    return path


def test_workspace_isolated_from_source(tmp_path: Path) -> None:
    source = create_repo(tmp_path / "source")
    original_head = git(source, "rev-parse", "HEAD")
    original_content = (source / "app.py").read_text(
        encoding="utf-8"
    )

    manager = WorkspaceManager(tmp_path / "workspaces")
    record = manager.create(
        source_repository=source,
        project_id="project-1",
        run_id="run-1",
    )

    workspace = Path(record.workspace_path)

    (workspace / "app.py").write_text(
        "VALUE = 2\n",
        encoding="utf-8",
    )

    assert any(
        "app.py" in line
        for line in manager.status(record)
    )
    assert "VALUE = 2" in manager.diff(record)

    assert (source / "app.py").read_text(
        encoding="utf-8"
    ) == original_content

    assert git(source, "status", "--porcelain") == ""
    assert git(source, "rev-parse", "HEAD") == original_head

    manager.cleanup(record, force=True)
    assert not workspace.exists()


def test_workspace_is_registered(tmp_path: Path) -> None:
    source = create_repo(tmp_path / "source")
    manager = WorkspaceManager(tmp_path / "workspaces")

    record = manager.create(
        source_repository=source,
        project_id="project-2",
        run_id="run-2",
    )

    assert any(
        item.get("worktree") == record.workspace_path
        for item in GitClient(source).worktree_list()
    )

    manager.cleanup(record, force=True)


def test_duplicate_workspace_is_rejected(
    tmp_path: Path,
) -> None:
    source = create_repo(tmp_path / "source")
    manager = WorkspaceManager(tmp_path / "workspaces")

    record = manager.create(
        source_repository=source,
        project_id="project-3",
        run_id="run-3",
    )

    with pytest.raises(WorktreeError):
        manager.create(
            source_repository=source,
            project_id="project-3",
            run_id="run-3",
        )

    manager.cleanup(record, force=True)


def test_unsafe_identifier_is_rejected(
    tmp_path: Path,
) -> None:
    source = create_repo(tmp_path / "source")
    manager = WorkspaceManager(tmp_path / "workspaces")

    with pytest.raises(ValueError):
        manager.create(
            source_repository=source,
            project_id="../",
            run_id="run-4",
        )
