from __future__ import annotations

from .authority_gate import (
    AuthorityDecisionStatus,
    CommunicationAuthorityGate,
)
from .communication_audit import (
    CommunicationAuditEvent,
    CommunicationAuditTrail,
)
from .dead_letter_queue import (
    DeadLetterQueue,
)
from .message_filter import (
    MessageFilter,
)
from .message_models import (
    AgentMessage,
    DeliveryStatus,
    MessageDelivery,
)
from .priority_message_queue import (
    PriorityMessageQueue,
)
from .retry_manager import (
    RetryManager,
    RetryPolicy,
)
from .subscription_registry import (
    MessageHandler,
    MessagePredicate,
    SubscriptionRegistry,
)


class AgentCommunicationBus:
    """
    Secure in-memory Agent Communication Bus.

    Features:
    - Topic and wildcard routing
    - Direct recipient routing
    - Capability routing
    - Workspace isolation
    - Declarative and predicate filtering
    - Priority dispatch
    - Retry management
    - Dead letter isolation
    - Authority enforcement
    - Immutable hash-chain audit trail
    """

    def __init__(
        self,
        registry: SubscriptionRegistry | None = None,
        retry_policy: RetryPolicy | None = None,
        dead_letter_queue: DeadLetterQueue | None = None,
        authority_gate: CommunicationAuthorityGate | None = None,
        audit_trail: CommunicationAuditTrail | None = None,
    ) -> None:
        self._registry = (
            registry
            or SubscriptionRegistry()
        )

        self._pending = (
            PriorityMessageQueue()
        )

        self._retry_manager = (
            RetryManager(
                retry_policy
            )
        )

        self._dead_letter_queue = (
            dead_letter_queue
            or DeadLetterQueue()
        )

        self._authority_gate = (
            authority_gate
            or CommunicationAuthorityGate()
        )

        self._audit_trail = (
            audit_trail
            or CommunicationAuditTrail()
        )

        self._message_history: list[
            AgentMessage
        ] = []

        self._delivery_history: list[
            MessageDelivery
        ] = []

        self._known_message_ids: set[
            str
        ] = set()

    def subscribe(
        self,
        *,
        topic: str,
        agent_id: str,
        handler: MessageHandler,
        workspace_id: str | None = None,
        capability: str | None = None,
        message_filter: MessageFilter | None = None,
        predicate: MessagePredicate | None = None,
    ) -> None:
        self._registry.subscribe(
            topic=topic,
            agent_id=agent_id,
            handler=handler,
            workspace_id=workspace_id,
            capability=capability,
            message_filter=message_filter,
            predicate=predicate,
        )

    def unsubscribe(
        self,
        *,
        topic: str,
        agent_id: str,
    ) -> bool:
        return self._registry.unsubscribe(
            topic=topic,
            agent_id=agent_id,
        )

    def publish(
        self,
        message: AgentMessage,
        *,
        auto_dispatch: bool = True,
    ) -> MessageDelivery | None:
        if (
            message.message_id
            in self._known_message_ids
        ):
            raise ValueError(
                "duplicate message_id"
            )

        self._known_message_ids.add(
            message.message_id
        )

        self._message_history.append(
            message
        )

        self._pending.push(
            message
        )

        self._audit_trail.append(
            event=(
                CommunicationAuditEvent
                .MESSAGE_PUBLISHED
            ),
            message_id=message.message_id,
            topic=message.topic,
            workspace_id=(
                message.workspace_id
            ),
            actor_agent_id=(
                message.sender_agent_id
            ),
            details={
                "message_type":
                    message.message_type.value,
                "priority":
                    message.priority,
                "recipient_agent_id":
                    message.recipient_agent_id,
                "required_capability":
                    message.required_capability,
            },
        )

        if auto_dispatch:
            return self.dispatch_next()

        return None

    def dispatch_next(
        self,
    ) -> MessageDelivery | None:
        message = self._pending.pop()

        if message is None:
            return None

        authority = (
            self._authority_gate
            .evaluate(message)
        )

        if (
            authority.status
            is AuthorityDecisionStatus
            .NOT_REQUIRED
        ):
            self._audit_trail.append(
                event=(
                    CommunicationAuditEvent
                    .AUTHORITY_NOT_REQUIRED
                ),
                message_id=(
                    message.message_id
                ),
                topic=message.topic,
                workspace_id=(
                    message.workspace_id
                ),
                actor_agent_id=(
                    message.sender_agent_id
                ),
                details={
                    "reason":
                        authority.reason,
                },
            )

        elif (
            authority.status
            is AuthorityDecisionStatus
            .ALLOWED
        ):
            self._audit_trail.append(
                event=(
                    CommunicationAuditEvent
                    .AUTHORITY_GRANTED
                ),
                message_id=(
                    message.message_id
                ),
                topic=message.topic,
                workspace_id=(
                    message.workspace_id
                ),
                actor_agent_id=(
                    message.sender_agent_id
                ),
                details={
                    "permission":
                        authority.permission,
                    "environment":
                        authority.environment,
                    "resource_scope":
                        authority.resource_scope,
                    "reason":
                        authority.reason,
                },
            )

        else:
            return self._deny_message(
                message=message,
                authority_reason=(
                    authority.reason
                ),
                permission=(
                    authority.permission
                ),
                environment=(
                    authority.environment
                ),
                resource_scope=(
                    authority.resource_scope
                ),
            )

        retry_state = (
            self._retry_manager
            .register_attempt(
                message
            )
        )

        subscriptions = (
            self._registry.matching(
                message
            )
        )

        delivered_agent_ids: list[str] = []
        failed_agent_ids: list[str] = []

        for subscription in subscriptions:
            try:
                subscription.handler(
                    message
                )

                delivered_agent_ids.append(
                    subscription.agent_id
                )

            except Exception:
                failed_agent_ids.append(
                    subscription.agent_id
                )

        attempted = len(
            subscriptions
        )

        successful = len(
            delivered_agent_ids
        )

        failed = len(
            failed_agent_ids
        )

        retry_scheduled = False
        dead_lettered = False

        if attempted == 0:
            status = (
                DeliveryStatus.UNDELIVERED
            )

            if (
                self._retry_manager
                .can_retry(
                    message.message_id
                )
            ):
                self._pending.push(
                    message
                )

                retry_scheduled = True

            else:
                self._dead_letter_queue.add(
                    message=message,
                    reason=(
                        "no matching subscriber"
                    ),
                    attempts=(
                        retry_state.attempts
                    ),
                )

                dead_lettered = True

        elif failed == 0:
            status = (
                DeliveryStatus.DELIVERED
            )

            self._retry_manager.clear(
                message.message_id
            )

        elif successful == 0:
            status = (
                DeliveryStatus.UNDELIVERED
            )

            if (
                self._retry_manager
                .can_retry(
                    message.message_id
                )
            ):
                self._pending.push(
                    message
                )

                retry_scheduled = True

            else:
                self._dead_letter_queue.add(
                    message=message,
                    reason=(
                        "all subscribed handlers failed"
                    ),
                    attempts=(
                        retry_state.attempts
                    ),
                    failed_agent_ids=(
                        failed_agent_ids
                    ),
                )

                dead_lettered = True

        else:
            status = (
                DeliveryStatus
                .PARTIALLY_DELIVERED
            )

            if (
                self._retry_manager
                .can_retry(
                    message.message_id
                )
            ):
                self._pending.push(
                    message
                )

                retry_scheduled = True

            else:
                self._dead_letter_queue.add(
                    message=message,
                    reason=(
                        "one or more subscribed "
                        "handlers failed"
                    ),
                    attempts=(
                        retry_state.attempts
                    ),
                    failed_agent_ids=(
                        failed_agent_ids
                    ),
                )

                dead_lettered = True

        delivery = MessageDelivery(
            message_id=message.message_id,
            topic=message.topic,
            attempted_subscribers=attempted,
            successful_deliveries=successful,
            failed_deliveries=failed,
            status=status,
            attempt=retry_state.attempts,
            retry_scheduled=(
                retry_scheduled
            ),
            dead_lettered=(
                dead_lettered
            ),
            authority_granted=True,
            authority_reason=(
                authority.reason
            ),
            delivered_agent_ids=(
                delivered_agent_ids
            ),
            failed_agent_ids=(
                failed_agent_ids
            ),
        )

        self._delivery_history.append(
            delivery
        )

        self._audit_delivery(
            message=message,
            delivery=delivery,
        )

        return delivery

    def _deny_message(
        self,
        *,
        message: AgentMessage,
        authority_reason: str,
        permission: str | None,
        environment: str | None,
        resource_scope: str | None,
    ) -> MessageDelivery:
        self._dead_letter_queue.add(
            message=message,
            reason=(
                "authority denied: "
                f"{authority_reason}"
            ),
            attempts=0,
        )

        delivery = MessageDelivery(
            message_id=message.message_id,
            topic=message.topic,
            attempted_subscribers=0,
            successful_deliveries=0,
            failed_deliveries=0,
            status=DeliveryStatus.DENIED,
            attempt=0,
            retry_scheduled=False,
            dead_lettered=True,
            authority_granted=False,
            authority_reason=(
                authority_reason
            ),
        )

        self._delivery_history.append(
            delivery
        )

        self._audit_trail.append(
            event=(
                CommunicationAuditEvent
                .AUTHORITY_DENIED
            ),
            message_id=message.message_id,
            topic=message.topic,
            workspace_id=(
                message.workspace_id
            ),
            actor_agent_id=(
                message.sender_agent_id
            ),
            details={
                "permission": permission,
                "environment": environment,
                "resource_scope":
                    resource_scope,
                "reason":
                    authority_reason,
            },
        )

        self._audit_trail.append(
            event=(
                CommunicationAuditEvent
                .DEAD_LETTERED
            ),
            message_id=message.message_id,
            topic=message.topic,
            workspace_id=(
                message.workspace_id
            ),
            actor_agent_id=(
                message.sender_agent_id
            ),
            details={
                "reason":
                    "authority denied",
                "attempts": 0,
            },
        )

        return delivery

    def _audit_delivery(
        self,
        *,
        message: AgentMessage,
        delivery: MessageDelivery,
    ) -> None:
        if (
            delivery.status
            is DeliveryStatus.DELIVERED
        ):
            event = (
                CommunicationAuditEvent
                .MESSAGE_DELIVERED
            )

        elif (
            delivery.status
            is DeliveryStatus
            .PARTIALLY_DELIVERED
        ):
            event = (
                CommunicationAuditEvent
                .MESSAGE_PARTIALLY_DELIVERED
            )

        else:
            event = (
                CommunicationAuditEvent
                .MESSAGE_UNDELIVERED
            )

        self._audit_trail.append(
            event=event,
            message_id=message.message_id,
            topic=message.topic,
            workspace_id=(
                message.workspace_id
            ),
            actor_agent_id=(
                message.sender_agent_id
            ),
            details={
                "attempt":
                    delivery.attempt,
                "attempted_subscribers":
                    delivery.attempted_subscribers,
                "successful_deliveries":
                    delivery.successful_deliveries,
                "failed_deliveries":
                    delivery.failed_deliveries,
                "delivered_agent_ids":
                    delivery.delivered_agent_ids,
                "failed_agent_ids":
                    delivery.failed_agent_ids,
            },
        )

        if delivery.retry_scheduled:
            self._audit_trail.append(
                event=(
                    CommunicationAuditEvent
                    .RETRY_SCHEDULED
                ),
                message_id=(
                    message.message_id
                ),
                topic=message.topic,
                workspace_id=(
                    message.workspace_id
                ),
                actor_agent_id=(
                    message.sender_agent_id
                ),
                details={
                    "attempt":
                        delivery.attempt,
                },
            )

        if delivery.dead_lettered:
            self._audit_trail.append(
                event=(
                    CommunicationAuditEvent
                    .DEAD_LETTERED
                ),
                message_id=(
                    message.message_id
                ),
                topic=message.topic,
                workspace_id=(
                    message.workspace_id
                ),
                actor_agent_id=(
                    message.sender_agent_id
                ),
                details={
                    "attempts":
                        delivery.attempt,
                    "failed_agent_ids":
                        delivery.failed_agent_ids,
                },
            )

    def dispatch_all(
        self,
        *,
        max_dispatches: int = 1000,
    ) -> tuple[
        MessageDelivery,
        ...
    ]:
        if max_dispatches < 1:
            raise ValueError(
                "max_dispatches must be at least 1"
            )

        deliveries: list[
            MessageDelivery
        ] = []

        while (
            self._pending
            and len(deliveries)
            < max_dispatches
        ):
            delivery = self.dispatch_next()

            if delivery is not None:
                deliveries.append(
                    delivery
                )

        return tuple(
            deliveries
        )

    def requeue_dead_letter(
        self,
        message_id: str,
    ) -> bool:
        record = (
            self._dead_letter_queue
            .remove(message_id)
        )

        if record is None:
            return False

        self._retry_manager.clear(
            message_id
        )

        self._pending.push(
            record.message
        )

        self._audit_trail.append(
            event=(
                CommunicationAuditEvent
                .DEAD_LETTER_REQUEUED
            ),
            message_id=(
                record.message.message_id
            ),
            topic=record.message.topic,
            workspace_id=(
                record.message.workspace_id
            ),
            actor_agent_id=(
                record.message.sender_agent_id
            ),
            details={
                "previous_reason":
                    record.reason,
            },
        )

        return True

    def message_history(
        self,
    ) -> tuple[
        AgentMessage,
        ...
    ]:
        return tuple(
            self._message_history
        )

    def delivery_history(
        self,
    ) -> tuple[
        MessageDelivery,
        ...
    ]:
        return tuple(
            self._delivery_history
        )

    def pending_messages(
        self,
    ) -> tuple[
        AgentMessage,
        ...
    ]:
        return self._pending.messages()

    def dead_letters(
        self,
    ):
        return (
            self._dead_letter_queue
            .all()
        )

    def audit_records(
        self,
    ):
        return (
            self._audit_trail
            .records()
        )

    def verify_audit_integrity(
        self,
    ) -> bool:
        return (
            self._audit_trail
            .verify_integrity()
        )

    def retry_attempts(
        self,
        message_id: str,
    ) -> int:
        return (
            self._retry_manager
            .attempts(message_id)
        )

    @property
    def pending_count(
        self,
    ) -> int:
        return len(
            self._pending
        )

    @property
    def dead_letter_count(
        self,
    ) -> int:
        return (
            self._dead_letter_queue
            .count
        )

    @property
    def audit_count(
        self,
    ) -> int:
        return (
            self._audit_trail.count
        )

    @property
    def subscription_count(
        self,
    ) -> int:
        return self._registry.count
