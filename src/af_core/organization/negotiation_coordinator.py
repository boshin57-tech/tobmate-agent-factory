from __future__ import annotations

from .consensus_models import (
    SessionConsensusResult,
)
from .negotiation_engine import (
    AgentNegotiationEngine,
)
from .negotiation_event_models import (
    NegotiationEventType,
)
from .negotiation_event_publisher import (
    NegotiationEventPublisher,
)
from .negotiation_models import (
    NegotiationDecisionType,
    NegotiationParticipant,
    NegotiationProposal,
    NegotiationSession,
    NegotiationVote,
)


class NegotiationCoordinator:
    """
    Coordinates negotiation state changes and Communication Bus events.
    """

    def __init__(
        self,
        *,
        engine: AgentNegotiationEngine,
        publisher: NegotiationEventPublisher,
    ) -> None:
        self._engine = engine
        self._publisher = publisher

    def create_session(
        self,
        session: NegotiationSession,
        *,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> NegotiationSession:
        created = self._engine.create_session(
            session
        )

        self._publisher.publish_session(
            event_type=(
                NegotiationEventType
                .SESSION_CREATED
            ),
            session=created,
            protected=protected_event,
            environment=environment,
        )

        return created

    def add_participant(
        self,
        *,
        session_id: str,
        participant: NegotiationParticipant,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> NegotiationSession:
        updated = self._engine.add_participant(
            session_id=session_id,
            participant=participant,
        )

        self._publisher.publish_session(
            event_type=(
                NegotiationEventType
                .PARTICIPANT_ADDED
            ),
            session=updated,
            reasons=[
                (
                    "participant added: "
                    f"{participant.agent_id}"
                )
            ],
            protected=protected_event,
            environment=environment,
        )

        return updated

    def open_session(
        self,
        session_id: str,
        *,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> NegotiationSession:
        opened = self._engine.open_session(
            session_id
        )

        self._publisher.publish_session(
            event_type=(
                NegotiationEventType
                .SESSION_OPENED
            ),
            session=opened,
            protected=protected_event,
            environment=environment,
        )

        return opened

    def submit_proposal(
        self,
        proposal: NegotiationProposal,
        *,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> NegotiationSession:
        updated = self._engine.submit_proposal(
            proposal
        )

        stored = self._require_proposal(
            session=updated,
            proposal_id=proposal.proposal_id,
        )

        self._publisher.publish_proposal(
            event_type=(
                NegotiationEventType
                .PROPOSAL_SUBMITTED
            ),
            session=updated,
            proposal=stored,
            protected=protected_event,
            environment=environment,
        )

        return updated

    def generate_counter_proposal(
        self,
        *,
        session_id: str,
        parent_proposal_id: str,
        proposer_agent_id: str,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> NegotiationSession:
        before = self._require_session(
            session_id
        )

        existing_ids = {
            proposal.proposal_id
            for proposal in before.proposals
        }

        updated = (
            self._engine
            .generate_counter_proposal(
                session_id=session_id,
                parent_proposal_id=(
                    parent_proposal_id
                ),
                proposer_agent_id=(
                    proposer_agent_id
                ),
            )
        )

        counter = next(
            proposal
            for proposal in updated.proposals
            if (
                proposal.proposal_id
                not in existing_ids
            )
        )

        self._publisher.publish_proposal(
            event_type=(
                NegotiationEventType
                .PROPOSAL_COUNTERED
            ),
            session=updated,
            proposal=counter,
            protected=protected_event,
            environment=environment,
        )

        return updated

    def cast_vote(
        self,
        vote: NegotiationVote,
        *,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> NegotiationSession:
        updated = self._engine.cast_vote(
            vote
        )

        self._publisher.publish_vote(
            session=updated,
            vote=vote,
            protected=protected_event,
            environment=environment,
        )

        return updated

    def evaluate_consensus(
        self,
        session_id: str,
        *,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> SessionConsensusResult:
        session = self._require_session(
            session_id
        )

        result = (
            self._engine
            .evaluate_consensus(
                session_id
            )
        )

        event_type = self._consensus_event(
            result
        )

        self._publisher.publish_consensus(
            event_type=event_type,
            session=session,
            result=result,
            protected=protected_event,
            environment=environment,
        )

        return result

    def finalize_consensus(
        self,
        *,
        session_id: str,
        decided_by: str,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> NegotiationSession:
        result = (
            self._engine
            .evaluate_consensus(
                session_id
            )
        )

        finalized = (
            self._engine
            .finalize_consensus(
                session_id=session_id,
                decided_by=decided_by,
            )
        )

        event_type = self._consensus_event(
            result
        )

        self._publisher.publish_consensus(
            event_type=event_type,
            session=finalized,
            result=result,
            protected=protected_event,
            environment=environment,
        )

        return finalized

    def close_session(
        self,
        session_id: str,
        *,
        protected_event: bool = False,
        environment: str = "runtime",
    ) -> NegotiationSession:
        closed = self._engine.close_session(
            session_id
        )

        self._publisher.publish_session(
            event_type=(
                NegotiationEventType
                .SESSION_CLOSED
            ),
            session=closed,
            protected=protected_event,
            environment=environment,
        )

        return closed

    def _require_session(
        self,
        session_id: str,
    ) -> NegotiationSession:
        session = self._engine.get_session(
            session_id
        )

        if session is None:
            raise ValueError(
                "negotiation session not found"
            )

        return session

    @staticmethod
    def _require_proposal(
        *,
        session: NegotiationSession,
        proposal_id: str,
    ) -> NegotiationProposal:
        for proposal in session.proposals:
            if (
                proposal.proposal_id
                == proposal_id
            ):
                return proposal

        raise ValueError(
            "proposal not found"
        )

    @staticmethod
    def _consensus_event(
        result: SessionConsensusResult,
    ) -> NegotiationEventType:
        if (
            result.decision_type
            is NegotiationDecisionType
            .ACCEPT_PROPOSAL
        ):
            return (
                NegotiationEventType
                .CONSENSUS_REACHED
            )

        if (
            result.decision_type
            is NegotiationDecisionType
            .REQUEST_REVISION
        ):
            return (
                NegotiationEventType
                .REVISION_REQUESTED
            )

        if (
            result.decision_type
            is NegotiationDecisionType
            .ESCALATE
        ):
            return (
                NegotiationEventType
                .ESCALATED
            )

        if (
            result.decision_type
            is NegotiationDecisionType
            .REJECT_ALL
        ):
            return (
                NegotiationEventType
                .REJECTED
            )

        return (
            NegotiationEventType
            .CONSENSUS_EVALUATED
        )
