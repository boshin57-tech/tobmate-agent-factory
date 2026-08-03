from __future__ import annotations

from af_core.communication import (
    AgentCommunicationBus,
    AgentMessage,
    DeliveryStatus,
    MessageType,
    RetryPolicy,
)


def make_message(
    *,
    task_id: str,
    priority: int = 5,
) -> AgentMessage:
    return AgentMessage(
        topic="task",
        message_type=(
            MessageType.TASK_REQUESTED
        ),
        sender_agent_id=(
            "planning-agent"
        ),
        workspace_id=(
            "workspace-001"
        ),
        priority=priority,
        payload={
            "task_id": task_id,
        },
    )


def test_higher_priority_message_dispatches_first():

    received: list[str] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="task",
        agent_id="coding-agent",
        handler=lambda message: (
            received.append(
                message.payload[
                    "task_id"
                ]
            )
        ),
    )

    bus.publish(
        make_message(
            task_id="low",
            priority=1,
        ),
        auto_dispatch=False,
    )

    bus.publish(
        make_message(
            task_id="critical",
            priority=9,
        ),
        auto_dispatch=False,
    )

    bus.publish(
        make_message(
            task_id="normal",
            priority=5,
        ),
        auto_dispatch=False,
    )

    bus.dispatch_all()

    assert received == [
        "critical",
        "normal",
        "low",
    ]


def test_equal_priority_preserves_fifo_order():

    received: list[str] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="task",
        agent_id="coding-agent",
        handler=lambda message: (
            received.append(
                message.payload[
                    "task_id"
                ]
            )
        ),
    )

    for task_id in (
        "task-1",
        "task-2",
        "task-3",
    ):
        bus.publish(
            make_message(
                task_id=task_id,
                priority=5,
            ),
            auto_dispatch=False,
        )

    bus.dispatch_all()

    assert received == [
        "task-1",
        "task-2",
        "task-3",
    ]


def test_failed_delivery_is_retried():

    calls = 0

    def handler(
        message: AgentMessage,
    ) -> None:
        nonlocal calls

        calls += 1

        if calls == 1:
            raise RuntimeError(
                "temporary failure"
            )

    bus = AgentCommunicationBus(
        retry_policy=RetryPolicy(
            max_attempts=3
        )
    )

    bus.subscribe(
        topic="task",
        agent_id="coding-agent",
        handler=handler,
    )

    message = make_message(
        task_id="retry-task"
    )

    first = bus.publish(
        message
    )

    assert first is not None

    assert (
        first.status
        is DeliveryStatus.UNDELIVERED
    )

    assert first.attempt == 1
    assert first.retry_scheduled
    assert bus.pending_count == 1

    second = bus.dispatch_next()

    assert second is not None

    assert (
        second.status
        is DeliveryStatus.DELIVERED
    )

    assert second.attempt == 2
    assert not second.retry_scheduled
    assert bus.pending_count == 0
    assert bus.dead_letter_count == 0


def test_exhausted_message_moves_to_dead_letter():

    def failing_handler(
        message: AgentMessage,
    ) -> None:
        raise RuntimeError(
            "permanent failure"
        )

    bus = AgentCommunicationBus(
        retry_policy=RetryPolicy(
            max_attempts=3
        )
    )

    bus.subscribe(
        topic="task",
        agent_id="failing-agent",
        handler=failing_handler,
    )

    message = make_message(
        task_id="failed-task"
    )

    bus.publish(
        message,
        auto_dispatch=False,
    )

    deliveries = (
        bus.dispatch_all()
    )

    assert len(deliveries) == 3

    assert deliveries[0].attempt == 1
    assert deliveries[1].attempt == 2
    assert deliveries[2].attempt == 3

    assert deliveries[2].dead_lettered
    assert not (
        deliveries[2]
        .retry_scheduled
    )

    assert bus.pending_count == 0
    assert bus.dead_letter_count == 1

    dead_letter = (
        bus.dead_letters()[0]
    )

    assert (
        dead_letter.message.message_id
        == message.message_id
    )

    assert dead_letter.attempts == 3

    assert (
        dead_letter.failed_agent_ids
        == ["failing-agent"]
    )


def test_missing_subscriber_is_dead_lettered():

    bus = AgentCommunicationBus(
        retry_policy=RetryPolicy(
            max_attempts=2
        )
    )

    message = make_message(
        task_id="unroutable-task"
    )

    bus.publish(
        message,
        auto_dispatch=False,
    )

    deliveries = bus.dispatch_all()

    assert len(deliveries) == 2

    assert (
        deliveries[-1].status
        is DeliveryStatus.UNDELIVERED
    )

    assert deliveries[-1].dead_lettered
    assert bus.dead_letter_count == 1

    assert (
        bus.dead_letters()[0].reason
        == "no matching subscriber"
    )


def test_dead_letter_can_be_requeued():

    received: list[str] = []

    bus = AgentCommunicationBus(
        retry_policy=RetryPolicy(
            max_attempts=1
        )
    )

    message = make_message(
        task_id="recoverable-task"
    )

    bus.publish(
        message,
        auto_dispatch=False,
    )

    bus.dispatch_all()

    assert bus.dead_letter_count == 1

    bus.subscribe(
        topic="task",
        agent_id="coding-agent",
        handler=lambda item: (
            received.append(
                item.payload[
                    "task_id"
                ]
            )
        ),
    )

    assert bus.requeue_dead_letter(
        message.message_id
    )

    assert bus.dead_letter_count == 0
    assert bus.pending_count == 1

    delivery = bus.dispatch_next()

    assert delivery is not None

    assert (
        delivery.status
        is DeliveryStatus.DELIVERED
    )

    assert delivery.attempt == 1

    assert received == [
        "recoverable-task"
    ]


def test_partial_delivery_retries_message():

    healthy_calls = 0
    failing_calls = 0

    def healthy_handler(
        message: AgentMessage,
    ) -> None:
        nonlocal healthy_calls
        healthy_calls += 1

    def failing_handler(
        message: AgentMessage,
    ) -> None:
        nonlocal failing_calls
        failing_calls += 1

        raise RuntimeError(
            "failure"
        )

    bus = AgentCommunicationBus(
        retry_policy=RetryPolicy(
            max_attempts=2
        )
    )

    bus.subscribe(
        topic="task",
        agent_id="healthy-agent",
        handler=healthy_handler,
    )

    bus.subscribe(
        topic="task",
        agent_id="failing-agent",
        handler=failing_handler,
    )

    message = make_message(
        task_id="partial-task"
    )

    first = bus.publish(
        message
    )

    assert first is not None

    assert (
        first.status
        is DeliveryStatus
        .PARTIALLY_DELIVERED
    )

    assert first.retry_scheduled

    second = bus.dispatch_next()

    assert second is not None
    assert second.dead_lettered

    assert healthy_calls == 2
    assert failing_calls == 2
    assert bus.dead_letter_count == 1
