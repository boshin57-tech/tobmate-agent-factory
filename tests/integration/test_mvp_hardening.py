from pathlib import Path
import asyncio
import subprocess
import sys

import pytest

from af_core.runtime.command_runner import (
    CommandPolicy,
    CommandPolicyError,
    RestrictedCommandRunner,
)
from af_core.workspace.manager import WorkspaceManager


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.rstrip("\r\n")


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


def test_original_repository_remains_unchanged(
    tmp_path: Path,
) -> None:
    source = create_repo(tmp_path / "source")
    original_head = git(source, "rev-parse", "HEAD")
    original_status = git(
        source,
        "status",
        "--porcelain=v1",
    )
    original_content = (
        source / "app.py"
    ).read_text(encoding="utf-8")

    manager = WorkspaceManager(tmp_path / "workspaces")
    record = manager.create(
        source_repository=source,
        project_id="project-hardening",
        run_id="run-hardening",
    )

    runner = RestrictedCommandRunner(
        record.workspace_path
    )

    result = asyncio.run(
        runner.run(
            [
                sys.executable,
                "-c",
                (
                    "from pathlib import Path;"
                    "Path('app.py').write_text('VALUE = 2\\n')"
                ),
            ]
        )
    )

    assert result.returncode == 0
    assert "app.py" in result.changed_files

    assert git(source, "rev-parse", "HEAD") == original_head
    assert git(
        source,
        "status",
        "--porcelain=v1",
    ) == original_status
    assert (
        source / "app.py"
    ).read_text(encoding="utf-8") == original_content

    manager.cleanup(record, force=True)


@pytest.mark.parametrize(
    "command",
    [
        ["git", "commit", "-m", "unauthorized"],
        ["git", "merge", "main"],
        ["git", "rebase", "main"],
        ["git", "checkout", "--", "app.py"],
        ["git", "switch", "main"],
        ["git", "tag", "unsafe"],
        ["git", "remote", "-v"],
        ["git", "config", "--list"],
    ],
)
def test_sensitive_git_commands_are_blocked(
    command: list[str],
) -> None:
    with pytest.raises(CommandPolicyError):
        CommandPolicy().validate(command)


@pytest.mark.parametrize(
    "command",
    [
        ["bash", "-c", "sudo true"],
        ["bash", "-c", "ssh example.com"],
        ["bash", "-c", "wget https://example.com/file"],
        ["bash", "-c", "reboot"],
        ["bash", "-c", "shutdown now"],
    ],
)
def test_sensitive_shell_commands_are_blocked(
    command: list[str],
) -> None:
    with pytest.raises(CommandPolicyError):
        CommandPolicy().validate(command)
