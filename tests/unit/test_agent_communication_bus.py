from __future__ import annotations

import pytest

from af_core.communication import (
    AgentCommunicationBus,
    AgentMessage,
    DeliveryStatus,
    MessageType,
)


def make_message(
    **overrides,
) -> AgentMessage:
    values = {
        "topic": "task",
        "message_type":
            MessageType.TASK_REQUESTED,
        "sender_agent_id":
            "planning-agent",
        "workspace_id":
            "workspace-001",
        "payload": {
            "task_id": "task-001",
        },
    }

    values.update(overrides)

    return AgentMessage(
        **values
    )


def test_topic_message_is_delivered():

    received = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="task",
        agent_id="coding-agent",
        handler=received.append,
    )

    delivery = bus.publish(
        make_message()
    )

    assert delivery is not None

    assert (
        delivery.status
        is DeliveryStatus.DELIVERED
    )

    assert (
        delivery.successful_deliveries
        == 1
    )

    assert len(received) == 1

    assert (
        received[0].payload["task_id"]
        == "task-001"
    )


def test_topic_message_is_broadcast():

    coding_messages = []
    security_messages = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="task",
        agent_id="coding-agent",
        handler=coding_messages.append,
    )

    bus.subscribe(
        topic="task",
        agent_id="security-agent",
        handler=security_messages.append,
    )

    delivery = bus.publish(
        make_message()
    )

    assert delivery is not None

    assert (
        delivery.successful_deliveries
        == 2
    )

    assert len(coding_messages) == 1
    assert len(security_messages) == 1


def test_direct_recipient_routing():

    coding_messages = []
    security_messages = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="task",
        agent_id="coding-agent",
        handler=coding_messages.append,
    )

    bus.subscribe(
        topic="task",
        agent_id="security-agent",
        handler=security_messages.append,
    )

    delivery = bus.publish(
        make_message(
            recipient_agent_id=
                "security-agent",
        )
    )

    assert delivery is not None

    assert (
        delivery.delivered_agent_ids
        == ["security-agent"]
    )

    assert coding_messages == []
    assert len(security_messages) == 1


def test_capability_routing():

    move_messages = []
    python_messages = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="task",
        agent_id="move-agent",
        capability="sui_move",
        handler=move_messages.append,
    )

    bus.subscribe(
        topic="task",
        agent_id="python-agent",
        capability="python",
        handler=python_messages.append,
    )

    delivery = bus.publish(
        make_message(
            required_capability=
                "sui_move",
        )
    )

    assert delivery is not None

    assert (
        delivery.delivered_agent_ids
        == ["move-agent"]
    )

    assert len(move_messages) == 1
    assert python_messages == []


def test_workspace_isolation():

    workspace_a_messages = []
    workspace_b_messages = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="task",
        agent_id="agent-a",
        workspace_id="workspace-001",
        handler=workspace_a_messages.append,
    )

    bus.subscribe(
        topic="task",
        agent_id="agent-b",
        workspace_id="workspace-002",
        handler=workspace_b_messages.append,
    )

    delivery = bus.publish(
        make_message(
            workspace_id=
                "workspace-001",
        )
    )

    assert delivery is not None

    assert (
        delivery.delivered_agent_ids
        == ["agent-a"]
    )

    assert len(workspace_a_messages) == 1
    assert workspace_b_messages == []


def test_message_can_wait_for_dispatch():

    received = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="task",
        agent_id="coding-agent",
        handler=received.append,
    )

    result = bus.publish(
        make_message(),
        auto_dispatch=False,
    )

    assert result is None
    assert bus.pending_count == 1
    assert received == []

    delivery = bus.dispatch_next()

    assert delivery is not None
    assert bus.pending_count == 0
    assert len(received) == 1


def test_unsubscribed_topic_is_undelivered():

    bus = AgentCommunicationBus()

    delivery = bus.publish(
        make_message()
    )

    assert delivery is not None

    assert (
        delivery.status
        is DeliveryStatus.UNDELIVERED
    )

    assert (
        delivery.attempted_subscribers
        == 0
    )


def test_failed_handler_is_isolated():

    successful_messages = []

    def failing_handler(
        message: AgentMessage,
    ) -> None:
        raise RuntimeError(
            "handler failure"
        )

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="task",
        agent_id="failing-agent",
        handler=failing_handler,
    )

    bus.subscribe(
        topic="task",
        agent_id="healthy-agent",
        handler=successful_messages.append,
    )

    delivery = bus.publish(
        make_message()
    )

    assert delivery is not None

    assert (
        delivery.status
        is DeliveryStatus
        .PARTIALLY_DELIVERED
    )

    assert (
        delivery.failed_agent_ids
        == ["failing-agent"]
    )

    assert (
        delivery.delivered_agent_ids
        == ["healthy-agent"]
    )

    assert len(successful_messages) == 1

    assert bus.pending_count == 1


def test_duplicate_message_is_rejected():

    bus = AgentCommunicationBus()

    message = make_message()

    bus.publish(message)

    with pytest.raises(
        ValueError,
        match="duplicate message_id",
    ):
        bus.publish(message)


def test_duplicate_subscription_is_rejected():

    bus = AgentCommunicationBus()

    def handler(
        message: AgentMessage,
    ) -> None:
        return None

    bus.subscribe(
        topic="task",
        agent_id="coding-agent",
        handler=handler,
    )

    with pytest.raises(
        ValueError,
        match="subscription already exists",
    ):
        bus.subscribe(
            topic="task",
            agent_id="coding-agent",
            handler=handler,
        )


def test_message_and_delivery_history():

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="task",
        agent_id="coding-agent",
        handler=lambda message: None,
    )

    message = make_message()

    bus.publish(message)

    assert (
        bus.message_history()
        == (message,)
    )

    assert (
        len(
            bus.delivery_history()
        )
        == 1
    )


def test_invalid_priority_is_rejected():

    with pytest.raises(
        ValueError,
        match="priority",
    ):
        make_message(
            priority=10
        )
