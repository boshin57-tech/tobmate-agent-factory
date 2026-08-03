from __future__ import annotations

from .consensus_models import (
    ConsensusFailureReason,
    ConsensusPolicy,
    ProposalConsensusResult,
)
from .negotiation_models import (
    NegotiationParticipantRole,
    NegotiationProposal,
    NegotiationSession,
    NegotiationVote,
)


class WeightedConsensusEngine:
    """
    Calculates proposal-level weighted consensus.

    Voting weight comes from NegotiationParticipant.voting_weight.
    Approval ratio is calculated against cast voting weight.
    Quorum is calculated against total eligible voting weight.
    """

    def __init__(
        self,
        policy: ConsensusPolicy | None = None,
    ) -> None:
        self._policy = (
            policy
            or ConsensusPolicy()
        )

    def evaluate_proposal(
        self,
        *,
        session: NegotiationSession,
        proposal: NegotiationProposal,
    ) -> ProposalConsensusResult:
        voters = [
            participant
            for participant
            in session.participants
            if participant.can_vote
        ]

        votes = [
            vote
            for vote in session.votes
            if vote.proposal_id
            == proposal.proposal_id
        ]

        participants_by_id = {
            participant.agent_id:
                participant
            for participant in voters
        }

        eligible_weight = sum(
            participant.voting_weight
            for participant in voters
        )

        cast_weight = 0.0
        approval_weight = 0.0
        rejection_weight = 0.0

        weighted_vote_score = 0.0

        approving_ids: list[str] = []
        rejecting_ids: list[str] = []
        veto_ids: list[str] = []

        voted_agent_ids: set[str] = set()

        for vote in votes:
            participant = (
                participants_by_id.get(
                    vote.voter_agent_id
                )
            )

            if participant is None:
                continue

            weight = (
                participant.voting_weight
            )

            voted_agent_ids.add(
                participant.agent_id
            )

            cast_weight += weight
            weighted_vote_score += (
                vote.score * weight
            )

            if vote.approve:
                approval_weight += weight
                approving_ids.append(
                    participant.agent_id
                )
            else:
                rejection_weight += weight
                rejecting_ids.append(
                    participant.agent_id
                )

            if vote.veto:
                veto_ids.append(
                    participant.agent_id
                )

        quorum_ratio = (
            cast_weight / eligible_weight
            if eligible_weight > 0
            else 0.0
        )

        approval_ratio = (
            approval_weight / cast_weight
            if cast_weight > 0
            else 0.0
        )

        average_vote_score = (
            weighted_vote_score
            / cast_weight
            if cast_weight > 0
            else 0.0
        )

        required_approval_ratio = (
            self._policy
            .required_approval_ratio
            if self._policy
            .required_approval_ratio
            is not None
            else session
            .required_consensus_ratio
        )

        quorum_reached = (
            quorum_ratio
            >= self._policy
            .minimum_quorum_ratio
        )

        approval_reached = (
            approval_ratio
            >= required_approval_ratio
        )

        score_reached = (
            average_vote_score
            >= self._policy
            .minimum_average_vote_score
        )

        vetoed = bool(veto_ids)

        decision_makers = {
            participant.agent_id
            for participant
            in session.participants
            if (
                participant.role
                is NegotiationParticipantRole
                .DECISION_MAKER
                and participant.can_vote
            )
        }

        missing_decision_makers = (
            decision_makers
            - voted_agent_ids
        )

        decision_maker_rule_passed = (
            not self._policy
            .require_decision_maker_vote
            or not missing_decision_makers
        )

        failure_reasons: list[
            ConsensusFailureReason
        ] = []

        if not voters:
            failure_reasons.append(
                ConsensusFailureReason
                .NO_VOTERS
            )

        if not quorum_reached:
            failure_reasons.append(
                ConsensusFailureReason
                .QUORUM_NOT_REACHED
            )

        if not approval_reached:
            failure_reasons.append(
                ConsensusFailureReason
                .APPROVAL_RATIO_NOT_REACHED
            )

        if not score_reached:
            failure_reasons.append(
                ConsensusFailureReason
                .MINIMUM_SCORE_NOT_REACHED
            )

        if (
            vetoed
            and self._policy
            .veto_blocks_consensus
        ):
            failure_reasons.append(
                ConsensusFailureReason
                .VETO_APPLIED
            )

        if not decision_maker_rule_passed:
            failure_reasons.append(
                ConsensusFailureReason
                .DECISION_MAKER_VOTE_MISSING
            )

        consensus_reached = (
            bool(voters)
            and quorum_reached
            and approval_reached
            and score_reached
            and decision_maker_rule_passed
            and not (
                vetoed
                and self._policy
                .veto_blocks_consensus
            )
        )

        missing_voters = [
            participant.agent_id
            for participant in voters
            if (
                participant.agent_id
                not in voted_agent_ids
            )
        ]

        return ProposalConsensusResult(
            proposal_id=proposal.proposal_id,
            eligible_voter_count=len(voters),
            cast_vote_count=len(votes),
            eligible_voting_weight=round(
                eligible_weight,
                4,
            ),
            cast_voting_weight=round(
                cast_weight,
                4,
            ),
            approval_weight=round(
                approval_weight,
                4,
            ),
            rejection_weight=round(
                rejection_weight,
                4,
            ),
            quorum_ratio=round(
                quorum_ratio,
                4,
            ),
            approval_ratio=round(
                approval_ratio,
                4,
            ),
            average_vote_score=round(
                average_vote_score,
                4,
            ),
            vetoed=vetoed,
            quorum_reached=quorum_reached,
            approval_reached=approval_reached,
            score_reached=score_reached,
            consensus_reached=(
                consensus_reached
            ),
            approving_agent_ids=(
                approving_ids
            ),
            rejecting_agent_ids=(
                rejecting_ids
            ),
            veto_agent_ids=veto_ids,
            missing_voter_agent_ids=(
                missing_voters
            ),
            failure_reasons=(
                failure_reasons
            ),
        )

    def evaluate_session(
        self,
        session: NegotiationSession,
    ) -> list[
        ProposalConsensusResult
    ]:
        return [
            self.evaluate_proposal(
                session=session,
                proposal=proposal,
            )
            for proposal in session.proposals
        ]

    @property
    def policy(
        self,
    ) -> ConsensusPolicy:
        return self._policy
