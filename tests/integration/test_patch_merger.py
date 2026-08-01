from pathlib import Path
import subprocess

from af_core.orchestrator.parallel_models import AgentTaskResult
from af_core.orchestrator.patch_merger import (
    IntegrationPatchMerger,
    PatchMergeStatus,
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

    (path / "feature_a.py").write_text(
        "FEATURE_A = False\n",
        encoding="utf-8",
    )
    (path / "feature_b.py").write_text(
        "FEATURE_B = False\n",
        encoding="utf-8",
    )
    (path / "shared.py").write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )

    git(path, "add", ".")
    git(path, "commit", "-m", "initial")
    return path


def create_patch(
    source: Path,
    workspace_root: Path,
    branch: str,
    file_name: str,
    content: str,
) -> AgentTaskResult:
    workspace = workspace_root / branch.replace("/", "-")

    git(
        source,
        "worktree",
        "add",
        "-b",
        branch,
        str(workspace),
        "HEAD",
    )

    (workspace / file_name).write_text(
        content,
        encoding="utf-8",
    )

    diff_process = subprocess.run(
        [
            "git",
            "-C",
            str(workspace),
            "diff",
            "--binary",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    if diff_process.returncode != 0:
        raise RuntimeError(
            diff_process.stderr.strip()
            or "Failed to generate patch"
        )

    # Patch는 마지막 개행까지 원문 그대로 보존해야 한다.
    diff_text = diff_process.stdout

    return AgentTaskResult(
        task_id=branch.rsplit("/", 1)[-1],
        agent_name=f"agent-{branch}",
        success=True,
        workspace_path=str(workspace),
        branch=branch,
        changed_files=[file_name],
        diff_text=diff_text,
        summary="Patch generated",
    )


def test_independent_patches_merge_successfully(
    tmp_path: Path,
) -> None:
    source = create_repo(tmp_path / "source")
    original_head = git(source, "rev-parse", "HEAD")

    agents = tmp_path / "agents"
    agents.mkdir()

    first = create_patch(
        source,
        agents,
        "af/task-a",
        "feature_a.py",
        "FEATURE_A = True\n",
    )
    second = create_patch(
        source,
        agents,
        "af/task-b",
        "feature_b.py",
        "FEATURE_B = True\n",
    )

    result = IntegrationPatchMerger(
        integration_root=tmp_path / "integration",
    ).merge(
        source_repository=source,
        project_id="merge-project",
        run_id="merge-run",
        task_results=[first, second],
    )

    assert result.successful is True
    assert result.status is PatchMergeStatus.COMPLETED
    assert len(result.applications) == 2

    integration = Path(result.integration_workspace)

    assert (integration / "feature_a.py").read_text(
        encoding="utf-8"
    ) == "FEATURE_A = True\n"

    assert (integration / "feature_b.py").read_text(
        encoding="utf-8"
    ) == "FEATURE_B = True\n"

    assert set(result.changed_files) == {
        "feature_a.py",
        "feature_b.py",
    }

    assert git(source, "rev-parse", "HEAD") == original_head
    assert git(source, "status", "--porcelain=v1") == ""


def test_overlapping_patches_detect_conflict(
    tmp_path: Path,
) -> None:
    source = create_repo(tmp_path / "source")
    original_content = (source / "shared.py").read_text(
        encoding="utf-8"
    )

    agents = tmp_path / "agents"
    agents.mkdir()

    first = create_patch(
        source,
        agents,
        "af/conflict-a",
        "shared.py",
        "VALUE = 2\n",
    )
    second = create_patch(
        source,
        agents,
        "af/conflict-b",
        "shared.py",
        "VALUE = 3\n",
    )

    result = IntegrationPatchMerger(
        integration_root=tmp_path / "integration",
    ).merge(
        source_repository=source,
        project_id="conflict-project",
        run_id="conflict-run",
        task_results=[first, second],
    )

    assert result.successful is False
    assert result.status in {
        PatchMergeStatus.CONFLICTED,
        PatchMergeStatus.FAILED,
    }
    assert result.conflicting_task_id == "conflict-b"
    assert result.failure_reason

    assert (source / "shared.py").read_text(
        encoding="utf-8"
    ) == original_content
    assert git(source, "status", "--porcelain=v1") == ""


def test_failed_agent_result_is_not_applied(
    tmp_path: Path,
) -> None:
    source = create_repo(tmp_path / "source")

    successful = AgentTaskResult(
        task_id="task-success",
        agent_name="agent-success",
        success=True,
        workspace_path="/tmp/success",
        branch="af/task-success",
        changed_files=[],
        diff_text="",
        summary="No-op success",
    )

    failed = AgentTaskResult(
        task_id="task-failed",
        agent_name="agent-failed",
        success=False,
        workspace_path="/tmp/failed",
        branch="af/task-failed",
        changed_files=["shared.py"],
        diff_text="invalid patch",
        error="Agent failed",
    )

    result = IntegrationPatchMerger(
        integration_root=tmp_path / "integration",
    ).merge(
        source_repository=source,
        project_id="filter-project",
        run_id="filter-run",
        task_results=[successful, failed],
    )

    assert result.successful is True
    assert len(result.applications) == 1
    assert result.applications[0].task_id == "task-success"
    assert git(source, "status", "--porcelain=v1") == ""


def test_original_repository_protected_after_conflict(
    tmp_path: Path,
) -> None:
    source = create_repo(tmp_path / "source")

    before_head = git(source, "rev-parse", "HEAD")
    before_status = git(source, "status", "--porcelain=v1")
    before_content = (source / "shared.py").read_bytes()

    agents = tmp_path / "agents"
    agents.mkdir()

    first = create_patch(
        source,
        agents,
        "af/protect-a",
        "shared.py",
        "VALUE = 10\n",
    )
    second = create_patch(
        source,
        agents,
        "af/protect-b",
        "shared.py",
        "VALUE = 20\n",
    )

    result = IntegrationPatchMerger(
        integration_root=tmp_path / "integration",
    ).merge(
        source_repository=source,
        project_id="protect-project",
        run_id="protect-run",
        task_results=[first, second],
    )

    assert result.successful is False
    assert git(source, "rev-parse", "HEAD") == before_head
    assert git(source, "status", "--porcelain=v1") == before_status
    assert (source / "shared.py").read_bytes() == before_content
