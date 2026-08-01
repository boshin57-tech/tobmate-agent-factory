from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from af_core.assurance.completion import (
    CompletionDecision,
    CompletionStatus,
)
from af_core.assurance.reviewer import (
    ReviewDecision,
    ReviewResult,
)
from af_core.assurance.validator import ValidationResult

from .store import KnowledgeRecord


class PromotionStatus(StrEnum):
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"


class PromotionInput(BaseModel):
    category: str
    title: str
    summary: str
    repository_fingerprint: str | None = None
    tags: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    validation: ValidationResult
    review: ReviewResult
    completion: CompletionDecision


class PromotionDecision(BaseModel):
    status: PromotionStatus
    reasons: list[str] = Field(default_factory=list)
    record: KnowledgeRecord | None = None


class KnowledgePromoter:
    def promote(
        self,
        promotion_input: PromotionInput,
    ) -> PromotionDecision:
        reasons: list[str] = []

        if not promotion_input.validation.passed:
            reasons.append(
                "Validation did not pass."
            )

        if (
            promotion_input.review.decision
            is not ReviewDecision.APPROVED
        ):
            reasons.append(
                "Review did not approve the change."
            )

        if (
            promotion_input.completion.status
            is not CompletionStatus.COMPLETE
        ):
            reasons.append(
                "Completion auditor did not mark the run complete."
            )

        if not promotion_input.evidence_refs:
            reasons.append(
                "No evidence references were supplied."
            )

        if reasons:
            return PromotionDecision(
                status=PromotionStatus.REJECTED,
                reasons=reasons,
            )

        confidence = self._confidence(
            promotion_input,
        )

        record = KnowledgeRecord(
            category=promotion_input.category,
            title=promotion_input.title,
            summary=promotion_input.summary,
            repository_fingerprint=(
                promotion_input.repository_fingerprint
            ),
            tags=promotion_input.tags,
            evidence_refs=promotion_input.evidence_refs,
            confidence=confidence,
        )

        return PromotionDecision(
            status=PromotionStatus.PROMOTED,
            reasons=[
                "Validation passed.",
                "Review approved.",
                "Completion was confirmed.",
                "Evidence references are available.",
            ],
            record=record,
        )

    def _confidence(
        self,
        promotion_input: PromotionInput,
    ) -> float:
        evidence_count = len(
            set(promotion_input.evidence_refs)
        )

        return min(
            1.0,
            0.8 + min(evidence_count, 4) * 0.05,
        )
