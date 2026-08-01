from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .reviewer import ReviewDecision, ReviewResult
from .validator import ValidationResult


class CompletionStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    BLOCKED = "BLOCKED"


class CompletionInput(BaseModel):
    required_task_ids: list[str]
    completed_task_ids: list[str]
    required_evidence: list[str] = Field(default_factory=list)
    available_evidence: list[str] = Field(default_factory=list)
    validation: ValidationResult
    review: ReviewResult
    acceptance_criteria: list[str] = Field(default_factory=list)
    satisfied_criteria: list[str] = Field(default_factory=list)


class CompletionDecision(BaseModel):
    status: CompletionStatus
    satisfied_requirements: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommended_action: str


class CompletionAuditor:
    def audit(
        self,
        completion_input: CompletionInput,
    ) -> CompletionDecision:
        satisfied: list[str] = []
        missing: list[str] = []
        risks: list[str] = []

        required_tasks = set(completion_input.required_task_ids)
        completed_tasks = set(completion_input.completed_task_ids)
        missing_tasks = sorted(required_tasks - completed_tasks)

        if missing_tasks:
            missing.append(
                "Incomplete tasks: " + ", ".join(missing_tasks)
            )
        else:
            satisfied.append("All required tasks are complete.")

        required_evidence = set(completion_input.required_evidence)
        available_evidence = set(completion_input.available_evidence)
        missing_evidence = sorted(
            required_evidence - available_evidence
        )

        if missing_evidence:
            missing.append(
                "Missing evidence: " + ", ".join(missing_evidence)
            )
        else:
            satisfied.append("All required evidence is available.")

        if completion_input.validation.passed:
            satisfied.append("Required validation checks passed.")
        else:
            missing.append("Required validation checks failed.")
            risks.extend(completion_input.validation.failures)

        if completion_input.review.decision is ReviewDecision.APPROVED:
            satisfied.append("Review approved the change set.")
        elif (
            completion_input.review.decision
            is ReviewDecision.CHANGES_REQUIRED
        ):
            missing.append("Review requires changes.")
        else:
            missing.append("Review rejected the change set.")

        required_criteria = set(
            completion_input.acceptance_criteria
        )
        satisfied_criteria = set(
            completion_input.satisfied_criteria
        )
        unsatisfied_criteria = sorted(
            required_criteria - satisfied_criteria
        )

        if unsatisfied_criteria:
            missing.append(
                "Unsatisfied acceptance criteria: "
                + ", ".join(unsatisfied_criteria)
            )
        else:
            satisfied.append(
                "All acceptance criteria are satisfied."
            )

        status = self._status(
            completion_input=completion_input,
            missing_tasks=missing_tasks,
            missing_evidence=missing_evidence,
            unsatisfied_criteria=unsatisfied_criteria,
        )

        if status is CompletionStatus.COMPLETE:
            action = "Prepare delivery artifacts."
        elif status is CompletionStatus.BLOCKED:
            action = (
                "Resolve validation or review blockers before retrying."
            )
        else:
            action = (
                "Complete missing tasks, evidence, or acceptance criteria."
            )

        return CompletionDecision(
            status=status,
            satisfied_requirements=satisfied,
            missing_requirements=missing,
            risks=risks,
            recommended_action=action,
        )

    def _status(
        self,
        *,
        completion_input: CompletionInput,
        missing_tasks: list[str],
        missing_evidence: list[str],
        unsatisfied_criteria: list[str],
    ) -> CompletionStatus:
        if not completion_input.validation.passed:
            return CompletionStatus.BLOCKED

        if completion_input.review.decision in {
            ReviewDecision.CHANGES_REQUIRED,
            ReviewDecision.REJECTED,
        }:
            return CompletionStatus.BLOCKED

        if (
            missing_tasks
            or missing_evidence
            or unsatisfied_criteria
        ):
            return CompletionStatus.INCOMPLETE

        return CompletionStatus.COMPLETE
