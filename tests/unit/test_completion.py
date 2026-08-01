from af_core.assurance.completion import (
    CompletionAuditor,
    CompletionInput,
    CompletionStatus,
)
from af_core.assurance.reviewer import (
    ReviewDecision,
    ReviewResult,
)
from af_core.assurance.validator import ValidationResult


def validation(passed: bool) -> ValidationResult:
    return ValidationResult(
        passed=passed,
        checks=[],
        failures=[] if passed else ["pytest failed"],
        evidence_summary="validation summary",
    )


def review(decision: ReviewDecision) -> ReviewResult:
    return ReviewResult(
        decision=decision,
        findings=[],
        summary="review summary",
    )


def test_completion_auditor_marks_complete() -> None:
    decision = CompletionAuditor().audit(
        CompletionInput(
            required_task_ids=["task-1", "task-2"],
            completed_task_ids=["task-1", "task-2"],
            required_evidence=[
                "validation",
                "review",
                "diff",
            ],
            available_evidence=[
                "validation",
                "review",
                "diff",
            ],
            validation=validation(True),
            review=review(ReviewDecision.APPROVED),
            acceptance_criteria=[
                "Tests pass",
                "Review approved",
            ],
            satisfied_criteria=[
                "Tests pass",
                "Review approved",
            ],
        )
    )

    assert decision.status is CompletionStatus.COMPLETE
    assert decision.missing_requirements == []
    assert decision.recommended_action == (
        "Prepare delivery artifacts."
    )


def test_completion_auditor_marks_incomplete_for_missing_evidence() -> None:
    decision = CompletionAuditor().audit(
        CompletionInput(
            required_task_ids=["task-1"],
            completed_task_ids=["task-1"],
            required_evidence=["validation", "review"],
            available_evidence=["validation"],
            validation=validation(True),
            review=review(ReviewDecision.APPROVED),
        )
    )

    assert decision.status is CompletionStatus.INCOMPLETE
    assert any(
        "Missing evidence" in item
        for item in decision.missing_requirements
    )


def test_completion_auditor_blocks_failed_validation() -> None:
    decision = CompletionAuditor().audit(
        CompletionInput(
            required_task_ids=["task-1"],
            completed_task_ids=["task-1"],
            validation=validation(False),
            review=review(ReviewDecision.APPROVED),
        )
    )

    assert decision.status is CompletionStatus.BLOCKED
    assert "pytest failed" in decision.risks


def test_completion_auditor_blocks_review_rejection() -> None:
    decision = CompletionAuditor().audit(
        CompletionInput(
            required_task_ids=["task-1"],
            completed_task_ids=["task-1"],
            validation=validation(True),
            review=review(ReviewDecision.REJECTED),
        )
    )

    assert decision.status is CompletionStatus.BLOCKED
    assert any(
        "Review rejected" in item
        for item in decision.missing_requirements
    )


def test_completion_auditor_detects_incomplete_tasks() -> None:
    decision = CompletionAuditor().audit(
        CompletionInput(
            required_task_ids=["task-1", "task-2"],
            completed_task_ids=["task-1"],
            validation=validation(True),
            review=review(ReviewDecision.APPROVED),
        )
    )

    assert decision.status is CompletionStatus.INCOMPLETE
    assert any(
        "task-2" in item
        for item in decision.missing_requirements
    )
