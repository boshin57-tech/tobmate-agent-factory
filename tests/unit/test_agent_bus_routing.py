from __future__ import annotations

import pytest

from af_core.communication import (
    AgentCommunicationBus,
    AgentMessage,
    DeliveryStatus,
    MessageFilter,
    MessageType,
    RetryPolicy,
    TopicRouter,
)


def make_message(
    *,
    topic: str = "task.requested",
    message_type: MessageType = (
        MessageType.TASK_REQUESTED
    ),
    sender_agent_id: str = (
        "planning-agent"
    ),
    recipient_agent_id: str | None = None,
    workspace_id: str = (
        "workspace-001"
    ),
    required_capability: str | None = None,
    priority: int = 5,
    metadata: dict[str, str] | None = None,
    payload: dict[str, object] | None = None,
) -> AgentMessage:
    return AgentMessage(
        topic=topic,
        message_type=message_type,
        sender_agent_id=sender_agent_id,
        recipient_agent_id=(
            recipient_agent_id
        ),
        workspace_id=workspace_id,
        required_capability=(
            required_capability
        ),
        priority=priority,
        metadata=metadata or {},
        payload=payload or {},
    )


def test_exact_topic_matching():

    router = TopicRouter()

    assert router.matches(
        "task.requested",
        "task.requested",
    )

    assert not router.matches(
        "task.requested",
        "task.completed",
    )


def test_single_segment_wildcard():

    router = TopicRouter()

    assert router.matches(
        "task.*",
        "task.requested",
    )

    assert router.matches(
        "task.*",
        "task.completed",
    )

    assert not router.matches(
        "task.*",
        "task.lifecycle.completed",
    )


def test_multi_segment_wildcard():

    router = TopicRouter()

    assert router.matches(
        "task.**",
        "task",
    )

    assert router.matches(
        "task.**",
        "task.requested",
    )

    assert router.matches(
        "task.**",
        "task.lifecycle.completed",
    )

    assert not router.matches(
        "task.**",
        "workflow.completed",
    )


def test_global_wildcard():

    router = TopicRouter()

    assert router.matches(
        "**",
        "task.requested",
    )

    assert router.matches(
        "**",
        "security.authority.denied",
    )


def test_invalid_wildcard_pattern_is_rejected():

    router = TopicRouter()

    with pytest.raises(
        ValueError,
        match="complete topic segment",
    ):
        router.matches(
            "task.req*",
            "task.requested",
        )


def test_wildcard_subscription_receives_messages():

    received: list[str] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="task.*",
        agent_id="task-monitor",
        handler=lambda message: (
            received.append(
                message.topic
            )
        ),
    )

    first = bus.publish(
        make_message(
            topic="task.requested"
        )
    )

    second = bus.publish(
        make_message(
            topic="task.completed",
            message_type=(
                MessageType.TASK_COMPLETED
            ),
        )
    )

    assert first is not None
    assert second is not None

    assert received == [
        "task.requested",
        "task.completed",
    ]


def test_global_audit_subscription():

    received: list[str] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="**",
        agent_id="audit-agent",
        handler=lambda message: (
            received.append(
                message.topic
            )
        ),
    )

    bus.publish(
        make_message(
            topic="task.requested"
        )
    )

    bus.publish(
        make_message(
            topic="knowledge.updated",
            message_type=(
                MessageType.KNOWLEDGE_UPDATED
            ),
        )
    )

    assert received == [
        "task.requested",
        "knowledge.updated",
    ]


def test_message_type_filter():

    received: list[MessageType] = []

    bus = AgentCommunicationBus(
        retry_policy=RetryPolicy(
            max_attempts=1
        )
    )

    bus.subscribe(
        topic="task.*",
        agent_id="completion-agent",
        handler=lambda message: (
            received.append(
                message.message_type
            )
        ),
        message_filter=MessageFilter(
            message_types={
                MessageType.TASK_COMPLETED
            }
        ),
    )

    unmatched = bus.publish(
        make_message(
            topic="task.requested",
            message_type=(
                MessageType.TASK_REQUESTED
            ),
        )
    )

    matched = bus.publish(
        make_message(
            topic="task.completed",
            message_type=(
                MessageType.TASK_COMPLETED
            ),
        )
    )

    assert unmatched is not None
    assert matched is not None

    assert (
        unmatched.status
        is DeliveryStatus.UNDELIVERED
    )

    assert (
        matched.status
        is DeliveryStatus.DELIVERED
    )

    assert received == [
        MessageType.TASK_COMPLETED
    ]


