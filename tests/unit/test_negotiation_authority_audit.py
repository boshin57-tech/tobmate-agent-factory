from __future__ import annotations

from af_core.communication import (
    AgentCommunicationBus,
    CommunicationAuditEvent,
    CommunicationAuthorityGate,
    DeliveryStatus,
)
from af_core.organization import (
    AgentNegotiationEngine,
    NegotiationCoordinator,
    NegotiationEventPublisher,
    NegotiationSession,
)


def make_coordinator(
    bus: AgentCommunicationBus,
) -> NegotiationCoordinator:
    return NegotiationCoordinator(
        engine=AgentNegotiationEngine(),
        publisher=(
            NegotiationEventPublisher(bus)
        ),
    )


def test_protected_event_is_denied_without_authority():

    bus = AgentCommunicationBus(
        authority_gate=(
            CommunicationAuthorityGate(
                checker=lambda agent_id, permission, environment, resource_scope: False
            )
        )
    )

    coordinator = make_coordinator(
        bus
    )

    coordinator.create_session(
        NegotiationSession(
            workspace_id="workspace-001",
            team_id="team-001",
            subject="Protected negotiation",
            objective="Test authority denial",
            created_by="manager-agent",
        ),
        protected_event=True,
        environment="mainnet",
    )

    delivery = (
        bus.delivery_history()[-1]
    )

    assert (
        delivery.status
        is DeliveryStatus.DENIED
    )

    assert not delivery.authority_granted
    assert bus.dead_letter_count == 1

    events = [
        record.event
        for record in bus.audit_records()
    ]

    assert events == [
        CommunicationAuditEvent
        .MESSAGE_PUBLISHED,
        CommunicationAuditEvent
        .AUTHORITY_DENIED,
        CommunicationAuditEvent
        .DEAD_LETTERED,
    ]

    assert bus.verify_audit_integrity()


def test_protected_event_is_allowed_with_authority():

    received = []

    def checker(
        agent_id: str,
        permission: str,
        environment: str,
        resource_scope: str,
    ) -> bool:
        return (
            agent_id
            == "agent-negotiation-engine"
            and permission
            == "negotiation_session_manage"
            and environment
            == "mainnet"
            and resource_scope
            == "team-001"
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
        agent_id="governance-monitor",
        handler=received.append,
    )

    coordinator = make_coordinator(
        bus
    )

    coordinator.create_session(
        NegotiationSession(
            workspace_id="workspace-001",
            team_id="team-001",
            subject="Authorized negotiation",
            objective="Test protected delivery",
            created_by="manager-agent",
        ),
        protected_event=True,
        environment="mainnet",
    )

    delivery = (
        bus.delivery_history()[-1]
    )

    assert (
        delivery.status
        is DeliveryStatus.DELIVERED
    )

    assert delivery.authority_granted
    assert len(received) == 1

    audit_events = [
        record.event
        for record in bus.audit_records()
    ]

    assert audit_events == [
        CommunicationAuditEvent
        .MESSAGE_PUBLISHED,
        CommunicationAuditEvent
        .AUTHORITY_GRANTED,
        CommunicationAuditEvent
        .MESSAGE_DELIVERED,
    ]

    assert bus.verify_audit_integrity()


def test_authority_checker_failure_fails_closed():

    def failing_checker(
        agent_id: str,
        permission: str,
        environment: str,
        resource_scope: str,
    ) -> bool:
        raise RuntimeError(
            "authority service unavailable"
        )

    bus = AgentCommunicationBus(
        authority_gate=(
            CommunicationAuthorityGate(
                checker=failing_checker
            )
        )
    )

    coordinator = make_coordinator(
        bus
    )

    coordinator.create_session(
        NegotiationSession(
            workspace_id="workspace-001",
            team_id="team-001",
            subject="Fail closed",
            objective="Test checker failure",
            created_by="manager-agent",
        ),
        protected_event=True,
        environment="mainnet",
    )

    delivery = (
        bus.delivery_history()[-1]
    )

    assert (
        delivery.status
        is DeliveryStatus.DENIED
    )

    assert (
        delivery.authority_reason
        == "authority checker failed"
    )

    assert bus.verify_audit_integrity()
