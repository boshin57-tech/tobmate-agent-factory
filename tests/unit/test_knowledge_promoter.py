from af_core.assurance.completion import (
    CompletionDecision,
    CompletionStatus,
)
from af_core.assurance.reviewer import (
    ReviewDecision,
    ReviewResult,
)
from af_core.assurance.validator import ValidationResult
from af_core.knowledge.promoter import (
    KnowledgePromoter,
    PromotionInput,
    PromotionStatus,
)


def validation(passed: bool) -> ValidationResult:
    return ValidationResult(
        passed=passed,
        checks=[],
        failures=[] if passed else ["test failed"],
        evidence_summary="validation",
    )


def review(decision: ReviewDecision) -> ReviewResult:
    return ReviewResult(
        decision=decision,
        findings=[],
        summary="review",
    )


def completion(
    status: CompletionStatus,
) -> CompletionDecision:
    return CompletionDecision(
        status=status,
        satisfied_requirements=[],
        missing_requirements=[],
        risks=[],
        recommended_action="next",
    )


def test_promoter_creates_record_for_completed_run() -> None:
    result = KnowledgePromoter().promote(
        PromotionInput(
            category="patterns",
            title="Validated pattern",
            summary="Reusable implementation pattern.",
            tags=["validated"],
            evidence_refs=[
                "validation.json",
                "review.json",
            ],
            validation=validation(True),
            review=review(ReviewDecision.APPROVED),
            completion=completion(
                CompletionStatus.COMPLETE
            ),
        )
    )

    assert result.status is PromotionStatus.PROMOTED
    assert result.record is not None
    assert result.record.confidence == 0.9


def test_promoter_rejects_failed_or_unevidenced_run() -> None:
    result = KnowledgePromoter().promote(
        PromotionInput(
            category="patterns",
            title="Rejected pattern",
            summary="Should not promote.",
            evidence_refs=[],
            validation=validation(False),
            review=review(
                ReviewDecision.CHANGES_REQUIRED
            ),
            completion=completion(
                CompletionStatus.BLOCKED
            ),
        )
    )

    assert result.status is PromotionStatus.REJECTED
    assert result.record is None
    assert len(result.reasons) == 4
