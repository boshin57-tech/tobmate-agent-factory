from __future__ import annotations

import pytest
from pydantic import ValidationError

from af_core.communication import (
    AgentCommunicationBus,
    AgentMessage,
    AuthorityDecisionStatus,
    CommunicationAuditEvent,
    CommunicationAuditTrail,
    CommunicationAuthorityGate,
    DeliveryStatus,
    MessageType,
)


def make_message(
    *,
    metadata: dict[str, str] | None = None,
) -> AgentMessage:
    return AgentMessage(
        topic="task.requested",
        message_type=(
            MessageType.TASK_REQUESTED
        ),
        sender_agent_id=(
            "blockchain-agent"
        ),
        workspace_id=(
            "blockchain-workspace"
        ),
        payload={
            "task_id":
                "deploy-contract",
        },
        metadata=metadata or {},
    )


def test_unprotected_message_is_allowed():

    gate = CommunicationAuthorityGate()

    decision = gate.evaluate(
        make_message()
    )

    assert (
        decision.status
        is AuthorityDecisionStatus
        .NOT_REQUIRED
    )

    assert decision.allowed


def test_protected_message_without_checker_is_denied():

    gate = CommunicationAuthorityGate()

    decision = gate.evaluate(
        make_message(
            metadata={
                "required_permission":
                    "contract_deploy",
                "environment":
                    "mainnet",
            }
        )
    )

    assert (
        decision.status
        is AuthorityDecisionStatus
        .DENIED
    )

    assert not decision.allowed


def test_authorized_message_is_delivered():

    received = []

    gate = CommunicationAuthorityGate(
        checker=lambda agent_id, permission, environment, resource_scope: (
            agent_id
            == "blockchain-agent"
            and permission
            == "contract_deploy"
            and environment
            == "testnet"
            and resource_scope
            == "tobmate-blockchain"
        )
    )

    bus = AgentCommunicationBus(
        authority_gate=gate
    )

    bus.subscribe(
        topic="task.*",
        agent_id="execution-agent",
        handler=received.append,
    )

    delivery = bus.publish(
        make_message(
            metadata={
                "required_permission":
                    "contract_deploy",
                "environment":
                    "testnet",
                "resource_scope":
                    "tobmate-blockchain",
            }
        )
    )

    assert delivery is not None

    assert (
        delivery.status
        is DeliveryStatus.DELIVERED
    )

    assert delivery.authority_granted
    assert len(received) == 1


def test_denied_message_never_reaches_handler():

    received = []

    gate = CommunicationAuthorityGate(
        checker=lambda agent_id, permission, environment, resource_scope: False
    )

    bus = AgentCommunicationBus(
        authority_gate=gate
    )

    bus.subscribe(
        topic="task.*",
        agent_id="execution-agent",
        handler=received.append,
    )

    delivery = bus.publish(
        make_message(
            metadata={
                "required_permission":
                    "contract_deploy",
                "environment":
                    "mainnet",
            }
        )
    )

    assert delivery is not None

    assert (
        delivery.status
        is DeliveryStatus.DENIED
    )

    assert not (
        delivery.authority_granted
    )

    assert delivery.dead_lettered
    assert delivery.attempt == 0

    assert received == []
    assert bus.pending_count == 0
    assert bus.dead_letter_count == 1


def test_authority_checker_failure_denies_message():

    def failing_checker(
        agent_id: str,
        permission: str,
        environment: str,
        resource_scope: str,
    ) -> bool:
        raise RuntimeError(
            "authority backend unavailable"
        )

    gate = CommunicationAuthorityGate(
        checker=failing_checker
    )

    bus = AgentCommunicationBus(
        authority_gate=gate
    )

    delivery = bus.publish(
        make_message(
            metadata={
                "required_permission":
                    "contract_deploy",
            }
        )
    )

    assert delivery is not None

    assert (
        delivery.status
        is DeliveryStatus.DENIED
    )

    assert (
        delivery.authority_reason
        == "authority checker failed"
    )


def test_audit_records_publish_authority_and_delivery():

    gate = CommunicationAuthorityGate(
        checker=lambda agent_id, permission, environment, resource_scope: True
    )

    bus = AgentCommunicationBus(
        authority_gate=gate
    )

    bus.subscribe(
        topic="task.*",
        agent_id="execution-agent",
        handler=lambda message: None,
    )

    message = make_message(
        metadata={
            "required_permission":
                "contract_deploy",
            "environment":
                "testnet",
        }
    )

    bus.publish(message)

    events = [
        record.event
        for record
        in bus.audit_records()
    ]

    assert events == [
        CommunicationAuditEvent
        .MESSAGE_PUBLISHED,

        CommunicationAuditEvent
        .AUTHORITY_GRANTED,

        CommunicationAuditEvent
        .MESSAGE_DELIVERED,
    ]

    assert bus.verify_audit_integrity()


def test_denied_message_audit_chain():

    gate = CommunicationAuthorityGate(
        checker=lambda agent_id, permission, environment, resource_scope: False
    )

    bus = AgentCommunicationBus(
        authority_gate=gate
    )

    message = make_message(
        metadata={
            "required_permission":
                "contract_deploy",
            "environment":
                "mainnet",
        }
    )

    bus.publish(message)

    events = [
        record.event
        for record
        in bus.audit_records()
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


def test_retry_events_are_audited():

    calls = 0

    def temporary_failure(
        message: AgentMessage,
    ) -> None:
        nonlocal calls
        calls += 1

        if calls == 1:
            raise RuntimeError(
                "temporary failure"
            )

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="task.*",
        agent_id="execution-agent",
        handler=temporary_failure,
    )

    message = make_message()

    bus.publish(message)

    first_events = [
        record.event
        for record
        in bus.audit_records()
    ]

    assert (
        CommunicationAuditEvent
        .RETRY_SCHEDULED
        in first_events
    )

    bus.dispatch_next()

    final_events = [
        record.event
        for record
        in bus.audit_records()
    ]

    assert (
        final_events[-1]
        is CommunicationAuditEvent
        .MESSAGE_DELIVERED
    )

    assert bus.verify_audit_integrity()


def test_audit_records_are_frozen():

    trail = CommunicationAuditTrail()

    record = trail.append(
        event=(
            CommunicationAuditEvent
            .MESSAGE_PUBLISHED
        ),
        message_id="message-001",
        topic="task.requested",
    )

    with pytest.raises(
        ValidationError
    ):
        record.sequence = 99


def test_audit_hash_chain_links_records():

    trail = CommunicationAuditTrail()

    first = trail.append(
        event=(
            CommunicationAuditEvent
            .MESSAGE_PUBLISHED
        ),
        message_id="message-001",
        topic="task.requested",
    )

    second = trail.append(
        event=(
            CommunicationAuditEvent
            .MESSAGE_DELIVERED
        ),
        message_id="message-001",
        topic="task.requested",
    )

    assert (
        first.previous_hash
        == trail.GENESIS_HASH
    )

    assert (
        second.previous_hash
        == first.record_hash
    )

    assert trail.verify_integrity()


def test_message_specific_audit_query():

    trail = CommunicationAuditTrail()

    trail.append(
        event=(
            CommunicationAuditEvent
            .MESSAGE_PUBLISHED
        ),
        message_id="message-001",
        topic="task.requested",
    )

    trail.append(
        event=(
            CommunicationAuditEvent
            .MESSAGE_PUBLISHED
        ),
        message_id="message-002",
        topic="task.requested",
    )

    records = trail.for_message(
        "message-001"
    )

    assert len(records) == 1

    assert (
        records[0].message_id
        == "message-001"
    )
