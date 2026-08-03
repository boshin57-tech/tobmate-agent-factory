from __future__ import annotations

from typing import Any

from af_core.communication import (
    AgentCommunicationBus,
    AgentMessage,
    MessageType,
)

from .consensus_models import (
    SessionConsensusResult,
)
from .negotiation_event_models import (
    NegotiationConsensusEventPayload,
    NegotiationEventType,
    NegotiationProposalEventPayload,
    NegotiationSessionEventPayload,
    NegotiationVoteEventPayload,
)
from .negotiation_models import (
    NegotiationProposal,
    NegotiationSession,
    NegotiationVote,
)


class NegotiationEventPublisher:
    """
    Publishes negotiation lifecycle events through the
    Agent Communication Bus.

    Protected events declare authority requirements in message
    metadata. The Communication Bus performs fail-closed authority
    enforcement and records every outcome in its hash-chain audit.
    """

    def __init__(
        self,
        bus: AgentCommunicationBus,
        *,
        sender_agent_id: str = (
            "agent-negotiation-engine"
        ),
    ) -> None:
        self._bus = bus
        self._sender_agent_id = (
            sender_agent_id
        )

    def publish_session(
        self,
        *,
        event_type: NegotiationEventType,
        session: NegotiationSession,
        reasons: list[str] | None = None,
        protected: bool = False,
        environment: str = "runtime",
        permission: str = (
            "negotiation_session_manage"
        ),
    ):
        payload = (
            NegotiationSessionEventPayload
            .from_session(
                event_type=event_type,
                session=session,
                reasons=reasons,
            )
        )

        return self._publish(
            topic=event_type.value,
            workspace_id=session.workspace_id,
            correlation_id=(
                session.session_id
            ),
            payload=payload.model_dump(
                mode="json"
            ),
            metadata={
                "session_id":
                    session.session_id,
                "team_id":
                    session.team_id or "",
                "session_status":
                    session.status.value,
            },
            protected=protected,
            permission=permission,
            environment=environment,
            resource_scope=(
                session.team_id
                or session.session_id
            ),
        )

    def publish_proposal(
        self,
        *,
        event_type: NegotiationEventType,
        session: NegotiationSession,
        proposal: NegotiationProposal,
        protected: bool = False,
        environment: str = "runtime",
    ):
        payload = (
            NegotiationProposalEventPayload
            .from_proposal(
                event_type=event_type,
                proposal=proposal,
            )
        )

        return self._publish(
            topic=event_type.value,
            workspace_id=session.workspace_id,
            correlation_id=(
                session.session_id
            ),
            payload=payload.model_dump(
                mode="json"
            ),
            metadata={
                "session_id":
                    session.session_id,
                "proposal_id":
                    proposal.proposal_id,
                "proposal_status":
                    proposal.status.value,
            },
            protected=protected,
            permission=(
                "negotiation_proposal_manage"
            ),
            environment=environment,
            resource_scope=(
                session.team_id
                or session.session_id
            ),
        )

    def publish_vote(
        self,
        *,
        session: NegotiationSession,
        vote: NegotiationVote,
        protected: bool = False,
        environment: str = "runtime",
    ):
        payload = (
            NegotiationVoteEventPayload
            .from_vote(vote)
        )

        return self._publish(
            topic=(
                NegotiationEventType
                .VOTE_CAST.value
            ),
            workspace_id=session.workspace_id,
            correlation_id=(
                session.session_id
            ),
            payload=payload.model_dump(
                mode="json"
            ),
            metadata={
                "session_id":
                    session.session_id,
                "proposal_id":
                    vote.proposal_id,
                "vote_id":
                    vote.vote_id,
                "voter_agent_id":
                    vote.voter_agent_id,
                "veto":
                    str(vote.veto).lower(),
            },
            protected=protected,
            permission=(
                "negotiation_vote_cast"
            ),
            environment=environment,
            resource_scope=(
                session.team_id
                or session.session_id
            ),
        )

    def publish_consensus(
        self,
        *,
        event_type: NegotiationEventType,
        session: NegotiationSession,
        result: SessionConsensusResult,
        protected: bool = False,
        environment: str = "runtime",
    ):
        payload = (
            NegotiationConsensusEventPayload
            .from_result(
                event_type=event_type,
                result=result,
            )
        )

        return self._publish(
            topic=event_type.value,
            workspace_id=session.workspace_id,
            correlation_id=(
                session.session_id
            ),
            payload=payload.model_dump(
                mode="json"
            ),
            metadata={
                "session_id":
                    session.session_id,
                "decision_type":
                    result.decision_type.value,
                "consensus_reached":
                    str(
                        result.consensus_reached
                    ).lower(),
                "selected_proposal_id":
                    result.selected_proposal_id
                    or "",
            },
            protected=protected,
            permission=(
                "negotiation_consensus_finalize"
            ),
            environment=environment,
            resource_scope=(
                session.team_id
                or session.session_id
            ),
        )

    def _publish(
        self,
        *,
        topic: str,
        workspace_id: str,
        correlation_id: str,
        payload: dict[str, Any],
        metadata: dict[str, str],
        protected: bool,
        permission: str,
        environment: str,
        resource_scope: str,
    ):
        message_metadata = dict(metadata)

        if protected:
            message_metadata.update(
                {
                    "required_permission":
                        permission,
                    "environment":
                        environment,
                    "resource_scope":
                        resource_scope,
                }
            )

        message = AgentMessage(
            topic=topic,
            message_type=(
                MessageType.EVENT_PUBLISHED
            ),
            sender_agent_id=(
                self._sender_agent_id
            ),
            workspace_id=workspace_id,
            correlation_id=correlation_id,
            payload=payload,
            metadata=message_metadata,
        )

        return self._bus.publish(message)
