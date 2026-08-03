"""Validation and completion auditing for autonomous project runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping

from af_core.orchestrator.project_execution_models import (
    ProjectRunState,
    ProjectTaskStatus,
)


class ProjectCompletionAuditError(ValueError):
    """Raised when project completion auditing is invalid."""


class ProjectValidationStatus(str, Enum):
    """Validation result for one project task or artifact."""

    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"
    NOT_RUN = "not_run"


class ProjectCompletionDecision(str, Enum):
    """Final completion decision for one project run."""

    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ProjectValidationResult:
    """Validation evidence for one project task."""

    task_id: str
    status: ProjectValidationStatus
    validator_id: str
    checked_at: float
    findings: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise ProjectCompletionAuditError(
                "validation task_id must not be empty"
            )

        if not self.validator_id.strip():
            raise ProjectCompletionAuditError(
                "validator_id must not be empty"
            )


@dataclass(frozen=True, slots=True)
class ProjectCompletionAudit:
    """Immutable final audit result for a project run."""

    run_id: str
    project_id: str
    decision: ProjectCompletionDecision
    audited_at: float
    total_tasks: int
    succeeded_tasks: int
    failed_tasks: int
    skipped_tasks: int
    cancelled_tasks: int
    validation_passed: int
    validation_failed: int
    validation_partial: int
    validation_not_run: int
    output_references: tuple[str, ...]
    reasons: tuple[str, ...]
    task_statuses: Mapping[str, str]
    metadata: Mapping[str, object] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ProjectCompletionAuditError(
                "audit run_id must not be empty"
            )

        if self.total_tasks < 1:
            raise ProjectCompletionAuditError(
                "audit requires at least one task"
            )


class ProjectCompletionAuditEngine:
    """Determine final project status from execution and validation."""

    def audit(
        self,
        state: ProjectRunState,
        *,
        validations: Iterable[
            ProjectValidationResult
        ] = (),
        now: float,
        metadata: Mapping[str, object] | None = None,
    ) -> ProjectCompletionAudit:
        """Produce a deterministic project completion decision."""

        if not state.tasks:
            raise ProjectCompletionAuditError(
                "project run has no tasks to audit"
            )

        validation_by_task: dict[
            str,
            ProjectValidationResult,
        ] = {}

        for validation in validations:
            if validation.task_id not in state.tasks:
                raise ProjectCompletionAuditError(
                    "validation references unknown task: "
                    f"{validation.task_id}"
                )

            if validation.task_id in validation_by_task:
                raise ProjectCompletionAuditError(
                    "duplicate validation result: "
                    f"{validation.task_id}"
                )

            validation_by_task[
                validation.task_id
            ] = validation

        succeeded = self._count(
            state,
            ProjectTaskStatus.SUCCEEDED,
        )
        failed = self._count(
            state,
            ProjectTaskStatus.FAILED,
        )
        skipped = self._count(
            state,
            ProjectTaskStatus.SKIPPED,
        )
        cancelled = self._count(
            state,
            ProjectTaskStatus.CANCELLED,
        )

        passed_validations = sum(
            result.status
            is ProjectValidationStatus.PASSED
            for result in validation_by_task.values()
        )
        failed_validations = sum(
            result.status
            is ProjectValidationStatus.FAILED
            for result in validation_by_task.values()
        )
        partial_validations = sum(
            result.status
            is ProjectValidationStatus.PARTIAL
            for result in validation_by_task.values()
        )

        not_run_validations = (
            len(state.tasks)
            - len(validation_by_task)
            + sum(
                result.status
                is ProjectValidationStatus.NOT_RUN
                for result in validation_by_task.values()
            )
        )

        nonterminal = tuple(
            task_id
            for task_id, task in state.tasks.items()
            if not task.terminal
        )

        reasons: list[str] = []

        if nonterminal:
            reasons.append(
                "nonterminal tasks remain: "
                + ", ".join(sorted(nonterminal))
            )

        if failed:
            reasons.append(
                f"{failed} task(s) failed"
            )

        if skipped:
            reasons.append(
                f"{skipped} task(s) skipped"
            )

        if cancelled:
            reasons.append(
                f"{cancelled} task(s) cancelled"
            )

        if failed_validations:
            reasons.append(
                f"{failed_validations} validation(s) failed"
            )

        if partial_validations:
            reasons.append(
                f"{partial_validations} validation(s) partial"
            )

        if not_run_validations:
            reasons.append(
                f"{not_run_validations} validation(s) not run"
            )

        decision = self._decision(
            total=len(state.tasks),
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            cancelled=cancelled,
            nonterminal=len(nonterminal),
            validation_failed=failed_validations,
            validation_partial=partial_validations,
            validation_not_run=not_run_validations,
        )

        if decision is ProjectCompletionDecision.COMPLETED:
            reasons.append(
                "all tasks and validations completed successfully"
            )

        outputs = tuple(
            sorted(
                {
                    task.output_reference
                    for task in state.tasks.values()
                    if task.output_reference is not None
                }
            )
        )

        return ProjectCompletionAudit(
            run_id=state.run_id,
            project_id=state.project_id,
            decision=decision,
            audited_at=now,
            total_tasks=len(state.tasks),
            succeeded_tasks=succeeded,
            failed_tasks=failed,
            skipped_tasks=skipped,
            cancelled_tasks=cancelled,
            validation_passed=passed_validations,
            validation_failed=failed_validations,
            validation_partial=partial_validations,
            validation_not_run=not_run_validations,
            output_references=outputs,
            reasons=tuple(reasons),
            task_statuses={
                task_id: task.status.value
                for task_id, task in sorted(
                    state.tasks.items()
                )
            },
            metadata=dict(metadata or {}),
        )

    @staticmethod
    def _count(
        state: ProjectRunState,
        status: ProjectTaskStatus,
    ) -> int:
        return sum(
            task.status is status
            for task in state.tasks.values()
        )

    @staticmethod
    def _decision(
        *,
        total: int,
        succeeded: int,
        failed: int,
        skipped: int,
        cancelled: int,
        nonterminal: int,
        validation_failed: int,
        validation_partial: int,
        validation_not_run: int,
    ) -> ProjectCompletionDecision:
        if (
            succeeded == total
            and failed == 0
            and skipped == 0
            and cancelled == 0
            and nonterminal == 0
            and validation_failed == 0
            and validation_partial == 0
            and validation_not_run == 0
        ):
            return ProjectCompletionDecision.COMPLETED

        if succeeded > 0:
            return ProjectCompletionDecision.PARTIAL

        return ProjectCompletionDecision.FAILED
