from __future__ import annotations

from af_core.communication import (
    AgentCommunicationBus,
    AgentMessage,
)
from af_core.organization import (
    AgentNegotiationEngine,
    NegotiationCoordinator,
    NegotiationEventPublisher,
    NegotiationParticipant,
    NegotiationParticipantRole,
    NegotiationProposal,
    NegotiationSession,
    NegotiationVote,
)


def make_system(
    bus: AgentCommunicationBus,
) -> tuple[
    AgentNegotiationEngine,
    NegotiationCoordinator,
]:
    engine = AgentNegotiationEngine()

    coordinator = NegotiationCoordinator(
        engine=engine,
        publisher=(
            NegotiationEventPublisher(bus)
        ),
    )

    return engine, coordinator


def create_open_session(
    coordinator: NegotiationCoordinator,
) -> NegotiationSession:
    session = coordinator.create_session(
        NegotiationSession(
            workspace_id=(
                "blockchain-workspace"
            ),
            team_id="team-001",
            subject="Move Architecture",
            objective=(
                "Select a secure implementation"
            ),
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
        session = coordinator.add_participant(
            session_id=session.session_id,
            participant=participant,
        )

    return coordinator.open_session(
        session.session_id
    )


def make_proposal(
    session_id: str,
) -> NegotiationProposal:
    return NegotiationProposal(
        session_id=session_id,
        proposer_agent_id=(
            "architect-agent"
        ),
        title="Secure Modular Plan",
        summary=(
            "Implement governed Move modules"
        ),
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


def test_session_and_proposal_events_are_published():

    received: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="negotiation.**",
        agent_id="negotiation-monitor",
        handler=received.append,
    )

    _, coordinator = make_system(bus)

    session = create_open_session(
        coordinator
    )

    coordinator.submit_proposal(
        make_proposal(
            session.session_id
        )
    )

    topics = [
        message.topic
        for message in received
    ]

    assert topics == [
        "negotiation.session.created",
        "negotiation.participant.added",
        "negotiation.participant.added",
        "negotiation.participant.added",
        "negotiation.session.opened",
        "negotiation.proposal.submitted",
    ]

    assert bus.verify_audit_integrity()


def test_vote_and_consensus_events_are_published():

    received: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="negotiation.**",
        agent_id="governance-monitor",
        handler=received.append,
    )

    _, coordinator = make_system(bus)

    session = create_open_session(
        coordinator
    )

    proposal = make_proposal(
        session.session_id
    )

    coordinator.submit_proposal(
        proposal
    )

    for voter_id, score in (
        ("security-agent", 94),
        ("manager-agent", 96),
    ):
        coordinator.cast_vote(
            NegotiationVote(
                session_id=(
                    session.session_id
                ),
                proposal_id=(
                    proposal.proposal_id
                ),
                voter_agent_id=voter_id,
                approve=True,
                score=score,
            )
        )

    result = coordinator.evaluate_consensus(
        session.session_id
    )

    assert result.consensus_reached

    assert [
        message.topic
        for message in received[-3:]
    ] == [
        "negotiation.vote.cast",
        "negotiation.vote.cast",
        "negotiation.consensus.reached",
    ]

    assert bus.verify_audit_integrity()


def test_negotiation_events_are_workspace_isolated():

    blockchain_events: list[
        AgentMessage
    ] = []

    gsos_events: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="negotiation.**",
        agent_id="blockchain-monitor",
        workspace_id=(
            "blockchain-workspace"
        ),
        handler=(
            blockchain_events.append
        ),
    )

    bus.subscribe(
        topic="negotiation.**",
        agent_id="gsos-monitor",
        workspace_id="gsos-workspace",
        handler=gsos_events.append,
    )

    _, coordinator = make_system(bus)

    create_open_session(coordinator)

    assert blockchain_events
    assert gsos_events == []

    assert bus.verify_audit_integrity()


def test_consensus_finalization_can_be_closed():

    received: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="negotiation.**",
        agent_id="audit-agent",
        handler=received.append,
    )

    _, coordinator = make_system(bus)

    session = create_open_session(
        coordinator
    )

    proposal = make_proposal(
        session.session_id
    )

    coordinator.submit_proposal(
        proposal
    )

    for voter_id in (
        "security-agent",
        "manager-agent",
    ):
        coordinator.cast_vote(
            NegotiationVote(
                session_id=(
                    session.session_id
                ),
                proposal_id=(
                    proposal.proposal_id
                ),
                voter_agent_id=voter_id,
                approve=True,
                score=95,
            )
        )

    coordinator.finalize_consensus(
        session_id=session.session_id,
        decided_by="consensus-engine",
    )

    closed = coordinator.close_session(
        session.session_id
    )

    assert closed.closed_at is not None

    assert (
        received[-1].topic
        == "negotiation.session.closed"
    )

    assert bus.verify_audit_integrity()
