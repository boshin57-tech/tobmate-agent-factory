from __future__ import annotations

from af_core.communication import (
    AgentCommunicationBus,
    AgentMessage,
    CommunicationAuditEvent,
    CommunicationAuthorityGate,
    DeliveryStatus,
    MessageFilter,
    MessageType,
    RetryPolicy,
)


def make_message(
    *,
    topic: str,
    message_type: MessageType,
    sender_agent_id: str,
    workspace_id: str,
    payload: dict[str, object] | None = None,
    metadata: dict[str, str] | None = None,
    priority: int = 5,
    required_capability: str | None = None,
) -> AgentMessage:
    return AgentMessage(
        topic=topic,
        message_type=message_type,
        sender_agent_id=sender_agent_id,
        workspace_id=workspace_id,
        payload=payload or {},
        metadata=metadata or {},
        priority=priority,
        required_capability=required_capability,
    )


def test_end_to_end_agent_collaboration_flow():

    coding_received: list[
        AgentMessage
    ] = []

    security_received: list[
        AgentMessage
    ] = []

    audit_received: list[
        AgentMessage
    ] = []

    authority_gate = (
        CommunicationAuthorityGate(
            checker=lambda agent_id, permission, environment, resource_scope: (
                agent_id
                == "planning-agent"
                and permission
                == "task_assign"
                and environment
                == "runtime"
                and resource_scope
                == "blockchain-workspace"
            )
        )
    )

    bus = AgentCommunicationBus(
        authority_gate=authority_gate,
        retry_policy=RetryPolicy(
            max_attempts=2
        ),
    )

    bus.subscribe(
        topic="task.requested",
        agent_id="coding-agent",
        capability="sui_move",
        workspace_id=(
            "blockchain-workspace"
        ),
        handler=coding_received.append,
    )

    bus.subscribe(
        topic="task.*",
        agent_id="security-agent",
        workspace_id=(
            "blockchain-workspace"
        ),
        capability="sui_move",
        message_filter=MessageFilter(
            min_priority=7
        ),
        handler=security_received.append,
    )

    bus.subscribe(
        topic="**",
        agent_id="audit-agent",
        handler=audit_received.append,
    )

    message = make_message(
        topic="task.requested",
        message_type=(
            MessageType.TASK_REQUESTED
        ),
        sender_agent_id=(
            "planning-agent"
        ),
        workspace_id=(
            "blockchain-workspace"
        ),
        required_capability="sui_move",
        priority=9,
        payload={
            "task_id":
                "move-contract-001",
            "objective":
                "Implement Move contract",
        },
        metadata={
            "required_permission":
                "task_assign",
            "environment":
                "runtime",
            "resource_scope":
                "blockchain-workspace",
        },
    )

    delivery = bus.publish(message)

    assert delivery is not None

    assert (
        delivery.status
        is DeliveryStatus.DELIVERED
    )

    assert delivery.authority_granted

    assert (
        delivery.successful_deliveries
        == 2
    )

    assert len(coding_received) == 1

    assert len(security_received) == 1

    assert len(audit_received) == 0

    assert bus.verify_audit_integrity()

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


def test_authority_denial_blocks_execution():

    received: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus(
        authority_gate=(
            CommunicationAuthorityGate(
                checker=lambda agent_id, permission, environment, resource_scope: False
            )
        )
    )

    bus.subscribe(
        topic="deployment.*",
        agent_id="deployment-agent",
        handler=received.append,
    )

    message = make_message(
        topic="deployment.requested",
        message_type=(
            MessageType.EVENT_PUBLISHED
        ),
        sender_agent_id=(
            "coding-agent"
        ),
        workspace_id=(
            "blockchain-workspace"
        ),
        metadata={
            "required_permission":
                "contract_deploy",
            "environment":
                "mainnet",
            "resource_scope":
                "tobmate-blockchain",
        },
    )

    delivery = bus.publish(message)

    assert delivery is not None

    assert (
        delivery.status
        is DeliveryStatus.DENIED
    )

    assert received == []

    assert bus.dead_letter_count == 1

    assert bus.verify_audit_integrity()


def test_priority_retry_recovery_flow():

    call_order: list[str] = []

    attempts = 0

    def temporary_handler(
        message: AgentMessage,
    ) -> None:
        nonlocal attempts

        attempts += 1

        call_order.append(
            str(
                message.payload[
                    "task_id"
                ]
            )
        )

        if (
            message.payload[
                "task_id"
            ]
            == "retry-task"
            and attempts == 1
        ):
            raise RuntimeError(
                "temporary failure"
            )

    bus = AgentCommunicationBus(
        retry_policy=RetryPolicy(
            max_attempts=2
        )
    )

    bus.subscribe(
        topic="task.*",
        agent_id="worker-agent",
        handler=temporary_handler,
    )

    low = make_message(
        topic="task.requested",
        message_type=(
            MessageType.TASK_REQUESTED
        ),
        sender_agent_id=(
            "planning-agent"
        ),
        workspace_id="workspace-001",
        priority=1,
        payload={
            "task_id": "low-task",
        },
    )

    retry = make_message(
        topic="task.requested",
        message_type=(
            MessageType.TASK_REQUESTED
        ),
        sender_agent_id=(
            "planning-agent"
        ),
        workspace_id="workspace-001",
        priority=9,
        payload={
            "task_id": "retry-task",
        },
    )

    bus.publish(
        low,
        auto_dispatch=False,
    )

    bus.publish(
        retry,
        auto_dispatch=False,
    )

    deliveries = (
        bus.dispatch_all()
    )

    assert (
        deliveries[0].message_id
        == retry.message_id
    )

    assert (
        deliveries[0]
        .retry_scheduled
    )

    assert (
        deliveries[-1].status
        is DeliveryStatus.DELIVERED
    )

    assert bus.dead_letter_count == 0

    assert bus.verify_audit_integrity()
