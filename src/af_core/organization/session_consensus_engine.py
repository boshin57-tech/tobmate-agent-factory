from __future__ import annotations

from .consensus_models import (
    ConsensusFailureReason,
    ConsensusPolicy,
    SessionConsensusResult,
)
from .negotiation_conflict_resolution import (
    NegotiationConflictResolver,
)
from .negotiation_models import (
    NegotiationDecisionType,
    NegotiationSession,
)
from .proposal_scoring_engine import (
    ProposalScoringEngine,
)
from .weighted_consensus_engine import (
    WeightedConsensusEngine,
)


class SessionConsensusEngine:
    """
    Evaluates every proposal and produces one session-level decision.
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

        self._weighted_engine = (
            WeightedConsensusEngine(
                self._policy
            )
        )

        self._resolver = (
            NegotiationConflictResolver(
                policy=self._policy,
                scoring_engine=(
                    self._scoring_engine
                ),
            )
        )

    def evaluate(
        self,
        session: NegotiationSession,
    ) -> SessionConsensusResult:
        if not session.proposals:
            return SessionConsensusResult(
                session_id=session.session_id,
                decision_type=(
                    NegotiationDecisionType
                    .REJECT_ALL
                ),
                reasons=[
                    "negotiation contains no proposals"
                ],
            )

        proposal_results = (
            self._weighted_engine
            .evaluate_session(session)
        )

        resolution = (
            self._resolver.resolve(
                session=session,
                proposal_results=(
                    proposal_results
                ),
            )
        )

        consensus_ids = [
            result.proposal_id
            for result in proposal_results
            if result.consensus_reached
        ]

        consensus_reached = (
            resolution.decision_type
            is NegotiationDecisionType
            .ACCEPT_PROPOSAL
            and resolution
            .selected_proposal_id
            is not None
        )

        reasons = list(
            resolution.reasons
        )

        for result in proposal_results:
            if result.consensus_reached:
                continue

            if not result.failure_reasons:
                continue

            reasons.append(
                (
                    f"{result.proposal_id}: "
                    + ", ".join(
                        reason.value
                        for reason
                        in result.failure_reasons
                        if reason
                        is not ConsensusFailureReason
                        .NONE
                    )
                )
            )

        return SessionConsensusResult(
            session_id=session.session_id,
            proposal_results=(
                proposal_results
            ),
            consensus_proposal_ids=(
                consensus_ids
            ),
            selected_proposal_id=(
                resolution
                .selected_proposal_id
            ),
            decision_type=(
                resolution.decision_type
            ),
            resolution=resolution,
            consensus_reached=(
                consensus_reached
            ),
            reasons=reasons,
        )

    @property
    def policy(
        self,
    ) -> ConsensusPolicy:
        return self._policy
