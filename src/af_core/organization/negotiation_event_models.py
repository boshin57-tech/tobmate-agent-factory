from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .consensus_models import (
    SessionConsensusResult,
)
from .negotiation_models import (
    NegotiationProposal,
    NegotiationSession,
    NegotiationVote,
)


class NegotiationEventType(str, Enum):
    SESSION_CREATED = (
        "negotiation.session.created"
    )
    SESSION_OPENED = (
        "negotiation.session.opened"
    )
    PARTICIPANT_ADDED = (
        "negotiation.participant.added"
    )

    PROPOSAL_SUBMITTED = (
        "negotiation.proposal.submitted"
    )
    PROPOSAL_COUNTERED = (
        "negotiation.proposal.countered"
    )
    PROPOSAL_WITHDRAWN = (
        "negotiation.proposal.withdrawn"
    )

    VOTE_CAST = (
        "negotiation.vote.cast"
    )

    CONSENSUS_EVALUATED = (
        "negotiation.consensus.evaluated"
    )
    CONSENSUS_REACHED = (
        "negotiation.consensus.reached"
    )
    REVISION_REQUESTED = (
        "negotiation.revision.requested"
    )
    ESCALATED = (
        "negotiation.escalated"
    )
    REJECTED = (
        "negotiation.rejected"
    )

    SESSION_CANCELLED = (
        "negotiation.session.cancelled"
    )
    SESSION_CLOSED = (
        "negotiation.session.closed"
    )


class NegotiationSessionEventPayload(BaseModel):
    event_type: NegotiationEventType

    session_id: str
    workspace_id: str
    team_id: str | None = None

    subject: str
    objective: str
    status: str

    participant_count: int = 0
    proposal_count: int = 0
    vote_count: int = 0

    selected_proposal_id: str | None = None
    decision_type: str | None = None

    reasons: list[str] = Field(
        default_factory=list
    )

    metadata: dict[str, object] = Field(
        default_factory=dict
    )

    @classmethod
    def from_session(
        cls,
        *,
        event_type: NegotiationEventType,
        session: NegotiationSession,
        reasons: list[str] | None = None,
    ) -> "NegotiationSessionEventPayload":
        return cls(
            event_type=event_type,
            session_id=session.session_id,
            workspace_id=(
                session.workspace_id
            ),
            team_id=session.team_id,
            subject=session.subject,
            objective=session.objective,
            status=session.status.value,
            participant_count=len(
                session.participants
            ),
            proposal_count=len(
                session.proposals
            ),
            vote_count=len(
                session.votes
            ),
            selected_proposal_id=(
                session.decision
                .selected_proposal_id
                if session.decision is not None
                else None
            ),
            decision_type=(
                session.decision
                .decision_type.value
                if session.decision is not None
                else None
            ),
            reasons=(
                reasons
                or (
                    list(
                        session.decision.reasons
                    )
                    if session.decision
                    is not None
                    else []
                )
            ),
            metadata=dict(
                session.metadata
            ),
        )


class NegotiationProposalEventPayload(BaseModel):
    event_type: NegotiationEventType

    session_id: str
    proposal_id: str

    proposer_agent_id: str

    title: str
    summary: str
    status: str

    parent_proposal_id: str | None = None

    estimated_cost: float = 0.0
    estimated_duration_minutes: int = 0
    expected_quality: float = 0.0
    risk_score: float = 0.0
    confidence_score: float = 0.0

    metadata: dict[str, object] = Field(
        default_factory=dict
    )

    @classmethod
    def from_proposal(
        cls,
        *,
        event_type: NegotiationEventType,
        proposal: NegotiationProposal,
    ) -> "NegotiationProposalEventPayload":
        return cls(
            event_type=event_type,
            session_id=proposal.session_id,
            proposal_id=proposal.proposal_id,
            proposer_agent_id=(
                proposal.proposer_agent_id
            ),
            title=proposal.title,
            summary=proposal.summary,
            status=proposal.status.value,
            parent_proposal_id=(
                proposal.parent_proposal_id
            ),
            estimated_cost=(
                proposal.estimated_cost
            ),
            estimated_duration_minutes=(
                proposal
                .estimated_duration_minutes
            ),
            expected_quality=(
                proposal.expected_quality
            ),
            risk_score=proposal.risk_score,
            confidence_score=(
                proposal.confidence_score
            ),
            metadata=dict(
                proposal.metadata
            ),
        )


class NegotiationVoteEventPayload(BaseModel):
    event_type: NegotiationEventType

    session_id: str
    proposal_id: str
    vote_id: str

    voter_agent_id: str

    approve: bool
    score: float
    veto: bool

    rationale: str

    @classmethod
    def from_vote(
        cls,
        vote: NegotiationVote,
    ) -> "NegotiationVoteEventPayload":
        return cls(
            event_type=(
                NegotiationEventType
                .VOTE_CAST
            ),
            session_id=vote.session_id,
            proposal_id=vote.proposal_id,
            vote_id=vote.vote_id,
            voter_agent_id=(
                vote.voter_agent_id
            ),
            approve=vote.approve,
            score=vote.score,
            veto=vote.veto,
            rationale=vote.rationale,
        )


class NegotiationConsensusEventPayload(BaseModel):
    event_type: NegotiationEventType

    session_id: str

    decision_type: str

    consensus_reached: bool

    selected_proposal_id: str | None = None

    consensus_proposal_ids: list[str] = Field(
        default_factory=list
    )

    reasons: list[str] = Field(
        default_factory=list
    )

    resolution_strategy: str | None = None
    escalated: bool = False

    @classmethod
    def from_result(
        cls,
        *,
        event_type: NegotiationEventType,
        result: SessionConsensusResult,
    ) -> "NegotiationConsensusEventPayload":
        resolution = result.resolution

        return cls(
            event_type=event_type,
            session_id=result.session_id,
            decision_type=(
                result.decision_type.value
            ),
            consensus_reached=(
                result.consensus_reached
            ),
            selected_proposal_id=(
                result.selected_proposal_id
            ),
            consensus_proposal_ids=list(
                result.consensus_proposal_ids
            ),
            reasons=list(result.reasons),
            resolution_strategy=(
                resolution.strategy.value
                if resolution is not None
                else None
            ),
            escalated=(
                resolution.escalated
                if resolution is not None
                else False
            ),
        )
