from __future__ import annotations

from af_core.communication import (
    AgentCommunicationBus,
    CommunicationAuditEvent,
    CommunicationAuthorityGate,
    DeliveryStatus,
)
from af_core.organization import (
    MultiAgentTaskCoordinationEngine,
    TaskCoordinationCoordinator,
    TaskCoordinationEventPublisher,
    TaskCoordinationWorkflow,
)


def make_coordinator(
    bus: AgentCommunicationBus,
) -> TaskCoordinationCoordinator:
    return TaskCoordinationCoordinator(
        engine=(
            MultiAgentTaskCoordinationEngine()
        ),
        publisher=(
            TaskCoordinationEventPublisher(
                bus
            )
        ),
    )


def make_workflow() -> (
    TaskCoordinationWorkflow
):
    return TaskCoordinationWorkflow(
        workflow_id="workflow-001",
        workspace_id="workspace-001",
        team_id="team-001",
        name="Protected Workflow",
        objective=(
            "Validate task authority controls"
        ),
        created_by="planner-agent",
    )


def test_protected_workflow_event_is_denied_without_authority():
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

    workflow = coordinator.create_workflow(
        make_workflow(),
        protected_event=True,
        environment="mainnet",
    )

    assert (
        workflow.workflow_id
        == "workflow-001"
    )

    delivery = (
        bus.delivery_history()[-1]
    )

    assert (
        delivery.status
        is DeliveryStatus.DENIED
    )

    assert not delivery.authority_granted
    assert delivery.dead_lettered
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


def test_protected_workflow_event_is_allowed_with_authority():
    received = []

    def checker(
        agent_id: str,
        permission: str,
        environment: str,
        resource_scope: str,
    ) -> bool:
        return (
            agent_id
            == "multi-agent-task-coordinator"
            and permission
            == "task_workflow_manage"
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
        topic="task.**",
        agent_id="mainnet-governance",
        handler=received.append,
    )

    coordinator = make_coordinator(
        bus
    )

    coordinator.create_workflow(
        make_workflow(),
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

    assert (
        received[0].metadata[
            "required_permission"
        ]
        == "task_workflow_manage"
    )

    assert (
        received[0].metadata[
            "environment"
        ]
        == "mainnet"
    )

    assert (
        received[0].metadata[
            "resource_scope"
        ]
        == "team-001"
    )

    events = [
        record.event
        for record in bus.audit_records()
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

    coordinator.create_workflow(
        make_workflow(),
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

    assert (
        delivery.authority_reason
        == "authority checker failed"
    )

    assert delivery.dead_lettered

    assert bus.verify_audit_integrity()


def test_unprotected_event_does_not_require_authority():
    received = []

    bus = AgentCommunicationBus(
        authority_gate=(
            CommunicationAuthorityGate(
                checker=lambda agent_id, permission, environment, resource_scope: False
            )
        )
    )

    bus.subscribe(
        topic="task.**",
        agent_id="runtime-monitor",
        handler=received.append,
    )

    coordinator = make_coordinator(
        bus
    )

    coordinator.create_workflow(
        make_workflow(),
        protected_event=False,
    )

    delivery = (
        bus.delivery_history()[-1]
    )

    assert (
        delivery.status
        is DeliveryStatus.DELIVERED
    )

    assert len(received) == 1

    assert (
        "required_permission"
        not in received[0].metadata
    )

    assert bus.dead_letter_count == 0
    assert bus.verify_audit_integrity()


def test_audit_chain_detects_record_tampering():
    bus = AgentCommunicationBus()

    coordinator = make_coordinator(
        bus
    )

    coordinator.create_workflow(
        make_workflow()
    )

    assert bus.verify_audit_integrity()

    records = bus.audit_records()

    assert records

    record = records[0]

    original_hash = record.record_hash

    object.__setattr__(
        record,
        "record_hash",
        "tampered-hash",
    )

    assert not bus.verify_audit_integrity()

    object.__setattr__(
        record,
        "record_hash",
        original_hash,
    )

    assert bus.verify_audit_integrity()
