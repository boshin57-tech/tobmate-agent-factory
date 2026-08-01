import asyncio
from pathlib import Path
import subprocess
import sys

import pytest

from af_core.runtime.command_runner import (
    CommandPolicy,
    CommandPolicyError,
    RestrictedCommandRunner,
)


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


def run(coro):
    return asyncio.run(coro)


def test_command_runner_executes_allowed_command(
    tmp_path: Path,
) -> None:
    repo = create_repo(tmp_path / "repo")
    runner = RestrictedCommandRunner(repo)

    result = run(
        runner.run(
            [sys.executable, "-c", "print('hello')"],
        )
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "hello"
    assert result.timed_out is False


def test_command_runner_detects_changed_files(
    tmp_path: Path,
) -> None:
    repo = create_repo(tmp_path / "repo")
    runner = RestrictedCommandRunner(repo)

    result = run(
        runner.run(
            [
                sys.executable,
                "-c",
                (
                    "from pathlib import Path;"
                    "Path('generated.txt').write_text('created')"
                ),
            ]
        )
    )

    assert result.returncode == 0
    assert "generated.txt" in result.changed_files


def test_command_runner_blocks_external_cwd(
    tmp_path: Path,
) -> None:
    repo = create_repo(tmp_path / "repo")
    outside = tmp_path / "outside"
    outside.mkdir()

    runner = RestrictedCommandRunner(repo)

    with pytest.raises(CommandPolicyError):
        run(
            runner.run(
                [sys.executable, "-c", "print('no')"],
                cwd=outside,
            )
        )


def test_command_policy_blocks_dangerous_git() -> None:
    policy = CommandPolicy()

    with pytest.raises(CommandPolicyError):
        policy.validate(["git", "push"])

    with pytest.raises(CommandPolicyError):
        policy.validate(["git", "reset", "--hard"])

    with pytest.raises(CommandPolicyError):
        policy.validate(["git", "clean", "-f"])


def test_command_policy_blocks_dangerous_shell() -> None:
    policy = CommandPolicy()

    with pytest.raises(CommandPolicyError):
        policy.validate(["bash", "-c", "rm -rf /tmp/example"])

    with pytest.raises(CommandPolicyError):
        policy.validate(["sh", "-c", "curl https://example.com"])


def test_command_runner_timeout(
    tmp_path: Path,
) -> None:
    repo = create_repo(tmp_path / "repo")
    runner = RestrictedCommandRunner(repo)

    result = run(
        runner.run(
            [
                sys.executable,
                "-c",
                "import time; time.sleep(2)",
            ],
            timeout=1,
        )
    )

    assert result.timed_out is True
    assert result.returncode == -1


def test_environment_is_restricted(
    tmp_path: Path,
) -> None:
    repo = create_repo(tmp_path / "repo")
    runner = RestrictedCommandRunner(repo)

    with pytest.raises(CommandPolicyError):
        run(
            runner.run(
                [sys.executable, "-c", "print('x')"],
                environment={"OPENAI_API_KEY": "secret"},
            )
        )
