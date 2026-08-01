from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess

from af_core.orchestrator.parallel_models import AgentTaskResult
from af_core.orchestrator.parallel_scheduler import (
    ParallelTaskScheduler,
)
from af_core.orchestrator.planner import (
    PlannedTask,
    ProjectPlan,
)


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

    (path / "base.txt").write_text(
        "base\n",
        encoding="utf-8",
    )

    git(path, "add", ".")
    git(path, "commit", "-m", "initial")
    return path


def parallel_plan() -> ProjectPlan:
    return ProjectPlan(
        goal="Execute independent tasks in parallel",
        tasks=[
            PlannedTask(
                id="task-a",
                title="Create A",
                description="Create file A",
                task_type="implementation",
                agent_role="implementer",
            ),
            PlannedTask(
                id="task-b",
                title="Create B",
                description="Create file B",
                task_type="implementation",
                agent_role="implementer",
            ),
            PlannedTask(
                id="task-c",
                title="Combine results",
                description="Run after A and B",
                task_type="validation",
                dependencies=["task-a", "task-b"],
                agent_role="tester",
            ),
        ],
    )


async def successful_handler(
    task,
    assignment,
    workspace,
) -> AgentTaskResult:
    workspace_path = Path(workspace.workspace_path)

    await asyncio.sleep(0.05)

    target = workspace_path / f"{task.id}.txt"
    target.write_text(
        f"result from {task.id}\n",
        encoding="utf-8",
    )

    changed_files = [
        line[3:].strip()
        for line in git(
            workspace_path,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ).splitlines()
        if len(line) >= 4
    ]

    diff_process = subprocess.run(
        [
            "git",
            "-C",
            str(workspace_path),
            "diff",
            "--binary",
            "--no-index",
            "/dev/null",
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if diff_process.returncode not in {0, 1}:
        raise RuntimeError(
            diff_process.stderr.strip()
            or "Failed to generate task patch"
        )

    diff_text = diff_process.stdout.rstrip("\r\n")

    return AgentTaskResult(
        task_id=task.id,
        agent_name=assignment.agent_name,
        success=True,
        workspace_path=workspace.workspace_path,
        branch=workspace.branch,
        changed_files=changed_files,
        diff_text=diff_text,
        summary=f"{task.id} complete",
    )


def test_independent_tasks_execute_in_same_batch(
    tmp_path: Path,
) -> None:
    source = create_repo(tmp_path / "source")

    scheduler = ParallelTaskScheduler(
        workspace_root=tmp_path / "workspaces",
        maximum_parallelism=2,
    )

    result = asyncio.run(
        scheduler.execute(
            plan=parallel_plan(),
            source_repository=source,
            project_id="parallel-project",
            run_id="parallel-run",
            handler=successful_handler,
        )
    )

    assert result.successful is True
    assert len(result.batches) == 2

    assert set(result.batches[0].task_ids) == {
        "task-a",
        "task-b",
    }
    assert result.batches[1].task_ids == ["task-c"]

    assert set(result.task_results) == {
        "task-a",
        "task-b",
        "task-c",
    }

    task_a = result.task_results["task-a"]
    task_b = result.task_results["task-b"]

    assert task_a.workspace_path != task_b.workspace_path
    assert task_a.branch != task_b.branch

    assert git(source, "status", "--porcelain=v1") == ""
    assert not (source / "task-a.txt").exists()
    assert not (source / "task-b.txt").exists()


def test_maximum_parallelism_limits_batch_size(
    tmp_path: Path,
) -> None:
    source = create_repo(tmp_path / "source")

    plan = ProjectPlan(
        goal="Limit parallelism",
        tasks=[
            PlannedTask(
                id=f"task-{index}",
                title=f"Task {index}",
                description="Independent task",
                task_type="implementation",
                agent_role="implementer",
            )
            for index in range(1, 5)
        ],
    )

    scheduler = ParallelTaskScheduler(
        workspace_root=tmp_path / "workspaces",
        maximum_parallelism=2,
    )

    result = asyncio.run(
        scheduler.execute(
            plan=plan,
            source_repository=source,
            project_id="limited-project",
            run_id="limited-run",
            handler=successful_handler,
        )
    )

    assert result.successful is True
    assert [len(batch.task_ids) for batch in result.batches] == [
        2,
        2,
    ]


def test_agent_failure_blocks_dependent_task(
    tmp_path: Path,
) -> None:
    source = create_repo(tmp_path / "source")

    async def failing_handler(
        task,
        assignment,
        workspace,
    ) -> AgentTaskResult:
        if task.id == "task-b":
            return AgentTaskResult(
                task_id=task.id,
                agent_name=assignment.agent_name,
                success=False,
                workspace_path=workspace.workspace_path,
                branch=workspace.branch,
                error="agent execution failed",
            )

        return await successful_handler(
            task,
            assignment,
            workspace,
        )

    scheduler = ParallelTaskScheduler(
        workspace_root=tmp_path / "workspaces",
        maximum_parallelism=2,
    )

    result = asyncio.run(
        scheduler.execute(
            plan=parallel_plan(),
            source_repository=source,
            project_id="failure-project",
            run_id="failure-run",
            handler=failing_handler,
        )
    )

    assert result.successful is False
    assert result.failed_task_ids == ["task-b"]
    assert result.blocked_task_ids == ["task-c"]
    assert "task-c" not in result.task_results

    assert result.task_results["task-a"].success is True
    assert result.task_results["task-b"].success is False
    assert git(source, "status", "--porcelain=v1") == ""


def test_handler_exception_is_recorded_as_failure(
    tmp_path: Path,
) -> None:
    source = create_repo(tmp_path / "source")

    plan = ProjectPlan(
        goal="Record handler exception",
        tasks=[
            PlannedTask(
                id="task-error",
                title="Error",
                description="Raise exception",
                task_type="implementation",
                agent_role="implementer",
            )
        ],
    )

    async def broken_handler(
        task,
        assignment,
        workspace,
    ):
        raise RuntimeError("handler crashed")

    scheduler = ParallelTaskScheduler(
        workspace_root=tmp_path / "workspaces",
        maximum_parallelism=2,
    )

    result = asyncio.run(
        scheduler.execute(
            plan=plan,
            source_repository=source,
            project_id="error-project",
            run_id="error-run",
            handler=broken_handler,
        )
    )

    assert result.successful is False
    assert result.failed_task_ids == ["task-error"]
    assert (
        result.task_results["task-error"].error
        == "handler crashed"
    )
    assert git(source, "status", "--porcelain=v1") == ""