def test_priority_and_metadata_filter():

    received: list[str] = []

    bus = AgentCommunicationBus(
        retry_policy=RetryPolicy(
            max_attempts=1
        )
    )

    bus.subscribe(
        topic="security.**",
        agent_id="critical-security-agent",
        handler=lambda message: (
            received.append(
                message.metadata[
                    "classification"
                ]
            )
        ),
        message_filter=MessageFilter(
            min_priority=8,
            metadata_equals={
                "classification":
                    "critical",
            },
        ),
    )

    bus.publish(
        make_message(
            topic="security.alert",
            priority=5,
            metadata={
                "classification":
                    "critical",
            },
        )
    )

    bus.publish(
        make_message(
            topic="security.alert",
            priority=9,
            metadata={
                "classification":
                    "warning",
            },
        )
    )

    delivered = bus.publish(
        make_message(
            topic="security.alert",
            priority=9,
            metadata={
                "classification":
                    "critical",
            },
        )
    )

    assert delivered is not None

    assert (
        delivered.status
        is DeliveryStatus.DELIVERED
    )

    assert received == [
        "critical"
    ]


def test_payload_filter():

    received: list[str] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="task.*",
        agent_id="move-agent",
        handler=lambda message: (
            received.append(
                str(
                    message.payload[
                        "language"
                    ]
                )
            )
        ),
        message_filter=MessageFilter(
            payload_contains={
                "language": "move"
            }
        ),
    )

    bus.publish(
        make_message(
            payload={
                "language": "move"
            }
        )
    )

    assert received == [
        "move"
    ]


def test_custom_predicate_filter():

    received: list[str] = []

    bus = AgentCommunicationBus(
        retry_policy=RetryPolicy(
            max_attempts=1
        )
    )

    bus.subscribe(
        topic="task.**",
        agent_id="large-task-agent",
        handler=lambda message: (
            received.append(
                str(
                    message.payload[
                        "task_id"
                    ]
                )
            )
        ),
        predicate=lambda message: (
            int(
                message.payload.get(
                    "estimated_minutes",
                    0,
                )
            )
            >= 60
        ),
    )

    bus.publish(
        make_message(
            payload={
                "task_id": "short-task",
                "estimated_minutes": 15,
            }
        )
    )

    bus.publish(
        make_message(
            payload={
                "task_id": "large-task",
                "estimated_minutes": 120,
            }
        )
    )

    assert received == [
        "large-task"
    ]


def test_workspace_and_filter_are_combined():

    received: list[str] = []

    bus = AgentCommunicationBus(
        retry_policy=RetryPolicy(
            max_attempts=1
        )
    )

    bus.subscribe(
        topic="task.*",
        agent_id="blockchain-security-agent",
        workspace_id=(
            "blockchain-workspace"
        ),
        handler=lambda message: (
            received.append(
                message.workspace_id
            )
        ),
        message_filter=MessageFilter(
            min_priority=7
        ),
    )

    bus.publish(
        make_message(
            workspace_id=(
                "gsos-workspace"
            ),
            priority=9,
        )
    )

    bus.publish(
        make_message(
            workspace_id=(
                "blockchain-workspace"
            ),
            priority=4,
        )
    )

    bus.publish(
        make_message(
            workspace_id=(
                "blockchain-workspace"
            ),
            priority=8,
        )
    )

    assert received == [
        "blockchain-workspace"
    ]


def test_predicate_exception_is_isolated():

    bus = AgentCommunicationBus(
        retry_policy=RetryPolicy(
            max_attempts=1
        )
    )

    bus.subscribe(
        topic="task.*",
        agent_id="broken-filter-agent",
        handler=lambda message: None,
        predicate=lambda message: (
            1 / 0
        ),
    )

    delivery = bus.publish(
        make_message()
    )

    assert delivery is not None

    assert (
        delivery.status
        is DeliveryStatus.UNDELIVERED
    )
