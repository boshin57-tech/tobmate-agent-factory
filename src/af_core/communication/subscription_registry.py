from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .message_filter import (
    MessageFilter,
)
from .message_models import (
    AgentMessage,
)
from .topic_router import (
    TopicRouter,
)


MessageHandler = Callable[
    [AgentMessage],
    None,
]

MessagePredicate = Callable[
    [AgentMessage],
    bool,
]


@dataclass(frozen=True)
class AgentSubscription:
    """
    Agent subscription registered against a topic pattern.

    The `topic` field may contain `*` or `**` wildcards.
    """

    topic: str
    agent_id: str
    handler: MessageHandler

    workspace_id: str | None = None
    capability: str | None = None

    message_filter: MessageFilter | None = None
    predicate: MessagePredicate | None = None


class SubscriptionRegistry:
    """
    Maintains topic-pattern subscriptions and applies routing filters.
    """

    def __init__(
        self,
        router: TopicRouter | None = None,
    ) -> None:
        self._router = (
            router
            or TopicRouter()
        )

        self._subscriptions: list[
            AgentSubscription
        ] = []

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
    ) -> AgentSubscription:
        normalized_topic = (
            self._router.validate_pattern(
                topic
            )
        )

        normalized_agent_id = (
            agent_id.strip()
        )

        if not normalized_agent_id:
            raise ValueError(
                "agent_id must not be empty"
            )

        normalized_workspace_id = (
            workspace_id.strip()
            if workspace_id is not None
            else None
        )

        normalized_capability = (
            capability.strip()
            if capability is not None
            else None
        )

        if (
            normalized_workspace_id
            == ""
        ):
            raise ValueError(
                "workspace_id must not be empty"
            )

        if (
            normalized_capability
            == ""
        ):
            raise ValueError(
                "capability must not be empty"
            )

        subscription = AgentSubscription(
            topic=normalized_topic,
            agent_id=normalized_agent_id,
            handler=handler,
            workspace_id=(
                normalized_workspace_id
            ),
            capability=(
                normalized_capability
            ),
            message_filter=message_filter,
            predicate=predicate,
        )

        duplicate = any(
            existing.topic
            == subscription.topic
            and existing.agent_id
            == subscription.agent_id
            and existing.workspace_id
            == subscription.workspace_id
            and existing.capability
            == subscription.capability
            and existing.message_filter
            == subscription.message_filter
            for existing in self._subscriptions
        )

        if duplicate:
            raise ValueError(
                "subscription already exists"
            )

        self._subscriptions.append(
            subscription
        )

        return subscription

    def unsubscribe(
        self,
        *,
        topic: str,
        agent_id: str,
    ) -> bool:
        normalized_topic = (
            self._router.validate_pattern(
                topic
            )
        )

        normalized_agent_id = (
            agent_id.strip()
        )

        original_count = len(
            self._subscriptions
        )

        self._subscriptions = [
            subscription
            for subscription
            in self._subscriptions
            if not (
                subscription.topic
                == normalized_topic
                and subscription.agent_id
                == normalized_agent_id
            )
        ]

        return (
            len(self._subscriptions)
            != original_count
        )

    def matching(
        self,
        message: AgentMessage,
    ) -> tuple[
        AgentSubscription,
        ...
    ]:
        matches: list[
            AgentSubscription
        ] = []

        for subscription in (
            self._subscriptions
        ):
            if not self._router.matches(
                subscription.topic,
                message.topic,
            ):
                continue

            if (
                subscription.workspace_id
                is not None
                and subscription.workspace_id
                != message.workspace_id
            ):
                continue

            if (
                message.recipient_agent_id
                is not None
                and subscription.agent_id
                != message.recipient_agent_id
            ):
                continue

            if (
                message.required_capability
                is not None
                and subscription.capability
                != message.required_capability
            ):
                continue

            if (
                subscription.message_filter
                is not None
                and not (
                    subscription
                    .message_filter
                    .matches(message)
                )
            ):
                continue

            if (
                subscription.predicate
                is not None
            ):
                try:
                    accepted = (
                        subscription.predicate(
                            message
                        )
                    )
                except Exception:
                    accepted = False

                if not accepted:
                    continue

            matches.append(
                subscription
            )

        return tuple(matches)

    def subscribers(
        self,
        topic: str,
    ) -> tuple[str, ...]:
        normalized_topic = (
            self._router.validate_topic(
                topic
            )
        )

        return tuple(
            subscription.agent_id
            for subscription
            in self._subscriptions
            if self._router.matches(
                subscription.topic,
                normalized_topic,
            )
        )

    def subscriptions(
        self,
    ) -> tuple[
        AgentSubscription,
        ...
    ]:
        return tuple(
            self._subscriptions
        )

    @property
    def count(
        self,
    ) -> int:
        return len(
            self._subscriptions
        )
