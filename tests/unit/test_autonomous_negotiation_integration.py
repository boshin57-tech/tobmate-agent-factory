from __future__ import annotations

from af_core.communication import (
    AgentCommunicationBus,
    AgentMessage,
    CommunicationAuditEvent,
    CommunicationAuthorityGate,
    DeliveryStatus,
)
from af_core.organization import (
    AgentNegotiationEngine,
    NegotiationCoordinator,
    NegotiationDecisionType,
    NegotiationEventPublisher,
    NegotiationParticipant,
    NegotiationParticipantRole,
    NegotiationProposal,
    NegotiationSession,
    NegotiationStatus,
    NegotiationVote,
    ProposalStatus,
)


def participants() -> tuple[
    NegotiationParticipant,
    ...
]:
    return (
        NegotiationParticipant(
            agent_id="architecture-agent",
            role=(
                NegotiationParticipantRole
                .PROPOSER
            ),
            voting_weight=1.0,
            capabilities={
                "architecture",
                "adr",
            },
        ),
        NegotiationParticipant(
            agent_id="security-agent",
            role=(
                NegotiationParticipantRole
                .REVIEWER
            ),
            voting_weight=1.0,
            capabilities={
                "security_audit",
            },
        ),
        NegotiationParticipant(
            agent_id="implementation-agent",
            role=(
                NegotiationParticipantRole
                .PROPOSER
            ),
            voting_weight=1.0,
            capabilities={
                "sui_move",
                "smart_contract",
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


def create_coordinator(
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
            subject=(
                "Sui Move protocol "
                "implementation strategy"
            ),
            objective=(
                "Select the safest, fastest, "
                "and most maintainable plan"
            ),
            created_by="manager-agent",
            required_consensus_ratio=0.67,
            metadata={
                "project":
                    "tobmate-blockchain",
                "checkpoint":
                    "16-D",
            },
        )
    )

    for participant in participants():
        session = coordinator.add_participant(
            session_id=session.session_id,
            participant=participant,
        )

    return coordinator.open_session(
        session.session_id
    )


def weak_proposal(
    session_id: str,
) -> NegotiationProposal:
    return NegotiationProposal(
        session_id=session_id,
        proposer_agent_id=(
            "architecture-agent"
        ),
        title="Monolithic Fast Build",
        summary=(
            "Implement all functions in one "
            "large module"
        ),
        implementation_plan=[
            "Implement complete module",
            "Run basic unit tests",
        ],
        estimated_cost=85,
        estimated_duration_minutes=1100,
        expected_quality=60,
        risk_score=75,
        confidence_score=55,
        required_capabilities={
            "sui_move",
        },
        metadata={
            "security_score": "45",
            "reliability_score": "55",
            "maintainability_score": "40",
        },
    )


def strong_proposal(
    session_id: str,
) -> NegotiationProposal:
    return NegotiationProposal(
        session_id=session_id,
        proposer_agent_id=(
            "implementation-agent"
        ),
        title="Governed Modular Build",
        summary=(
            "Implement isolated governed modules "
            "with staged validation"
        ),
        implementation_plan=[
            "Define capability interfaces",
            "Implement isolated modules",
            "Add authority controls",
            "Run security tests",
            "Run full regression",
        ],
        estimated_cost=25,
        estimated_duration_minutes=180,
        expected_quality=96,
        risk_score=10,
        confidence_score=95,
        required_capabilities={
            "sui_move",
            "smart_contract",
        },
        metadata={
            "security_score": "98",
            "reliability_score": "97",
            "maintainability_score": "96",
        },
    )


def test_complete_autonomous_negotiation_flow():

    events: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="negotiation.**",
        agent_id=(
            "negotiation-intelligence-monitor"
        ),
        workspace_id=(
            "blockchain-workspace"
        ),
        handler=events.append,
    )

    engine, coordinator = (
        create_coordinator(bus)
    )

    session = create_open_session(
        coordinator
    )

    weak = weak_proposal(
        session.session_id
    )

    strong = strong_proposal(
        session.session_id
    )

    coordinator.submit_proposal(weak)
    coordinator.submit_proposal(strong)

    ranking = engine.rank_proposals(
        session.session_id
    )

    assert (
        ranking.best_proposal_id
        == strong.proposal_id
    )

    assert (
        ranking.ranked_proposal_ids[0]
        == strong.proposal_id
    )

    assert (
        ranking.scores[0].acceptable
    )

    for voter_id, score in (
        ("architecture-agent", 92),
        ("security-agent", 98),
        ("manager-agent", 97),
    ):
        coordinator.cast_vote(
            NegotiationVote(
                session_id=(
                    session.session_id
                ),
                proposal_id=(
                    strong.proposal_id
                ),
                voter_agent_id=voter_id,
                approve=True,
                score=score,
                rationale=(
                    "Modular governed plan "
                    "satisfies requirements"
                ),
            )
        )

    consensus = (
        coordinator.evaluate_consensus(
            session.session_id
        )
    )

    assert consensus.consensus_reached

    assert (
        consensus.decision_type
        is NegotiationDecisionType
        .ACCEPT_PROPOSAL
    )

    assert (
        consensus.selected_proposal_id
        == strong.proposal_id
    )

    finalized = (
        coordinator.finalize_consensus(
            session_id=session.session_id,
            decided_by=(
                "autonomous-consensus-engine"
            ),
        )
    )

    assert (
        finalized.status
        is NegotiationStatus
        .CONSENSUS_REACHED
    )

    assert finalized.decision is not None

    assert (
        finalized.decision
        .selected_proposal_id
        == strong.proposal_id
    )

    proposal_status = {
        proposal.proposal_id:
            proposal.status
        for proposal
        in finalized.proposals
    }

    assert (
        proposal_status[
            strong.proposal_id
        ]
        is ProposalStatus.ACCEPTED
    )

    assert (
        proposal_status[
            weak.proposal_id
        ]
        is ProposalStatus.REJECTED
    )

    closed = coordinator.close_session(
        session.session_id
    )

    assert (
        closed.status
        is NegotiationStatus.CLOSED
    )

    assert closed.closed_at is not None

    topics = [
        message.topic
        for message in events
    ]

    assert (
        "negotiation.session.created"
        in topics
    )

    assert (
        "negotiation.proposal.submitted"
        in topics
    )

    assert (
        "negotiation.vote.cast"
        in topics
    )

    assert (
        "negotiation.consensus.reached"
        in topics
    )

    assert (
        topics[-1]
        == "negotiation.session.closed"
    )

    assert bus.verify_audit_integrity()

    assert (
        len(bus.message_history())
        == len(bus.delivery_history())
    )


def test_counter_proposal_intelligence_improves_plan():

    events: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="negotiation.**",
        agent_id="proposal-monitor",
        handler=events.append,
    )

    engine, coordinator = (
        create_coordinator(bus)
    )

    session = create_open_session(
        coordinator
    )

    original = weak_proposal(
        session.session_id
    )

    coordinator.submit_proposal(
        original
    )

    original_score = (
        engine.rank_proposals(
            session.session_id
        ).scores[0]
    )

    updated = (
        coordinator
        .generate_counter_proposal(
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

    counter = next(
        proposal
        for proposal in updated.proposals
        if (
            proposal.proposal_id
            != original.proposal_id
        )
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

    ranking = engine.rank_proposals(
        session.session_id
    )

    counter_score = next(
        score
        for score in ranking.scores
        if (
            score.proposal_id
            == counter.proposal_id
        )
    )

    assert (
        counter_score.weighted_score
        > original_score.weighted_score
    )

    assert (
        events[-1].topic
        == "negotiation.proposal.countered"
    )

    assert bus.verify_audit_integrity()


def test_veto_escalates_negotiation():

    events: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="negotiation.**",
        agent_id="governance-monitor",
        handler=events.append,
    )

    _, coordinator = create_coordinator(
        bus
    )

    session = create_open_session(
        coordinator
    )

    proposal = strong_proposal(
        session.session_id
    )

    coordinator.submit_proposal(
        proposal
    )

    coordinator.cast_vote(
        NegotiationVote(
            session_id=session.session_id,
            proposal_id=(
                proposal.proposal_id
            ),
            voter_agent_id=(
                "security-agent"
            ),
            approve=True,
            score=95,
        )
    )

    coordinator.cast_vote(
        NegotiationVote(
            session_id=session.session_id,
            proposal_id=(
                proposal.proposal_id
            ),
            voter_agent_id=(
                "manager-agent"
            ),
            approve=False,
            score=20,
            rationale=(
                "Governance risk requires "
                "human review"
            ),
            veto=True,
        )
    )

    result = coordinator.evaluate_consensus(
        session.session_id
    )

    assert not result.consensus_reached

    assert (
        result.decision_type
        is NegotiationDecisionType
        .ESCALATE
    )

    assert result.resolution is not None
    assert result.resolution.escalated

    assert (
        events[-1].topic
        == "negotiation.escalated"
    )

    assert bus.verify_audit_integrity()


def test_protected_consensus_event_is_fail_closed():

    received: list[
        AgentMessage
    ] = []

    def checker(
        agent_id: str,
        permission: str,
        environment: str,
        resource_scope: str,
    ) -> bool:
        return (
            permission
            != "negotiation_consensus_finalize"
        )

    bus = AgentCommunicationBus(
        authority_gate=(
            CommunicationAuthorityGate(
                checker=checker
            )
        )
    )

    bus.subscribe(
        topic="negotiation.**",
        agent_id="mainnet-monitor",
        handler=received.append,
    )

    _, coordinator = create_coordinator(
        bus
    )

    session = create_open_session(
        coordinator
    )

    proposal = strong_proposal(
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

    delivered_before = len(received)

    result = coordinator.evaluate_consensus(
        session.session_id,
        protected_event=True,
        environment="mainnet",
    )

    assert result.consensus_reached

    assert len(received) == delivered_before

    delivery = (
        bus.delivery_history()[-1]
    )

    assert (
        delivery.status
        is DeliveryStatus.DENIED
    )

    assert not delivery.authority_granted
    assert delivery.dead_lettered

    audit_events = [
        record.event
        for record in bus.audit_records()
    ]

    assert (
        audit_events[-3:]
        == [
            CommunicationAuditEvent
            .MESSAGE_PUBLISHED,
            CommunicationAuditEvent
            .AUTHORITY_DENIED,
            CommunicationAuditEvent
            .DEAD_LETTERED,
        ]
    )

    assert bus.verify_audit_integrity()
