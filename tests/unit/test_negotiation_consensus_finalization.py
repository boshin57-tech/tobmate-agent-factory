from __future__ import annotations

from af_core.organization import (
    AgentNegotiationEngine,
    NegotiationDecisionType,
    NegotiationParticipant,
    NegotiationParticipantRole,
    NegotiationProposal,
    NegotiationSession,
    NegotiationStatus,
    NegotiationVote,
    ProposalStatus,
)


def prepared_engine(
) -> tuple[
    AgentNegotiationEngine,
    NegotiationSession,
    NegotiationProposal,
]:
    engine = AgentNegotiationEngine()

    session = engine.create_session(
        NegotiationSession(
            workspace_id="workspace-001",
            team_id="team-001",
            subject="Architecture choice",
            objective="Reach consensus",
            created_by="manager-agent",
        )
    )

    for participant in (
        NegotiationParticipant(
            agent_id="architect-agent",
            role=(
                NegotiationParticipantRole
                .PROPOSER
            ),
        ),
        NegotiationParticipant(
            agent_id="security-agent",
            role=(
                NegotiationParticipantRole
                .REVIEWER
            ),
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
    ):
        session = engine.add_participant(
            session_id=session.session_id,
            participant=participant,
        )

    session = engine.open_session(
        session.session_id
    )

    item = NegotiationProposal(
        session_id=session.session_id,
        proposer_agent_id=(
            "architect-agent"
        ),
        title="Secure Modular Plan",
        summary="Modular implementation",
        estimated_cost=20,
        estimated_duration_minutes=120,
        expected_quality=95,
        risk_score=10,
        confidence_score=95,
        metadata={
            "security_score": "98",
            "reliability_score": "97",
            "maintainability_score": "96",
        },
    )

    session = engine.submit_proposal(
        item
    )

    for voter_id, weight_score in (
        ("security-agent", 94),
        ("manager-agent", 96),
    ):
        session = engine.cast_vote(
            NegotiationVote(
                session_id=(
                    session.session_id
                ),
                proposal_id=(
                    item.proposal_id
                ),
                voter_agent_id=voter_id,
                approve=True,
                score=weight_score,
            )
        )

    return engine, session, item


def test_engine_evaluates_consensus():

    engine, session, item = (
        prepared_engine()
    )

    result = engine.evaluate_consensus(
        session.session_id
    )

    assert result.consensus_reached

    assert (
        result.selected_proposal_id
        == item.proposal_id
    )


def test_finalize_accepts_selected_proposal():

    engine, session, item = (
        prepared_engine()
    )

    finalized = engine.finalize_consensus(
        session_id=session.session_id,
        decided_by=(
            "consensus-engine"
        ),
    )

    assert (
        finalized.status
        is NegotiationStatus
        .CONSENSUS_REACHED
    )

    assert finalized.decision is not None

    assert (
        finalized.decision
        .decision_type
        is NegotiationDecisionType
        .ACCEPT_PROPOSAL
    )

    assert (
        finalized.decision
        .selected_proposal_id
        == item.proposal_id
    )

    assert (
        finalized.proposals[0].status
        is ProposalStatus.ACCEPTED
    )


def test_finalize_records_weighted_approval_score():

    engine, session, _ = (
        prepared_engine()
    )

    finalized = engine.finalize_consensus(
        session_id=session.session_id,
        decided_by=(
            "consensus-engine"
        ),
    )

    assert finalized.decision is not None

    assert (
        finalized.decision.approval_score
        == 100.0
    )
