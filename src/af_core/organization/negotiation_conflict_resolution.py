from __future__ import annotations

from .consensus_models import (
    ConflictResolutionResult,
    ConflictResolutionStrategy,
    ConsensusFailureReason,
    ConsensusPolicy,
    ProposalConsensusResult,
)
from .negotiation_models import (
    NegotiationDecisionType,
    NegotiationSession,
)
from .proposal_scoring_engine import (
    ProposalScoringEngine,
)


class NegotiationConflictResolver:
    """
    Resolves proposal-selection conflicts after weighted voting.

    Resolution order:
    1. Any blocking veto causes escalation.
    2. One consensus proposal is selected directly.
    3. Multiple consensus proposals are compared by approval and vote
       score.
    4. Remaining ties may be resolved by proposal scoring.
    5. Quorum or approval failures request revision.
    6. No acceptable proposal may reject all proposals.
    """

    def __init__(
        self,
        *,
        policy: ConsensusPolicy | None = None,
        scoring_engine: (
            ProposalScoringEngine
            | None
        ) = None,
    ) -> None:
        self._policy = (
            policy
            or ConsensusPolicy()
        )

        self._scoring_engine = (
            scoring_engine
            or ProposalScoringEngine()
        )

    def resolve(
        self,
        *,
        session: NegotiationSession,
        proposal_results: list[
            ProposalConsensusResult
        ],
    ) -> ConflictResolutionResult:
        if not session.proposals:
            return ConflictResolutionResult(
                strategy=(
                    ConflictResolutionStrategy
                    .REJECT_ALL
                ),
                decision_type=(
                    NegotiationDecisionType
                    .REJECT_ALL
                ),
                reasons=[
                    "negotiation contains no proposals"
                ],
            )

        vetoed = [
            result
            for result in proposal_results
            if result.vetoed
        ]

        if (
            vetoed
            and self._policy
            .veto_blocks_consensus
        ):
            return ConflictResolutionResult(
                strategy=(
                    ConflictResolutionStrategy
                    .ESCALATE
                ),
                decision_type=(
                    NegotiationDecisionType
                    .ESCALATE
                ),
                conflicting_proposal_ids=[
                    result.proposal_id
                    for result in vetoed
                ],
                reasons=[
                    (
                        "one or more authorized "
                        "vetoes block automatic consensus"
                    )
                ],
                escalated=True,
            )

        consensus_results = [
            result
            for result in proposal_results
            if result.consensus_reached
        ]

        if len(consensus_results) == 1:
            selected = (
                consensus_results[0]
            )

            return ConflictResolutionResult(
                strategy=(
                    ConflictResolutionStrategy
                    .SELECT_HIGHEST_CONSENSUS
                ),
                decision_type=(
                    NegotiationDecisionType
                    .ACCEPT_PROPOSAL
                ),
                selected_proposal_id=(
                    selected.proposal_id
                ),
                reasons=[
                    (
                        "one proposal reached "
                        "weighted consensus"
                    )
                ],
            )

        if len(consensus_results) > 1:
            ordered = sorted(
                consensus_results,
                key=lambda result: (
                    result.approval_ratio,
                    result.average_vote_score,
                    result.approval_weight,
                ),
                reverse=True,
            )

            first = ordered[0]
            second = ordered[1]

            first_tuple = (
                first.approval_ratio,
                first.average_vote_score,
                first.approval_weight,
            )

            second_tuple = (
                second.approval_ratio,
                second.average_vote_score,
                second.approval_weight,
            )

            if not self._is_tied(
                first_tuple,
                second_tuple,
            ):
                return ConflictResolutionResult(
                    strategy=(
                        ConflictResolutionStrategy
                        .SELECT_HIGHEST_CONSENSUS
                    ),
                    decision_type=(
                        NegotiationDecisionType
                        .ACCEPT_PROPOSAL
                    ),
                    selected_proposal_id=(
                        first.proposal_id
                    ),
                    conflicting_proposal_ids=[
                        result.proposal_id
                        for result
                        in consensus_results
                    ],
                    reasons=[
                        (
                            "proposal with the strongest "
                            "weighted consensus was selected"
                        )
                    ],
                )

            if (
                self._policy
                .allow_scoring_tie_break
            ):
                ranking = (
                    self._scoring_engine.rank(
                        session_id=(
                            session.session_id
                        ),
                        proposals=[
                            proposal
                            for proposal
                            in session.proposals
                            if proposal.proposal_id
                            in {
                                result.proposal_id
                                for result
                                in consensus_results
                            }
                        ],
                    )
                )

                if (
                    ranking.best_proposal_id
                    is not None
                    and not self._ranking_tied(
                        ranking.scores
                    )
                ):
                    return ConflictResolutionResult(
                        strategy=(
                            ConflictResolutionStrategy
                            .SELECT_HIGHEST_PROPOSAL_SCORE
                        ),
                        decision_type=(
                            NegotiationDecisionType
                            .ACCEPT_PROPOSAL
                        ),
                        selected_proposal_id=(
                            ranking
                            .best_proposal_id
                        ),
                        conflicting_proposal_ids=[
                            result.proposal_id
                            for result
                            in consensus_results
                        ],
                        reasons=[
                            (
                                "weighted voting was tied; "
                                "proposal scoring resolved "
                                "the conflict"
                            )
                        ],
                    )

            return ConflictResolutionResult(
                strategy=(
                    ConflictResolutionStrategy
                    .ESCALATE
                ),
                decision_type=(
                    NegotiationDecisionType
                    .ESCALATE
                ),
                conflicting_proposal_ids=[
                    result.proposal_id
                    for result
                    in consensus_results
                ],
                reasons=[
                    (
                        "multiple proposals remain tied "
                        "after consensus and scoring"
                    )
                ],
                escalated=True,
            )

        failure_reasons = {
            reason
            for result in proposal_results
            for reason
            in result.failure_reasons
        }

        ranking = self._scoring_engine.rank(
            session_id=session.session_id,
            proposals=list(
                session.proposals
            ),
        )

        if (
            self._policy
            .reject_all_when_no_acceptable_proposal
            and not ranking
            .acceptable_proposal_ids
        ):
            return ConflictResolutionResult(
                strategy=(
                    ConflictResolutionStrategy
                    .REJECT_ALL
                ),
                decision_type=(
                    NegotiationDecisionType
                    .REJECT_ALL
                ),
                reasons=[
                    (
                        "no proposal reached the "
                        "minimum acceptable proposal score"
                    )
                ],
            )

        if (
            ConsensusFailureReason
            .QUORUM_NOT_REACHED
            in failure_reasons
            or ConsensusFailureReason
            .APPROVAL_RATIO_NOT_REACHED
            in failure_reasons
            or ConsensusFailureReason
            .MINIMUM_SCORE_NOT_REACHED
            in failure_reasons
        ):
            return ConflictResolutionResult(
                strategy=(
                    ConflictResolutionStrategy
                    .REQUEST_REVISION
                ),
                decision_type=(
                    NegotiationDecisionType
                    .REQUEST_REVISION
                ),
                conflicting_proposal_ids=[
                    result.proposal_id
                    for result
                    in proposal_results
                ],
                reasons=[
                    (
                        "current proposals require "
                        "additional votes or revision"
                    )
                ],
            )

        return ConflictResolutionResult(
            strategy=(
                ConflictResolutionStrategy
                .ESCALATE
            ),
            decision_type=(
                NegotiationDecisionType
                .NO_DECISION
            ),
            reasons=[
                (
                    "automatic conflict resolution "
                    "could not determine an outcome"
                )
            ],
            escalated=True,
        )

    def _is_tied(
        self,
        first: tuple[
            float,
            float,
            float,
        ],
        second: tuple[
            float,
            float,
            float,
        ],
    ) -> bool:
        return all(
            abs(left - right)
            <= self._policy
            .score_tie_tolerance
            for left, right
            in zip(first, second)
        )

    def _ranking_tied(
        self,
        scores,
    ) -> bool:
        if len(scores) < 2:
            return False

        return (
            abs(
                scores[0].weighted_score
                - scores[1].weighted_score
            )
            <= self._policy
            .score_tie_tolerance
        )
