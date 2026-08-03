from __future__ import annotations

from .negotiation_models import (
    NegotiationCriterion,
    NegotiationProposal,
    ProposalStatus,
)
from .proposal_scoring_models import (
    ProposalRankingResult,
    ProposalScoreBreakdown,
    ProposalScoringPolicy,
)


class ProposalScoringEngine:
    """
    Produces normalized, explainable proposal scores.

    Higher is better for every normalized criterion:
    - Quality, security, reliability, maintainability, confidence:
      direct percentage scores.
    - Cost and duration:
      lower values produce higher scores.
    - Risk:
      lower risk produces a higher normalized score.
    """

    def __init__(
        self,
        policy: ProposalScoringPolicy | None = None,
    ) -> None:
        self._policy = (
            policy
            or ProposalScoringPolicy()
        )

        if (
            self._policy.weights.total_weight
            <= 0
        ):
            raise ValueError(
                "at least one proposal scoring "
                "weight must be positive"
            )

    def score(
        self,
        proposal: NegotiationProposal,
    ) -> ProposalScoreBreakdown:
        quality = self._clamp(
            proposal.expected_quality
        )

        cost = self._inverse_ratio_score(
            value=proposal.estimated_cost,
            maximum=self._policy.maximum_cost,
        )

        speed = self._inverse_ratio_score(
            value=float(
                proposal
                .estimated_duration_minutes
            ),
            maximum=float(
                self._policy
                .maximum_duration_minutes
            ),
        )

        risk = self._clamp(
            100.0 - proposal.risk_score
        )

        security = self._metadata_score(
            proposal=proposal,
            key="security_score",
            default=(
                self._policy
                .default_security_score
            ),
        )

        reliability = self._metadata_score(
            proposal=proposal,
            key="reliability_score",
            default=(
                self._policy
                .default_reliability_score
            ),
        )

        maintainability = self._metadata_score(
            proposal=proposal,
            key="maintainability_score",
            default=(
                self._policy
                .default_maintainability_score
            ),
        )

        confidence = self._clamp(
            proposal.confidence_score
        )

        weights = self._policy.weights

        weighted_sum = (
            quality * weights.quality
            + cost * weights.cost
            + speed * weights.speed
            + risk * weights.risk
            + security * weights.security
            + reliability
            * weights.reliability
            + maintainability
            * weights.maintainability
            + confidence
            * weights.confidence
        )

        weighted_score = (
            weighted_sum
            / weights.total_weight
        )

        criterion_scores = {
            NegotiationCriterion.QUALITY:
                quality,
            NegotiationCriterion.COST:
                cost,
            NegotiationCriterion.SPEED:
                speed,
            NegotiationCriterion.RISK:
                risk,
            NegotiationCriterion.SECURITY:
                security,
            NegotiationCriterion.RELIABILITY:
                reliability,
            NegotiationCriterion.MAINTAINABILITY:
                maintainability,
        }

        strengths: list[str] = []
        weaknesses: list[str] = []

        for criterion, value in (
            criterion_scores.items()
        ):
            if value >= 80.0:
                strengths.append(
                    f"strong {criterion.value}"
                )
            elif value < 60.0:
                weaknesses.append(
                    f"weak {criterion.value}"
                )

        if confidence >= 80.0:
            strengths.append(
                "high proposer confidence"
            )
        elif confidence < 60.0:
            weaknesses.append(
                "low proposer confidence"
            )

        if (
            proposal.status
            in {
                ProposalStatus.WITHDRAWN,
                ProposalStatus.REJECTED,
                ProposalStatus.SUPERSEDED,
            }
        ):
            weaknesses.append(
                "proposal is not active"
            )

            weighted_score = 0.0

        acceptable = (
            weighted_score
            >= self._policy
            .minimum_acceptable_score
            and proposal.status
            not in {
                ProposalStatus.WITHDRAWN,
                ProposalStatus.REJECTED,
                ProposalStatus.SUPERSEDED,
            }
        )

        return ProposalScoreBreakdown(
            proposal_id=proposal.proposal_id,
            proposer_agent_id=(
                proposal.proposer_agent_id
            ),
            quality_score=round(
                quality,
                4,
            ),
            cost_score=round(
                cost,
                4,
            ),
            speed_score=round(
                speed,
                4,
            ),
            risk_score=round(
                risk,
                4,
            ),
            security_score=round(
                security,
                4,
            ),
            reliability_score=round(
                reliability,
                4,
            ),
            maintainability_score=round(
                maintainability,
                4,
            ),
            confidence_score=round(
                confidence,
                4,
            ),
            weighted_score=round(
                weighted_score,
                4,
            ),
            acceptable=acceptable,
            strengths=strengths,
            weaknesses=weaknesses,
            criterion_scores=(
                criterion_scores
            ),
        )

    def rank(
        self,
        *,
        session_id: str,
        proposals: list[
            NegotiationProposal
        ],
    ) -> ProposalRankingResult:
        scores = [
            self.score(proposal)
            for proposal in proposals
        ]

        scores.sort(
            key=lambda item: (
                item.weighted_score,
                item.proposal_id,
            ),
            reverse=True,
        )

        ranked_ids = [
            item.proposal_id
            for item in scores
        ]

        acceptable_ids = [
            item.proposal_id
            for item in scores
            if item.acceptable
        ]

        return ProposalRankingResult(
            session_id=session_id,
            ranked_proposal_ids=ranked_ids,
            scores=scores,
            best_proposal_id=(
                ranked_ids[0]
                if ranked_ids
                else None
            ),
            acceptable_proposal_ids=(
                acceptable_ids
            ),
        )

    @property
    def policy(
        self,
    ) -> ProposalScoringPolicy:
        return self._policy

    @staticmethod
    def _clamp(
        value: float,
    ) -> float:
        return max(
            0.0,
            min(100.0, value),
        )

    @classmethod
    def _inverse_ratio_score(
        cls,
        *,
        value: float,
        maximum: float,
    ) -> float:
        if value <= 0:
            return 100.0

        ratio = min(
            1.0,
            value / maximum,
        )

        return cls._clamp(
            (1.0 - ratio) * 100.0
        )

    @classmethod
    def _metadata_score(
        cls,
        *,
        proposal: NegotiationProposal,
        key: str,
        default: float,
    ) -> float:
        raw = proposal.metadata.get(
            key
        )

        if raw is None:
            return cls._clamp(default)

        try:
            return cls._clamp(
                float(raw)
            )
        except (
            TypeError,
            ValueError,
        ):
            return cls._clamp(default)
