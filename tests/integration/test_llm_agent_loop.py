from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess
import sys

from af_core.orchestrator.planner import PlannedTask
from af_core.runtime.agent import (
    AgentProfile,
    AgentRole,
)
from af_core.runtime.executor import AgentExecutor
from af_core.runtime.llm_provider import StaticLLMProvider
from af_core.workspace.manager import WorkspaceManager


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.rstrip("\r\n")


def create_repository(path: Path) -> Path:
    path.mkdir()

    git(path, "init")
    git(path, "config", "user.name", "AF Test")
    git(path, "config", "user.email", "af@example.com")

    source = path / "src"
    source.mkdir()

    tests = path / "tests"
    tests.mkdir()

    (source / "calculator.py").write_text(
        (
            "def add(left: int, right: int) -> int:\n"
            "    return left + right\n"
        ),
        encoding="utf-8",
    )

    (tests / "test_calculator.py").write_text(
        (
            "from src.calculator import add\n\n\n"
            "def test_add() -> None:\n"
            "    assert add(2, 3) == 5\n"
        ),
        encoding="utf-8",
    )

    (path / "pyproject.toml").write_text(
        (
            "[project]\n"
            'name = "sample"\n'
            'version = "0.1.0"\n\n'
            "[tool.pytest.ini_options]\n"
            'testpaths = ["tests"]\n'
        ),
        encoding="utf-8",
    )

    git(path, "add", ".")
    git(path, "commit", "-m", "initial")

    return path


def implementer_profile() -> AgentProfile:
    return AgentProfile(
        name="implementer-task-multiply",
        role=AgentRole.IMPLEMENTER,
        allowed_tools={
            "read_file",
            "write_file",
            "list_files",
            "search_text",
            "run_command",
        },
        maximum_steps=10,
        command_timeout_seconds=30,
    )


def multiply_task() -> PlannedTask:
    return PlannedTask(
        id="task-multiply",
        title="Add multiplication support",
        description=(
            "Add multiply(left, right) and a passing unit test."
        ),
        task_type="implementation",
        agent_role="implementer",
        acceptance_criteria=[
            "multiply(4, 5) returns 20",
            "pytest passes",
        ],
    )


