from __future__ import annotations

import pytest

from af_core.organization import (
    AgentNegotiationEngine,
    NegotiationParticipant,
    NegotiationParticipantRole,
    NegotiationProposal,
    NegotiationSession,
    NegotiationStatus,
    NegotiationVote,
    ProposalStatus,
)


def make_session() -> NegotiationSession:
    return NegotiationSession(
        workspace_id=(
            "blockchain-workspace"
        ),
        team_id="team-001",
        subject=(
            "Move module implementation strategy"
        ),
        objective=(
            "Select the safest and most "
            "maintainable implementation plan"
        ),
        created_by="manager-agent",
    )


def participants() -> tuple[
    NegotiationParticipant,
    ...
]:
    return (
        NegotiationParticipant(
            agent_id="architect-agent",
            role=(
                NegotiationParticipantRole
                .PROPOSER
            ),
            capabilities={
                "architecture",
            },
        ),
        NegotiationParticipant(
            agent_id="security-agent",
            role=(
                NegotiationParticipantRole
                .REVIEWER
            ),
            capabilities={
                "security_audit",
            },
        ),
        NegotiationParticipant(
            agent_id="manager-agent",
            role=(
                NegotiationParticipantRole
                .DECISION_MAKER
            ),
            voting_weight=2.0,
            can_veto=True,
        ),
    )


def open_session(
    engine: AgentNegotiationEngine,
) -> NegotiationSession:
    session = engine.create_session(
        make_session()
    )

    for participant in participants():
        session = engine.add_participant(
            session_id=session.session_id,
            participant=participant,
        )

    return engine.open_session(
        session.session_id
    )


def proposal(
    *,
    session_id: str,
    proposer_agent_id: str = (
        "architect-agent"
    ),
    title: str = "Modular implementation",
) -> NegotiationProposal:
    return NegotiationProposal(
        session_id=session_id,
        proposer_agent_id=(
            proposer_agent_id
        ),
        title=title,
        summary=(
            "Implement the protocol using "
            "separate governed modules"
        ),
        implementation_plan=[
            "Define interfaces",
            "Implement modules",
            "Run security tests",
        ],
        estimated_cost=10.0,
        estimated_duration_minutes=120,
        expected_quality=95,
        risk_score=20,
        confidence_score=90,
        required_capabilities={
            "sui_move",
        },
    )


def test_session_requires_two_participants():

    engine = AgentNegotiationEngine()

    session = engine.create_session(
        make_session()
    )

    session = engine.add_participant(
        session_id=session.session_id,
        participant=participants()[0],
    )

    with pytest.raises(
        ValueError,
        match=(
            "requires at least two "
            "participants"
        ),
    ):
        engine.open_session(
            session.session_id
        )


def test_session_can_be_opened():

    engine = AgentNegotiationEngine()

    session = open_session(engine)

    assert (
        session.status
        is NegotiationStatus.OPEN
    )

    assert session.opened_at is not None
    assert len(session.participants) == 3


def test_registered_participant_can_submit_proposal():

    engine = AgentNegotiationEngine()

    session = open_session(engine)

    updated = engine.submit_proposal(
        proposal(
            session_id=session.session_id
        )
    )

    assert len(updated.proposals) == 1

    assert (
        updated.proposals[0].status
        is ProposalStatus.SUBMITTED
    )


def test_unregistered_agent_cannot_submit_proposal():

    engine = AgentNegotiationEngine()

    session = open_session(engine)

    with pytest.raises(
        ValueError,
        match="not a negotiation participant",
    ):
        engine.submit_proposal(
            proposal(
                session_id=session.session_id,
                proposer_agent_id=(
                    "unknown-agent"
                ),
            )
        )


def test_counter_proposal_links_parent():

    engine = AgentNegotiationEngine()

    session = open_session(engine)

    original = proposal(
        session_id=session.session_id
    )

    session = engine.submit_proposal(
        original
    )

    counter = proposal(
        session_id=session.session_id,
        proposer_agent_id=(
            "security-agent"
        ),
        title="Security-first implementation",
    )

    session = (
        engine.submit_counter_proposal(
            parent_proposal_id=(
                original.proposal_id
            ),
            proposal=counter,
        )
    )

    stored_original = next(
        item
        for item in session.proposals
        if (
            item.proposal_id
            == original.proposal_id
        )
    )

    stored_counter = next(
        item
        for item in session.proposals
        if item.proposal_id
        == counter.proposal_id
    )

    assert (
        stored_original.status
        is ProposalStatus.COUNTERED
    )

    assert (
        stored_counter.parent_proposal_id
        == original.proposal_id
    )


def test_participant_can_vote():

    engine = AgentNegotiationEngine()

    session = open_session(engine)

    item = proposal(
        session_id=session.session_id
    )

    session = engine.submit_proposal(
        item
    )

    session = engine.cast_vote(
        NegotiationVote(
            session_id=session.session_id,
            proposal_id=item.proposal_id,
            voter_agent_id=(
                "security-agent"
            ),
            approve=True,
            score=92,
            rationale=(
                "Security requirements satisfied"
            ),
        )
    )

    assert (
        session.status
        is NegotiationStatus.EVALUATING
    )

    assert len(session.votes) == 1


def test_duplicate_vote_is_rejected():

    engine = AgentNegotiationEngine()

    session = open_session(engine)

    item = proposal(
        session_id=session.session_id
    )

    engine.submit_proposal(item)

    vote = NegotiationVote(
        session_id=session.session_id,
        proposal_id=item.proposal_id,
        voter_agent_id="security-agent",
        approve=True,
        score=90,
    )

    engine.cast_vote(vote)

    with pytest.raises(
        ValueError,
        match="already voted",
    ):
        engine.cast_vote(
            vote.model_copy(
                update={
                    "vote_id":
                        "second-vote",
                }
            )
        )


def test_non_veto_participant_cannot_veto():

    engine = AgentNegotiationEngine()

    session = open_session(engine)

    item = proposal(
        session_id=session.session_id
    )

    engine.submit_proposal(item)

    with pytest.raises(
        ValueError,
        match="no veto authority",
    ):
        engine.cast_vote(
            NegotiationVote(
                session_id=(
                    session.session_id
                ),
                proposal_id=(
                    item.proposal_id
                ),
                voter_agent_id=(
                    "security-agent"
                ),
                approve=False,
                score=10,
                veto=True,
            )
        )


def test_proposer_can_withdraw_proposal():

    engine = AgentNegotiationEngine()

    session = open_session(engine)

    item = proposal(
        session_id=session.session_id
    )

    engine.submit_proposal(item)

    updated = engine.withdraw_proposal(
        session_id=session.session_id,
        proposal_id=item.proposal_id,
        requested_by=(
            item.proposer_agent_id
        ),
    )

    assert (
        updated.proposals[0].status
        is ProposalStatus.WITHDRAWN
    )


def test_creator_can_cancel_session():

    engine = AgentNegotiationEngine()

    session = open_session(engine)

    cancelled = engine.cancel_session(
        session_id=session.session_id,
        requested_by="manager-agent",
    )

    assert (
        cancelled.status
        is NegotiationStatus.CANCELLED
    )

    assert cancelled.closed_at is not None
