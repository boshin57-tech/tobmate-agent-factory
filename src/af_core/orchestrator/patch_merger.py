from __future__ import annotations

import subprocess
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from af_core.repository.git_client import GitClient
from af_core.workspace.manager import (
    WorkspaceManager,
    WorkspaceRecord,
)

from .parallel_models import AgentTaskResult


class PatchMergeStatus(StrEnum):
    CREATED = "CREATED"
    APPLYING = "APPLYING"
    COMPLETED = "COMPLETED"
    CONFLICTED = "CONFLICTED"
    FAILED = "FAILED"


class PatchApplication(BaseModel):
    task_id: str
    agent_name: str
    status: PatchMergeStatus
    changed_files: list[str] = Field(default_factory=list)
    error: str | None = None


class PatchMergeResult(BaseModel):
    successful: bool
    status: PatchMergeStatus
    integration_workspace: str
    integration_branch: str
    applications: list[PatchApplication] = Field(
        default_factory=list
    )
    changed_files: list[str] = Field(default_factory=list)
    diff_text: str = ""
    conflicting_task_id: str | None = None
    failure_reason: str | None = None


class PatchMergeError(RuntimeError):
    """Raised when patches cannot be safely integrated."""


class IntegrationPatchMerger:
    def __init__(
        self,
        *,
        integration_root: str | Path,
    ) -> None:
        self.integration_root = Path(
            integration_root
        ).expanduser().resolve()
        self.integration_root.mkdir(
            parents=True,
            exist_ok=True,
        )

    def merge(
        self,
        *,
        source_repository: str | Path,
        project_id: str,
        run_id: str,
        task_results: list[AgentTaskResult],
        base_revision: str = "HEAD",
    ) -> PatchMergeResult:
        successful_results = [
            result
            for result in task_results
            if result.success
        ]

        if not successful_results:
            raise PatchMergeError(
                "No successful Agent results are available."
            )

        manager = WorkspaceManager(
            self.integration_root
        )
        workspace = manager.create(
            source_repository=source_repository,
            project_id=f"{project_id}-integration",
            run_id=f"{run_id}-integration",
            base_revision=base_revision,
        )

        applications: list[PatchApplication] = []

        for task_result in successful_results:
            application = self._apply_patch(
                workspace=workspace,
                task_result=task_result,
            )
            applications.append(application)

            if application.status is not PatchMergeStatus.COMPLETED:
                return PatchMergeResult(
                    successful=False,
                    status=application.status,
                    integration_workspace=(
                        workspace.workspace_path
                    ),
                    integration_branch=workspace.branch,
                    applications=applications,
                    changed_files=self._status_paths(
                        workspace.workspace_path
                    ),
                    diff_text=self._diff(
                        workspace.workspace_path
                    ),
                    conflicting_task_id=task_result.task_id,
                    failure_reason=application.error,
                )

        changed_files = self._status_paths(
            workspace.workspace_path
        )
        diff_text = self._diff(
            workspace.workspace_path
        )

        return PatchMergeResult(
            successful=True,
            status=PatchMergeStatus.COMPLETED,
            integration_workspace=workspace.workspace_path,
            integration_branch=workspace.branch,
            applications=applications,
            changed_files=changed_files,
            diff_text=diff_text,
        )

    def _apply_patch(
        self,
        *,
        workspace: WorkspaceRecord,
        task_result: AgentTaskResult,
    ) -> PatchApplication:
        if not task_result.diff_text.strip():
            return PatchApplication(
                task_id=task_result.task_id,
                agent_name=task_result.agent_name,
                status=PatchMergeStatus.COMPLETED,
                changed_files=[],
            )

        workspace_path = Path(
            workspace.workspace_path
        ).resolve()

        process = subprocess.run(
            [
                "git",
                "apply",
                "--index",
                "--3way",
                "--whitespace=error",
                "-",
            ],
            cwd=workspace_path,
            input=task_result.diff_text,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )

        if process.returncode != 0:
            self._abort_failed_application(
                workspace_path
            )

            error = (
                process.stderr.strip()
                or process.stdout.strip()
                or "Patch application failed."
            )

            status = (
                PatchMergeStatus.CONFLICTED
                if self._looks_like_conflict(error)
                else PatchMergeStatus.FAILED
            )

            return PatchApplication(
                task_id=task_result.task_id,
                agent_name=task_result.agent_name,
                status=status,
                changed_files=[],
                error=error,
            )

        changed_files = self._status_paths(
            workspace_path
        )

        return PatchApplication(
            task_id=task_result.task_id,
            agent_name=task_result.agent_name,
            status=PatchMergeStatus.COMPLETED,
            changed_files=changed_files,
        )

    def _abort_failed_application(
        self,
        workspace_path: Path,
    ) -> None:
        subprocess.run(
            [
                "git",
                "reset",
                "--hard",
                "HEAD",
            ],
            cwd=workspace_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

    def _looks_like_conflict(
        self,
        error: str,
    ) -> bool:
        lowered = error.lower()

        markers = (
            "conflict",
            "does not apply",
            "patch failed",
            "with conflicts",
        )

        return any(
            marker in lowered
            for marker in markers
        )

    def _status_paths(
        self,
        workspace_path: str | Path,
    ) -> list[str]:
        lines = GitClient(
            workspace_path
        ).status_porcelain()

        paths: list[str] = []

        for line in lines:
            if len(line) < 4:
                continue

            value = line[3:].strip()

            if " -> " in value:
                value = value.split(
                    " -> ",
                    1,
                )[1]

            if value:
                paths.append(value)

        return sorted(set(paths))

    def _diff(
        self,
        workspace_path: str | Path,
    ) -> str:
        client = GitClient(
            workspace_path
        )

        staged = client.run(
            [
                "diff",
                "--cached",
                "--binary",
            ]
        ).stdout

        unstaged = client.run(
            [
                "diff",
                "--binary",
            ]
        ).stdout

        return "\n".join(
            part
            for part in (
                staged,
                unstaged,
            )
            if part
        )