def test_llm_agent_repairs_failed_test_and_completes(
    tmp_path: Path,
) -> None:
    source = create_repository(tmp_path / "source")
    source_head = git(source, "rev-parse", "HEAD")
    source_status = git(
        source,
        "status",
        "--porcelain=v1",
    )

    workspace_record = WorkspaceManager(
        tmp_path / "workspaces"
    ).create(
        source_repository=source,
        project_id="project-llm",
        run_id="run-llm",
    )

    workspace = Path(workspace_record.workspace_path)

    provider = StaticLLMProvider(
        [
            {
                "action_type": "tool_call",
                "tool_call": {
                    "tool_name": "read_file",
                    "arguments": {
                        "path": "src/calculator.py",
                    },
                    "reason": "Inspect implementation",
                },
            },
            {
                "action_type": "tool_call",
                "tool_call": {
                    "tool_name": "write_file",
                    "arguments": {
                        "path": "src/calculator.py",
                        "content": (
                            "def add(left: int, right: int) -> int:\n"
                            "    return left + right\n\n\n"
                            "def multiply(left: int, right: int) -> int:\n"
                            "    return left + right\n"
                        ),
                    },
                    "reason": "Add initial multiply implementation",
                },
            },
            {
                "action_type": "tool_call",
                "tool_call": {
                    "tool_name": "write_file",
                    "arguments": {
                        "path": "tests/test_calculator.py",
                        "content": (
                            "from src.calculator import add, multiply\n\n\n"
                            "def test_add() -> None:\n"
                            "    assert add(2, 3) == 5\n\n\n"
                            "def test_multiply() -> None:\n"
                            "    assert multiply(4, 5) == 20\n"
                        ),
                    },
                    "reason": "Add multiply test",
                },
            },
            {
                "action_type": "tool_call",
                "tool_call": {
                    "tool_name": "run_command",
                    "arguments": {
                        "command": [
                            sys.executable,
                            "-m",
                            "pytest",
                            "-q",
                        ],
                    },
                    "reason": "Run tests",
                },
            },
            {
                "action_type": "tool_call",
                "tool_call": {
                    "tool_name": "write_file",
                    "arguments": {
                        "path": "src/calculator.py",
                        "content": (
                            "def add(left: int, right: int) -> int:\n"
                            "    return left + right\n\n\n"
                            "def multiply(left: int, right: int) -> int:\n"
                            "    return left * right\n"
                        ),
                    },
                    "reason": (
                        "Repair multiply after failed assertion"
                    ),
                },
            },
            {
                "action_type": "tool_call",
                "tool_call": {
                    "tool_name": "run_command",
                    "arguments": {
                        "command": [
                            sys.executable,
                            "-m",
                            "pytest",
                            "-q",
                        ],
                    },
                    "reason": "Verify repaired implementation",
                },
            },
            {
                "action_type": "complete",
                "summary": (
                    "Added multiply support and passing tests."
                ),
            },
        ]
    )

    result = asyncio.run(
        AgentExecutor(
            provider=provider,
            profile=implementer_profile(),
            workspace_path=workspace,
        ).execute(
            task=multiply_task(),
            context_summary=(
                "Small Python calculator project."
            ),
        )
    )

    assert result.successful is True
    assert result.error is None
    assert result.summary == (
        "Added multiply support and passing tests."
    )

    assert len(result.tool_records) == 6
    assert result.tool_records[3].tool_name == "run_command"
    assert result.tool_records[3].success is False
    assert result.tool_records[5].tool_name == "run_command"
    assert result.tool_records[5].success is True

    assert provider.calls
    repair_call_messages = provider.calls[4]

    assert any(
        message.role == "tool"
        and '"success": false' in message.content
        and "1 failed" in message.content
        for message in repair_call_messages
    )

    assert set(result.changed_files) == {
        "src/calculator.py",
        "tests/test_calculator.py",
    }

    assert "return left * right" in result.diff_text
    assert "test_multiply" in result.diff_text

    final_test = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
        ],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )

    assert final_test.returncode == 0
    assert "2 passed" in final_test.stdout

    assert git(source, "rev-parse", "HEAD") == source_head
    assert git(
        source,
        "status",
        "--porcelain=v1",
    ) == source_status

    assert not (
        source / "src" / "calculator.py"
    ).read_text(
        encoding="utf-8"
    ).count("multiply")


def test_llm_agent_generates_patch_only_in_worktree(
    tmp_path: Path,
) -> None:
    source = create_repository(tmp_path / "source")

    workspace_record = WorkspaceManager(
        tmp_path / "workspaces"
    ).create(
        source_repository=source,
        project_id="project-patch",
        run_id="run-patch",
    )

    provider = StaticLLMProvider(
        [
            {
                "action_type": "tool_call",
                "tool_call": {
                    "tool_name": "write_file",
                    "arguments": {
                        "path": "src/new_feature.py",
                        "content": "ENABLED = True\n",
                    },
                    "reason": "Create feature file",
                },
            },
            {
                "action_type": "complete",
                "summary": "Created feature file",
            },
        ]
    )

    result = asyncio.run(
        AgentExecutor(
            provider=provider,
            profile=implementer_profile(),
            workspace_path=workspace_record.workspace_path,
        ).execute(
            task=PlannedTask(
                id="task-feature",
                title="Create feature",
                description="Create new_feature.py",
                task_type="implementation",
                agent_role="implementer",
            ),
        )
    )

    assert result.successful is True
    assert result.changed_files == [
        "src/new_feature.py"
    ]

    assert (
        Path(workspace_record.workspace_path)
        / "src"
        / "new_feature.py"
    ).is_file()

    assert not (
        source
        / "src"
        / "new_feature.py"
    ).exists()
