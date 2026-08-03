from __future__ import annotations

from af_core.organization import (
    AgentNegotiationEngine,
    CounterProposalIntelligence,
    NegotiationCriterion,
    NegotiationParticipant,
    NegotiationParticipantRole,
    NegotiationProposal,
    NegotiationSession,
    ProposalStatus,
)


def weak_proposal(
    *,
    session_id: str = "session-001",
) -> NegotiationProposal:
    return NegotiationProposal(
        session_id=session_id,
        proposer_agent_id="architect-agent",
        title="Weak Proposal",
        summary=(
            "Expensive and high-risk implementation"
        ),
        implementation_plan=[
            "Implement everything at once",
        ],
        estimated_cost=95,
        estimated_duration_minutes=1300,
        expected_quality=55,
        risk_score=85,
        confidence_score=50,
        metadata={
            "security_score": "45",
            "reliability_score": "50",
            "maintainability_score": "40",
        },
    )


def test_recommendation_targets_weak_criteria():

    intelligence = (
        CounterProposalIntelligence()
    )

    recommendation = (
        intelligence.recommend(
            weak_proposal()
        )
    )

    targets = set(
        recommendation.target_criteria
    )

    assert (
        NegotiationCriterion.COST
        in targets
    )

    assert (
        NegotiationCriterion.SPEED
        in targets
    )

    assert (
        NegotiationCriterion.RISK
        in targets
    )

    assert (
        NegotiationCriterion.SECURITY
        in targets
    )

    assert (
        recommendation
        .expected_score_improvement
        > 0
    )


def test_generated_counter_links_parent():

    intelligence = (
        CounterProposalIntelligence()
    )

    original = weak_proposal()

    counter = (
        intelligence
        .create_counter_proposal(
            original=original,
            proposer_agent_id=(
                "security-agent"
            ),
        )
    )

    assert (
        counter.parent_proposal_id
        == original.proposal_id
    )

    assert (
        counter.proposer_agent_id
        == "security-agent"
    )

    assert (
        counter.estimated_cost
        < original.estimated_cost
    )

    assert (
        counter.risk_score
        < original.risk_score
    )

    assert (
        counter.metadata[
            "counter_intelligence_generated"
        ]
        == "true"
    )


def open_engine_session(
) -> tuple[
    AgentNegotiationEngine,
    NegotiationSession,
]:
    engine = AgentNegotiationEngine()

    session = engine.create_session(
        NegotiationSession(
            workspace_id="workspace-001",
            team_id="team-001",
            subject="Architecture",
            objective="Select implementation",
            created_by="manager-agent",
        )
    )

    participants = (
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
    )

    for participant in participants:
        session = engine.add_participant(
            session_id=session.session_id,
            participant=participant,
        )

    session = engine.open_session(
        session.session_id
    )

    return engine, session


def test_engine_ranks_session_proposals():

    engine, session = (
        open_engine_session()
    )

    weak = weak_proposal(
        session_id=session.session_id
    )

    strong = NegotiationProposal(
        session_id=session.session_id,
        proposer_agent_id=(
            "security-agent"
        ),
        title="Strong Proposal",
        summary="Secure modular implementation",
        estimated_cost=20,
        estimated_duration_minutes=120,
        expected_quality=95,
        risk_score=10,
        confidence_score=95,
        metadata={
            "security_score": "98",
            "reliability_score": "96",
            "maintainability_score": "95",
        },
    )

    engine.submit_proposal(weak)
    engine.submit_proposal(strong)

    ranking = engine.rank_proposals(
        session.session_id
    )

    assert (
        ranking.best_proposal_id
        == strong.proposal_id
    )


def test_engine_generates_and_submits_counter():

    engine, session = (
        open_engine_session()
    )

    original = weak_proposal(
        session_id=session.session_id
    )

    engine.submit_proposal(original)

    updated = (
        engine.generate_counter_proposal(
            session_id=session.session_id,
            parent_proposal_id=(
                original.proposal_id
            ),
            proposer_agent_id=(
                "security-agent"
            ),
        )
    )

    assert len(updated.proposals) == 2

    stored_original = next(
        item
        for item in updated.proposals
        if (
            item.proposal_id
            == original.proposal_id
        )
    )

    counter = next(
        item
        for item in updated.proposals
        if (
            item.proposal_id
            != original.proposal_id
        )
    )

    assert (
        stored_original.status
        is ProposalStatus.COUNTERED
    )

    assert (
        counter.parent_proposal_id
        == original.proposal_id
    )

    assert (
        counter.metadata[
            "counter_intelligence_generated"
        ]
        == "true"
    )


def test_recommendation_can_be_queried():

    engine, session = (
        open_engine_session()
    )

    original = weak_proposal(
        session_id=session.session_id
    )

    engine.submit_proposal(original)

    recommendation = (
        engine.recommend_counter_proposal(
            session_id=session.session_id,
            proposal_id=(
                original.proposal_id
            ),
        )
    )

    assert (
        recommendation.parent_proposal_id
        == original.proposal_id
    )

    assert recommendation.suggested_changes
