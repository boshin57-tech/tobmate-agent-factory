from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from af_core.assurance.completion import CompletionStatus
from af_core.assurance.reviewer import ReviewDecision
from af_core.knowledge.store import FileKnowledgeStore
from af_core.orchestrator.run_models import (
    FactoryExecutionResult,
    FactoryRunPhase,
    FactoryRunRequest,
)
from af_core.orchestrator.service import ProjectOrchestrator
from af_core.workspace.manager import WorkspaceRecord


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

    (path / "pyproject.toml").write_text(
        """
[project]
name = "sample-project"
version = "0.1.0"

[tool.pytest.ini_options]
testpaths = ["tests"]
""".lstrip(),
        encoding="utf-8",
    )

    source = path / "src"
    source.mkdir()

    (source / "calculator.py").write_text(
        """
def add(left: int, right: int) -> int:
    return left + right
""".lstrip(),
        encoding="utf-8",
    )

    tests = path / "tests"
    tests.mkdir()

    (tests / "test_calculator.py").write_text(
        """
from src.calculator import add


def test_add() -> None:
    assert add(2, 3) == 5
""".lstrip(),
        encoding="utf-8",
    )

    git(path, "add", ".")
    git(path, "commit", "-m", "initial")

    return path


async def successful_execution(
    request: FactoryRunRequest,
    workspace: WorkspaceRecord,
    plan,
) -> FactoryExecutionResult:
    workspace_path = Path(workspace.workspace_path)

    source_file = workspace_path / "src" / "calculator.py"
    source_file.write_text(
        """
def add(left: int, right: int) -> int:
    return left + right


def multiply(left: int, right: int) -> int:
    return left * right
""".lstrip(),
        encoding="utf-8",
    )

    test_file = workspace_path / "tests" / "test_calculator.py"
    test_file.write_text(
        """
from src.calculator import add, multiply


def test_add() -> None:
    assert add(2, 3) == 5


def test_multiply() -> None:
    assert multiply(4, 5) == 20
""".lstrip(),
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

    diff_text = git(
        workspace_path,
        "diff",
        "--binary",
    )

    return FactoryExecutionResult(
        changed_files=changed_files,
        diff_text=diff_text,
        completed_task_ids=[
            task.id
            for task in plan.tasks
        ],
        evidence_refs=[
            "diff",
            "validation",
            "review",
        ],
    )


async def failing_execution(
    request: FactoryRunRequest,
    workspace: WorkspaceRecord,
    plan,
) -> FactoryExecutionResult:
    workspace_path = Path(workspace.workspace_path)

    source_file = workspace_path / "src" / "calculator.py"
    source_file.write_text(
        """
def add(left: int, right: int) -> int:
    return 999
""".lstrip(),
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

    diff_text = git(
        workspace_path,
        "diff",
        "--binary",
    )

    return FactoryExecutionResult(
        changed_files=changed_files,
        diff_text=diff_text,
        completed_task_ids=[
            task.id
            for task in plan.tasks
        ],
        evidence_refs=[
            "diff",
            "validation",
            "review",
        ],
    )


def test_project_orchestrator_runs_end_to_end(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path / "repository")

    orchestrator = ProjectOrchestrator(
        successful_execution
    )

    request = FactoryRunRequest(
        project_id="project-1",
        run_id="run-1",
        repository_path=str(repository),
        objective="Add multiply function and test",
        workspace_root=str(tmp_path / "workspaces"),
        report_root=str(tmp_path / "reports"),
        knowledge_root=str(tmp_path / "knowledge"),
        explicit_context_files=[
            "src/calculator.py",
            "tests/test_calculator.py",
        ],
        allowed_change_paths=[
            "src",
            "tests",
        ],
        validation_commands=[
            [
                sys.executable,
                "-m",
                "pytest",
            ],
            [
                "git",
                "diff",
                "--check",
            ],
        ],
        acceptance_criteria=[
            "Multiply function added",
            "Multiply test added",
        ],
        change_summary=(
            "Added multiplication support and tests."
        ),
        recommended_commit_message=(
            "feat: add multiplication support"
        ),
    )

    import asyncio

    result = asyncio.run(
        orchestrator.run(request)
    )

    assert result.phase is FactoryRunPhase.COMPLETED
    assert result.failure_reason is None
    assert result.analysis is not None
    assert result.context is not None
    assert result.plan is not None
    assert result.validation is not None
    assert result.validation.passed is True
    assert result.review is not None
    assert result.review.decision is ReviewDecision.APPROVED
    assert result.completion is not None
    assert (
        result.completion.status
        is CompletionStatus.COMPLETE
    )
    assert result.delivery is not None
    assert result.knowledge is not None

    assert [
        event.sequence
        for event in result.events
    ] == list(
        range(1, len(result.events) + 1)
    )

    assert result.events[-1].phase is FactoryRunPhase.COMPLETED

    report_dir = (
        tmp_path
        / "reports"
        / "project-1"
        / "run-1"
    )

    assert (report_dir / "summary.md").is_file()
    assert (report_dir / "manifest.json").is_file()
    assert (report_dir / "changes.diff").is_file()

    knowledge = FileKnowledgeStore(
        tmp_path / "knowledge"
    ).list("projects")

    assert len(knowledge) == 1
    assert knowledge[0].title == (
        "Add multiply function and test"
    )

    assert git(
        repository,
        "status",
        "--porcelain",
    ) == ""

    original_source = (
        repository
        / "src"
        / "calculator.py"
    ).read_text(encoding="utf-8")

    assert "multiply" not in original_source


def test_project_orchestrator_blocks_failed_validation(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path / "repository")

    orchestrator = ProjectOrchestrator(
        failing_execution
    )

    request = FactoryRunRequest(
        project_id="project-2",
        run_id="run-2",
        repository_path=str(repository),
        objective="Introduce invalid implementation",
        workspace_root=str(tmp_path / "workspaces"),
        report_root=str(tmp_path / "reports"),
        knowledge_root=str(tmp_path / "knowledge"),
        allowed_change_paths=[
            "src",
            "tests",
        ],
        validation_commands=[
            [
                sys.executable,
                "-m",
                "pytest",
            ]
        ],
        acceptance_criteria=[
            "Existing tests remain passing",
        ],
    )

    import asyncio

    result = asyncio.run(
        orchestrator.run(request)
    )

    assert result.phase is FactoryRunPhase.COMPLETED
    assert result.validation is not None
    assert result.validation.passed is False
    assert result.review is not None
    assert (
        result.review.decision
        is ReviewDecision.CHANGES_REQUIRED
    )
    assert result.completion is not None
    assert (
        result.completion.status
        is CompletionStatus.BLOCKED
    )
    assert result.delivery is not None
    assert result.knowledge is None

    knowledge = FileKnowledgeStore(
        tmp_path / "knowledge"
    ).list("projects")

    assert knowledge == []

    assert git(
        repository,
        "status",
        "--porcelain",
    ) == ""


def test_project_orchestrator_records_execution_failure(
    tmp_path: Path,
) -> None:
    repository = create_repository(tmp_path / "repository")

    async def broken_execution(
        request,
        workspace,
        plan,
    ):
        raise RuntimeError("execution failed")

    orchestrator = ProjectOrchestrator(
        broken_execution
    )

    request = FactoryRunRequest(
        project_id="project-3",
        run_id="run-3",
        repository_path=str(repository),
        objective="Fail during execution",
        workspace_root=str(tmp_path / "workspaces"),
        report_root=str(tmp_path / "reports"),
        knowledge_root=str(tmp_path / "knowledge"),
    )

    import asyncio

    result = asyncio.run(
        orchestrator.run(request)
    )

    assert result.phase is FactoryRunPhase.FAILED
    assert result.failure_reason == "execution failed"
    assert result.events[-1].phase is FactoryRunPhase.FAILED
    assert result.events[-1].data == {
        "error": "execution failed"
    }

    assert git(
        repository,
        "status",
        "--porcelain",
    ) == ""
