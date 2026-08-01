from pathlib import Path
import asyncio
import subprocess

from af_core.orchestrator.planner import PlannedTask
from af_core.runtime.agent import (
    AgentProfile,
    AgentRole,
)
from af_core.runtime.executor import AgentExecutor
from af_core.runtime.llm_provider import StaticLLMProvider


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


def profile(
    *,
    maximum_steps: int = 10,
) -> AgentProfile:
    return AgentProfile(
        name="implementer-1",
        role=AgentRole.IMPLEMENTER,
        allowed_tools={
            "read_file",
            "write_file",
            "list_files",
            "search_text",
            "run_command",
        },
        maximum_steps=maximum_steps,
    )


def task() -> PlannedTask:
    return PlannedTask(
        id="task-1",
        title="Update value",
        description="Change VALUE to 2",
        task_type="implementation",
        agent_role="implementer",
        acceptance_criteria=[
            "VALUE equals 2",
        ],
    )


def test_agent_executor_reads_writes_and_completes(
    tmp_path: Path,
) -> None:
    repo = create_repo(tmp_path / "repo")

    provider = StaticLLMProvider(
        [
            {
                "action_type": "tool_call",
                "tool_call": {
                    "tool_name": "read_file",
                    "arguments": {
                        "path": "app.py",
                    },
                    "reason": "Inspect file",
                },
            },
            {
                "action_type": "tool_call",
                "tool_call": {
                    "tool_name": "write_file",
                    "arguments": {
                        "path": "app.py",
                        "content": "VALUE = 2\n",
                    },
                    "reason": "Update value",
                },
            },
            {
                "action_type": "complete",
                "summary": "Updated VALUE",
            },
        ]
    )

    executor = AgentExecutor(
        provider=provider,
        profile=profile(),
        workspace_path=repo,
    )

    result = asyncio.run(
        executor.execute(
            task=task(),
            context_summary="Python repository",
        )
    )

    assert result.successful is True
    assert result.summary == "Updated VALUE"
    assert result.changed_files == ["app.py"]
    assert "VALUE = 2" in result.diff_text
    assert len(result.tool_records) == 2
    assert all(
        record.success
        for record in result.tool_records
    )


def test_agent_executor_reports_tool_failure_to_model(
    tmp_path: Path,
) -> None:
    repo = create_repo(tmp_path / "repo")

    provider = StaticLLMProvider(
        [
            {
                "action_type": "tool_call",
                "tool_call": {
                    "tool_name": "read_file",
                    "arguments": {
                        "path": "missing.py",
                    },
                    "reason": "Inspect missing file",
                },
            },
            {
                "action_type": "complete",
                "summary": "Handled missing file",
            },
        ]
    )

    executor = AgentExecutor(
        provider=provider,
        profile=profile(),
        workspace_path=repo,
    )

    result = asyncio.run(
        executor.execute(
            task=task(),
        )
    )

    assert result.successful is True
    assert result.tool_records[0].success is False
    assert "does not exist" in (
        result.tool_records[0].error or ""
    )

    second_call_messages = provider.calls[1]

    assert any(
        message.role == "tool"
        and '"success": false' in message.content
        for message in second_call_messages
    )


def test_agent_executor_blocks_unauthorized_tool(
    tmp_path: Path,
) -> None:
    repo = create_repo(tmp_path / "repo")

    restricted_profile = AgentProfile(
        name="reader",
        role=AgentRole.PLANNER,
        allowed_tools={"read_file"},
        maximum_steps=2,
    )

    provider = StaticLLMProvider(
        [
            {
                "action_type": "tool_call",
                "tool_call": {
                    "tool_name": "write_file",
                    "arguments": {
                        "path": "app.py",
                        "content": "VALUE = 999\n",
                    },
                    "reason": "Unauthorized write",
                },
            }
        ]
    )

    result = asyncio.run(
        AgentExecutor(
            provider=provider,
            profile=restricted_profile,
            workspace_path=repo,
        ).execute(
            task=task(),
        )
    )

    assert result.successful is False
    assert "not allowed" in (
        result.error or ""
    )
    assert (
        repo / "app.py"
    ).read_text(encoding="utf-8") == "VALUE = 1\n"


def test_agent_executor_stops_at_maximum_steps(
    tmp_path: Path,
) -> None:
    repo = create_repo(tmp_path / "repo")

    provider = StaticLLMProvider(
        [
            {
                "action_type": "tool_call",
                "tool_call": {
                    "tool_name": "read_file",
                    "arguments": {
                        "path": "app.py",
                    },
                    "reason": "Read repeatedly",
                },
            },
            {
                "action_type": "tool_call",
                "tool_call": {
                    "tool_name": "read_file",
                    "arguments": {
                        "path": "app.py",
                    },
                    "reason": "Read repeatedly",
                },
            },
        ]
    )

    result = asyncio.run(
        AgentExecutor(
            provider=provider,
            profile=profile(maximum_steps=2),
            workspace_path=repo,
        ).execute(
            task=task(),
        )
    )

    assert result.successful is False
    assert "maximum execution steps" in (
        result.error or ""
    )
