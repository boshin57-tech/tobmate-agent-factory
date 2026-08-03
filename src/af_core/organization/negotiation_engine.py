from __future__ import annotations

from datetime import datetime, timezone

from .negotiation_models import (
    NegotiationDecision,
    NegotiationDecisionType,
    NegotiationParticipant,
    NegotiationProposal,
    NegotiationSession,
    NegotiationStatus,
    NegotiationVote,
    ProposalStatus,
)
from .negotiation_repository import (
    NegotiationRepository,
)
from .counter_proposal_intelligence import (
    CounterProposalIntelligence,
)
from .proposal_scoring_engine import (
    ProposalScoringEngine,
)
from .proposal_scoring_models import (
    CounterProposalRecommendation,
    ProposalRankingResult,
)
from .consensus_models import (
    SessionConsensusResult,
)
from .session_consensus_engine import (
    SessionConsensusEngine,
)


class AgentNegotiationEngine:
    """
    Manages multi-Agent negotiation sessions.

    This first stage supports:
    - Session creation and opening
    - Participant registration
    - Proposal submission
    - Counter proposals
    - Proposal withdrawal
    - Vote recording
    - Session cancellation and closure

    Scoring and consensus decisions are implemented in later stages.
    """

    def __init__(
        self,
        repository: NegotiationRepository | None = None,
        *,
        scoring_engine: ProposalScoringEngine | None = None,
        counter_intelligence: CounterProposalIntelligence | None = None,
        consensus_engine: SessionConsensusEngine | None = None,
    ) -> None:
        self._repository = (
            repository
            or NegotiationRepository()
        )

        self._scoring_engine = (
            scoring_engine
            or ProposalScoringEngine()
        )

        self._counter_intelligence = (
            counter_intelligence
            or CounterProposalIntelligence(
                self._scoring_engine
            )
        )

        self._consensus_engine = (
            consensus_engine
            or SessionConsensusEngine(
                scoring_engine=(
                    self._scoring_engine
                )
            )
        )

    def create_session(
        self,
        session: NegotiationSession,
    ) -> NegotiationSession:
        if session.status is not NegotiationStatus.CREATED:
            raise ValueError(
                "new session must have CREATED status"
            )

        return self._repository.save(
            session
        )

    def add_participant(
        self,
        *,
        session_id: str,
        participant: NegotiationParticipant,
    ) -> NegotiationSession:
        session = self._require_session(
            session_id
        )

        if session.status not in {
            NegotiationStatus.CREATED,
            NegotiationStatus.OPEN,
        }:
            raise ValueError(
                "participants cannot be added "
                "in the current session state"
            )

        if any(
            existing.agent_id
            == participant.agent_id
            for existing in session.participants
        ):
            raise ValueError(
                "participant already registered"
            )

        updated = session.model_copy(
            update={
                "participants": [
                    *session.participants,
                    participant,
                ]
            }
        )

        return self._repository.replace(
            updated
        )

    def open_session(
        self,
        session_id: str,
    ) -> NegotiationSession:
        session = self._require_session(
            session_id
        )

        if session.status is not NegotiationStatus.CREATED:
            raise ValueError(
                "only CREATED sessions can be opened"
            )

        if len(session.participants) < 2:
            raise ValueError(
                "negotiation requires at least "
                "two participants"
            )

        opened = session.model_copy(
            update={
                "status":
                    NegotiationStatus.OPEN,

                "opened_at":
                    datetime.now(
                        timezone.utc
                    ),
            }
        )

        return self._repository.replace(
            opened
        )

    def submit_proposal(
        self,
        proposal: NegotiationProposal,
    ) -> NegotiationSession:
        session = self._require_session(
            proposal.session_id
        )

        if session.status is not NegotiationStatus.OPEN:
            raise ValueError(
                "proposals require an OPEN session"
            )

        participant = self._participant(
            session=session,
            agent_id=(
                proposal.proposer_agent_id
            ),
        )

        if participant is None:
            raise ValueError(
                "proposal submitter is not "
                "a negotiation participant"
            )

        if not participant.can_submit_proposal:
            raise ValueError(
                "participant cannot submit proposals"
            )

        if (
            len(session.proposals)
            >= session.maximum_proposals
        ):
            raise ValueError(
                "maximum proposal count reached"
            )

        if any(
            existing.proposal_id
            == proposal.proposal_id
            for existing in session.proposals
        ):
            raise ValueError(
                "proposal already exists"
            )

        updated = session.model_copy(
            update={
                "proposals": [
                    *session.proposals,
                    proposal,
                ]
            }
        )

        return self._repository.replace(
            updated
        )

    def submit_counter_proposal(
        self,
        *,
        parent_proposal_id: str,
        proposal: NegotiationProposal,
    ) -> NegotiationSession:
        session = self._require_session(
            proposal.session_id
        )

        parent = self._proposal(
            session=session,
            proposal_id=(
                parent_proposal_id
            ),
        )

        if parent is None:
            raise ValueError(
                "parent proposal not found"
            )

        if parent.status not in {
            ProposalStatus.SUBMITTED,
            ProposalStatus.COUNTERED,
        }:
            raise ValueError(
                "parent proposal cannot be countered"
            )

        counter = proposal.model_copy(
            update={
                "parent_proposal_id":
                    parent_proposal_id,
            }
        )

        session = self.submit_proposal(
            counter
        )

        updated_proposals = [
            (
                existing.model_copy(
                    update={
                        "status":
                            ProposalStatus
                            .COUNTERED,
                    }
                )
                if (
                    existing.proposal_id
                    == parent_proposal_id
                )
                else existing
            )
            for existing in session.proposals
        ]

        return self._repository.replace(
            session.model_copy(
                update={
                    "proposals":
                        updated_proposals,
                }
            )
        )

    def withdraw_proposal(
        self,
        *,
        session_id: str,
        proposal_id: str,
        requested_by: str,
    ) -> NegotiationSession:
        session = self._require_session(
            session_id
        )

        proposal = self._proposal(
            session=session,
            proposal_id=proposal_id,
        )

        if proposal is None:
            raise ValueError(
                "proposal not found"
            )

        if (
            proposal.proposer_agent_id
            != requested_by
        ):
            raise ValueError(
                "only the proposer can withdraw "
                "the proposal"
            )

        if proposal.status not in {
            ProposalStatus.SUBMITTED,
            ProposalStatus.COUNTERED,
        }:
            raise ValueError(
                "proposal cannot be withdrawn "
                "from current status"
            )

        updated = [
            (
                existing.model_copy(
                    update={
                        "status":
                            ProposalStatus
                            .WITHDRAWN,
                    }
                )
                if existing.proposal_id
                == proposal_id
                else existing
            )
            for existing in session.proposals
        ]

        return self._repository.replace(
            session.model_copy(
                update={
                    "proposals": updated,
                }
            )
        )

    def cast_vote(
        self,
        vote: NegotiationVote,
    ) -> NegotiationSession:
        session = self._require_session(
            vote.session_id
        )

        if session.status not in {
            NegotiationStatus.OPEN,
            NegotiationStatus.EVALUATING,
        }:
            raise ValueError(
                "votes cannot be cast in "
                "the current session state"
            )

        participant = self._participant(
            session=session,
            agent_id=vote.voter_agent_id,
        )

        if participant is None:
            raise ValueError(
                "voter is not a participant"
            )

        if not participant.can_vote:
            raise ValueError(
                "participant cannot vote"
            )

        if (
            vote.veto
            and not participant.can_veto
        ):
            raise ValueError(
                "participant has no veto authority"
            )

        proposal = self._proposal(
            session=session,
            proposal_id=vote.proposal_id,
        )

        if proposal is None:
            raise ValueError(
                "vote proposal not found"
            )

        if any(
            existing.voter_agent_id
            == vote.voter_agent_id
            and existing.proposal_id
            == vote.proposal_id
            for existing in session.votes
        ):
            raise ValueError(
                "participant already voted "
                "on this proposal"
            )

        updated = session.model_copy(
            update={
                "votes": [
                    *session.votes,
                    vote,
                ],
                "status":
                    NegotiationStatus
                    .EVALUATING,
            }
        )

        return self._repository.replace(
            updated
        )

    def cancel_session(
        self,
        *,
        session_id: str,
        requested_by: str,
    ) -> NegotiationSession:
        session = self._require_session(
            session_id
        )

        if session.created_by != requested_by:
            raise ValueError(
                "only the session creator "
                "can cancel negotiation"
            )

        if session.status in {
            NegotiationStatus.CLOSED,
            NegotiationStatus.CANCELLED,
        }:
            raise ValueError(
                "session is already finalized"
            )

        cancelled = session.model_copy(
            update={
                "status":
                    NegotiationStatus.CANCELLED,

                "closed_at":
                    datetime.now(
                        timezone.utc
                    ),
            }
        )

        return self._repository.replace(
            cancelled
        )

    def close_session(
        self,
        session_id: str,
    ) -> NegotiationSession:
        session = self._require_session(
            session_id
        )

        if session.status not in {
            NegotiationStatus
            .CONSENSUS_REACHED,
            NegotiationStatus.REJECTED,
            NegotiationStatus.EXPIRED,
        }:
            raise ValueError(
                "session cannot be closed "
                "before a final outcome"
            )

        closed = session.model_copy(
            update={
                "status":
                    NegotiationStatus.CLOSED,

                "closed_at":
                    datetime.now(
                        timezone.utc
                    ),
            }
        )

        return self._repository.replace(
            closed
        )

    def evaluate_consensus(
        self,
        session_id: str,
    ) -> SessionConsensusResult:
        session = self._require_session(
            session_id
        )

        return self._consensus_engine.evaluate(
            session
        )

    def finalize_consensus(
        self,
        *,
        session_id: str,
        decided_by: str,
    ) -> NegotiationSession:
        session = self._require_session(
            session_id
        )

        result = (
            self._consensus_engine
            .evaluate(session)
        )

        decision = NegotiationDecision(
            session_id=session.session_id,
            decision_type=(
                result.decision_type
            ),
            selected_proposal_id=(
                result.selected_proposal_id
            ),
            decided_by=decided_by,
            reasons=list(result.reasons),
            approval_score=(
                self._selected_approval_score(
                    result
                )
            ),
        )

        if (
            result.decision_type
            is NegotiationDecisionType
            .ACCEPT_PROPOSAL
            and result.selected_proposal_id
            is not None
        ):
            status = (
                NegotiationStatus
                .CONSENSUS_REACHED
            )

            proposals = [
                proposal.model_copy(
                    update={
                        "status": (
                            ProposalStatus.ACCEPTED
                            if proposal.proposal_id
                            == result.selected_proposal_id
                            else ProposalStatus
                            .REJECTED
                        )
                    }
                )
                for proposal
                in session.proposals
            ]

        elif (
            result.decision_type
            is NegotiationDecisionType
            .REJECT_ALL
        ):
            status = (
                NegotiationStatus.REJECTED
            )

            proposals = [
                proposal.model_copy(
                    update={
                        "status":
                            ProposalStatus.REJECTED,
                    }
                )
                for proposal
                in session.proposals
            ]

        else:
            status = (
                NegotiationStatus.EVALUATING
            )

            proposals = list(
                session.proposals
            )

        updated = session.model_copy(
            update={
                "status": status,
                "proposals": proposals,
                "decision": decision,
            }
        )

        return self._repository.replace(
            updated
        )

    @staticmethod
    def _selected_approval_score(
        result: SessionConsensusResult,
    ) -> float:
        if (
            result.selected_proposal_id
            is None
        ):
            return 0.0

        for proposal_result in (
            result.proposal_results
        ):
            if (
                proposal_result.proposal_id
                == result.selected_proposal_id
            ):
                return round(
                    proposal_result
                    .approval_ratio
                    * 100.0,
                    4,
                )

        return 0.0

    def rank_proposals(
        self,
        session_id: str,
    ) -> ProposalRankingResult:
        session = self._require_session(
            session_id
        )

        return self._scoring_engine.rank(
            session_id=session.session_id,
            proposals=list(
                session.proposals
            ),
        )

    def recommend_counter_proposal(
        self,
        *,
        session_id: str,
        proposal_id: str,
    ) -> CounterProposalRecommendation:
        session = self._require_session(
            session_id
        )

        proposal = self._proposal(
            session=session,
            proposal_id=proposal_id,
        )

        if proposal is None:
            raise ValueError(
                "proposal not found"
            )

        return (
            self._counter_intelligence
            .recommend(proposal)
        )

    def generate_counter_proposal(
        self,
        *,
        session_id: str,
        parent_proposal_id: str,
        proposer_agent_id: str,
    ) -> NegotiationSession:
        session = self._require_session(
            session_id
        )

        parent = self._proposal(
            session=session,
            proposal_id=(
                parent_proposal_id
            ),
        )

        if parent is None:
            raise ValueError(
                "parent proposal not found"
            )

        participant = self._participant(
            session=session,
            agent_id=proposer_agent_id,
        )

        if participant is None:
            raise ValueError(
                "counter proposer is not "
                "a negotiation participant"
            )

        if not participant.can_submit_proposal:
            raise ValueError(
                "participant cannot submit proposals"
            )

        recommendation = (
            self._counter_intelligence
            .recommend(parent)
        )

        counter = (
            self._counter_intelligence
            .create_counter_proposal(
                original=parent,
                proposer_agent_id=(
                    proposer_agent_id
                ),
                recommendation=(
                    recommendation
                ),
            )
        )

        return self.submit_counter_proposal(
            parent_proposal_id=(
                parent_proposal_id
            ),
            proposal=counter,
        )

    def get_session(
        self,
        session_id: str,
    ) -> NegotiationSession | None:
        return self._repository.get(
            session_id
        )

    def sessions_for_workspace(
        self,
        workspace_id: str,
    ) -> tuple[
        NegotiationSession,
        ...
    ]:
        return self._repository.by_workspace(
            workspace_id
        )

    def _require_session(
        self,
        session_id: str,
    ) -> NegotiationSession:
        session = self._repository.get(
            session_id
        )

        if session is None:
            raise ValueError(
                "negotiation session not found"
            )

        return session

    @staticmethod
    def _participant(
        *,
        session: NegotiationSession,
        agent_id: str,
    ) -> NegotiationParticipant | None:
        for participant in (
            session.participants
        ):
            if (
                participant.agent_id
                == agent_id
            ):
                return participant

        return None

    @staticmethod
    def _proposal(
        *,
        session: NegotiationSession,
        proposal_id: str,
    ) -> NegotiationProposal | None:
        for proposal in session.proposals:
            if (
                proposal.proposal_id
                == proposal_id
            ):
                return proposal

        return None

    @property
    def session_count(self) -> int:
        return self._repository.count
