from __future__ import annotations

from .negotiation_models import (
    NegotiationCriterion,
    NegotiationProposal,
)
from .proposal_scoring_engine import (
    ProposalScoringEngine,
)
from .proposal_scoring_models import (
    CounterProposalRecommendation,
    ProposalScoreBreakdown,
)


class CounterProposalIntelligence:
    """
    Analyzes proposal weaknesses and recommends a stronger
    counter-proposal profile.

    It does not autonomously submit a proposal. It produces an
    explainable recommendation that an authorized Agent may use.
    """

    def __init__(
        self,
        scoring_engine: (
            ProposalScoringEngine
            | None
        ) = None,
    ) -> None:
        self._scoring_engine = (
            scoring_engine
            or ProposalScoringEngine()
        )

    def recommend(
        self,
        proposal: NegotiationProposal,
    ) -> CounterProposalRecommendation:
        score = self._scoring_engine.score(
            proposal
        )

        target_criteria: list[
            NegotiationCriterion
        ] = []

        suggested_changes: list[str] = []
        rationale: list[str] = []

        suggested_cost: float | None = None
        suggested_duration: int | None = None
        suggested_quality: float | None = None
        suggested_risk: float | None = None
        suggested_confidence: float | None = None

        criterion_scores = (
            score.criterion_scores
        )

        if (
            criterion_scores[
                NegotiationCriterion.COST
            ]
            < 60.0
        ):
            target_criteria.append(
                NegotiationCriterion.COST
            )

            suggested_cost = round(
                proposal.estimated_cost
                * 0.85,
                4,
            )

            suggested_changes.append(
                "reduce estimated implementation cost"
            )

            rationale.append(
                "current cost score is below "
                "the preferred threshold"
            )

        if (
            criterion_scores[
                NegotiationCriterion.SPEED
            ]
            < 60.0
        ):
            target_criteria.append(
                NegotiationCriterion.SPEED
            )

            suggested_duration = max(
                1,
                int(
                    proposal
                    .estimated_duration_minutes
                    * 0.85
                ),
            )

            suggested_changes.append(
                "shorten implementation duration"
            )

            rationale.append(
                "current delivery speed is weak"
            )

        if (
            criterion_scores[
                NegotiationCriterion.QUALITY
            ]
            < 70.0
        ):
            target_criteria.append(
                NegotiationCriterion.QUALITY
            )

            suggested_quality = min(
                100.0,
                max(
                    75.0,
                    proposal.expected_quality
                    + 10.0,
                ),
            )

            suggested_changes.append(
                "add stronger validation and "
                "quality controls"
            )

            rationale.append(
                "expected quality requires improvement"
            )

        if (
            criterion_scores[
                NegotiationCriterion.RISK
            ]
            < 70.0
        ):
            target_criteria.append(
                NegotiationCriterion.RISK
            )

            suggested_risk = max(
                0.0,
                proposal.risk_score
                - 15.0,
            )

            suggested_changes.append(
                "reduce risk through staged execution "
                "and rollback controls"
            )

            rationale.append(
                "current risk exposure is too high"
            )

        for criterion in (
            NegotiationCriterion.SECURITY,
            NegotiationCriterion.RELIABILITY,
            NegotiationCriterion.MAINTAINABILITY,
        ):
            if (
                criterion_scores[criterion]
                < 70.0
            ):
                target_criteria.append(
                    criterion
                )

                suggested_changes.append(
                    (
                        f"strengthen "
                        f"{criterion.value} controls"
                    )
                )

                rationale.append(
                    (
                        f"{criterion.value} score "
                        "is below target"
                    )
                )

        if score.confidence_score < 70.0:
            suggested_confidence = min(
                100.0,
                max(
                    75.0,
                    proposal.confidence_score
                    + 10.0,
                ),
            )

            suggested_changes.append(
                "increase confidence with evidence, "
                "tests, or prior results"
            )

            rationale.append(
                "proposal confidence is below target"
            )

        if not suggested_changes:
            suggested_changes.append(
                "retain the current proposal structure"
            )

            rationale.append(
                "proposal has no material scoring weakness"
            )

        projected = self._projected_proposal(
            proposal=proposal,
            suggested_cost=suggested_cost,
            suggested_duration=(
                suggested_duration
            ),
            suggested_quality=(
                suggested_quality
            ),
            suggested_risk=suggested_risk,
            suggested_confidence=(
                suggested_confidence
            ),
            score=score,
        )

        projected_score = (
            self._scoring_engine
            .score(projected)
        )

        return CounterProposalRecommendation(
            parent_proposal_id=(
                proposal.proposal_id
            ),
            recommended_title=(
                f"Counter: {proposal.title}"
            ),
            recommended_summary=(
                "Revise the original proposal "
                "to improve its weakest criteria."
            ),
            target_criteria=(
                self._unique_criteria(
                    target_criteria
                )
            ),
            suggested_changes=(
                suggested_changes
            ),
            suggested_estimated_cost=(
                suggested_cost
            ),
            suggested_duration_minutes=(
                suggested_duration
            ),
            suggested_expected_quality=(
                suggested_quality
            ),
            suggested_risk_score=(
                suggested_risk
            ),
            suggested_confidence_score=(
                suggested_confidence
            ),
            expected_score_improvement=round(
                max(
                    0.0,
                    projected_score
                    .weighted_score
                    - score.weighted_score,
                ),
                4,
            ),
            rationale=rationale,
        )

    def create_counter_proposal(
        self,
        *,
        original: NegotiationProposal,
        proposer_agent_id: str,
        recommendation: (
            CounterProposalRecommendation
            | None
        ) = None,
    ) -> NegotiationProposal:
        recommendation = (
            recommendation
            or self.recommend(original)
        )

        metadata = dict(
            original.metadata
        )

        target_values = {
            NegotiationCriterion.SECURITY:
                "security_score",
            NegotiationCriterion.RELIABILITY:
                "reliability_score",
            NegotiationCriterion.MAINTAINABILITY:
                "maintainability_score",
        }

        for criterion, metadata_key in (
            target_values.items()
        ):
            if (
                criterion
                in recommendation.target_criteria
            ):
                current = self._metadata_float(
                    metadata,
                    metadata_key,
                    50.0,
                )

                metadata[metadata_key] = str(
                    min(
                        100.0,
                        current + 15.0,
                    )
                )

        metadata[
            "counter_intelligence_generated"
        ] = "true"

        return NegotiationProposal(
            session_id=original.session_id,
            proposer_agent_id=(
                proposer_agent_id
            ),
            title=(
                recommendation
                .recommended_title
            ),
            summary=(
                recommendation
                .recommended_summary
            ),
            implementation_plan=[
                *original.implementation_plan,
                *recommendation
                .suggested_changes,
            ],
            estimated_cost=(
                recommendation
                .suggested_estimated_cost
                if recommendation
                .suggested_estimated_cost
                is not None
                else original.estimated_cost
            ),
            estimated_duration_minutes=(
                recommendation
                .suggested_duration_minutes
                if recommendation
                .suggested_duration_minutes
                is not None
                else original
                .estimated_duration_minutes
            ),
            expected_quality=(
                recommendation
                .suggested_expected_quality
                if recommendation
                .suggested_expected_quality
                is not None
                else original.expected_quality
            ),
            risk_score=(
                recommendation
                .suggested_risk_score
                if recommendation
                .suggested_risk_score
                is not None
                else original.risk_score
            ),
            confidence_score=(
                recommendation
                .suggested_confidence_score
                if recommendation
                .suggested_confidence_score
                is not None
                else original.confidence_score
            ),
            required_capabilities=set(
                original
                .required_capabilities
            ),
            dependencies=list(
                original.dependencies
            ),
            parent_proposal_id=(
                original.proposal_id
            ),
            metadata=metadata,
        )

    def _projected_proposal(
        self,
        *,
        proposal: NegotiationProposal,
        suggested_cost: float | None,
        suggested_duration: int | None,
        suggested_quality: float | None,
        suggested_risk: float | None,
        suggested_confidence: float | None,
        score: ProposalScoreBreakdown,
    ) -> NegotiationProposal:
        metadata = dict(
            proposal.metadata
        )

        criterion_to_metadata = {
            NegotiationCriterion.SECURITY:
                "security_score",
            NegotiationCriterion.RELIABILITY:
                "reliability_score",
            NegotiationCriterion.MAINTAINABILITY:
                "maintainability_score",
        }

        for criterion, key in (
            criterion_to_metadata.items()
        ):
            current_score = (
                score.criterion_scores[
                    criterion
                ]
            )

            if current_score < 70.0:
                metadata[key] = str(
                    min(
                        100.0,
                        current_score + 15.0,
                    )
                )

        return proposal.model_copy(
            update={
                "estimated_cost": (
                    suggested_cost
                    if suggested_cost
                    is not None
                    else proposal
                    .estimated_cost
                ),
                "estimated_duration_minutes": (
                    suggested_duration
                    if suggested_duration
                    is not None
                    else proposal
                    .estimated_duration_minutes
                ),
                "expected_quality": (
                    suggested_quality
                    if suggested_quality
                    is not None
                    else proposal
                    .expected_quality
                ),
                "risk_score": (
                    suggested_risk
                    if suggested_risk
                    is not None
                    else proposal.risk_score
                ),
                "confidence_score": (
                    suggested_confidence
                    if suggested_confidence
                    is not None
                    else proposal
                    .confidence_score
                ),
                "metadata": metadata,
            }
        )

    @staticmethod
    def _unique_criteria(
        criteria: list[
            NegotiationCriterion
        ],
    ) -> list[
        NegotiationCriterion
    ]:
        seen: set[
            NegotiationCriterion
        ] = set()

        ordered: list[
            NegotiationCriterion
        ] = []

        for criterion in criteria:
            if criterion in seen:
                continue

            seen.add(criterion)
            ordered.append(criterion)

        return ordered

    @staticmethod
    def _metadata_float(
        metadata: dict[str, str],
        key: str,
        default: float,
    ) -> float:
        try:
            return float(
                metadata.get(
                    key,
                    str(default),
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            return default
