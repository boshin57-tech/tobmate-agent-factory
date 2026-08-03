from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from .negotiation_models import (
    NegotiationCriterion,
)


class ProposalScoringWeights(BaseModel):
    """
    Weighted criteria used to evaluate negotiation proposals.

    All weights must be non-negative. They do not need to sum to 1;
    the scoring engine normalizes them internally.
    """

    quality: float = 1.0
    cost: float = 1.0
    speed: float = 1.0
    risk: float = 1.0
    security: float = 1.0
    reliability: float = 1.0
    maintainability: float = 1.0
    confidence: float = 0.5

    @field_validator("*")
    @classmethod
    def validate_weight(
        cls,
        value: float,
    ) -> float:
        if value < 0:
            raise ValueError(
                "proposal scoring weights "
                "must not be negative"
            )

        return value

    @property
    def total_weight(self) -> float:
        return (
            self.quality
            + self.cost
            + self.speed
            + self.risk
            + self.security
            + self.reliability
            + self.maintainability
            + self.confidence
        )


class ProposalScoringPolicy(BaseModel):
    """
    Limits and defaults used when converting proposal data
    into comparable scores.
    """

    weights: ProposalScoringWeights = Field(
        default_factory=ProposalScoringWeights
    )

    maximum_cost: float = 100.0
    maximum_duration_minutes: int = 1440

    default_security_score: float = 50.0
    default_reliability_score: float = 50.0
    default_maintainability_score: float = 50.0

    minimum_acceptable_score: float = 60.0

    @field_validator("maximum_cost")
    @classmethod
    def validate_maximum_cost(
        cls,
        value: float,
    ) -> float:
        if value <= 0:
            raise ValueError(
                "maximum_cost must be positive"
            )

        return value

    @field_validator(
        "maximum_duration_minutes"
    )
    @classmethod
    def validate_maximum_duration(
        cls,
        value: int,
    ) -> int:
        if value <= 0:
            raise ValueError(
                "maximum_duration_minutes "
                "must be positive"
            )

        return value

    @field_validator(
        "default_security_score",
        "default_reliability_score",
        "default_maintainability_score",
        "minimum_acceptable_score",
    )
    @classmethod
    def validate_percentage(
        cls,
        value: float,
    ) -> float:
        if not 0.0 <= value <= 100.0:
            raise ValueError(
                "score must be between 0 and 100"
            )

        return value


class ProposalScoreBreakdown(BaseModel):
    proposal_id: str
    proposer_agent_id: str

    quality_score: float = 0.0
    cost_score: float = 0.0
    speed_score: float = 0.0
    risk_score: float = 0.0
    security_score: float = 0.0
    reliability_score: float = 0.0
    maintainability_score: float = 0.0
    confidence_score: float = 0.0

    weighted_score: float = 0.0

    acceptable: bool = False

    strengths: list[str] = Field(
        default_factory=list
    )

    weaknesses: list[str] = Field(
        default_factory=list
    )

    criterion_scores: dict[
        NegotiationCriterion,
        float,
    ] = Field(
        default_factory=dict
    )


class ProposalRankingResult(BaseModel):
    session_id: str

    ranked_proposal_ids: list[str] = Field(
        default_factory=list
    )

    scores: list[
        ProposalScoreBreakdown
    ] = Field(
        default_factory=list
    )

    best_proposal_id: str | None = None

    acceptable_proposal_ids: list[str] = Field(
        default_factory=list
    )


class CounterProposalRecommendation(BaseModel):
    parent_proposal_id: str

    recommended_title: str
    recommended_summary: str

    target_criteria: list[
        NegotiationCriterion
    ] = Field(
        default_factory=list
    )

    suggested_changes: list[str] = Field(
        default_factory=list
    )

    suggested_estimated_cost: float | None = None

    suggested_duration_minutes: int | None = None

    suggested_expected_quality: float | None = None
    suggested_risk_score: float | None = None
    suggested_confidence_score: float | None = None

    expected_score_improvement: float = 0.0

    rationale: list[str] = Field(
        default_factory=list
    )
