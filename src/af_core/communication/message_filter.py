from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from .message_models import (
    AgentMessage,
    MessageType,
)


class MessageFilter(BaseModel):
    """
    Declarative filter applied after topic routing.

    Empty filter fields mean that no restriction is applied for that
    property.
    """

    message_types: set[
        MessageType
    ] = Field(
        default_factory=set
    )

    sender_agent_ids: set[
        str
    ] = Field(
        default_factory=set
    )

    recipient_agent_ids: set[
        str
    ] = Field(
        default_factory=set
    )

    workspace_ids: set[
        str
    ] = Field(
        default_factory=set
    )

    required_capabilities: set[
        str
    ] = Field(
        default_factory=set
    )

    min_priority: int | None = None
    max_priority: int | None = None

    metadata_equals: dict[
        str,
        str,
    ] = Field(
        default_factory=dict
    )

    payload_contains: dict[
        str,
        object,
    ] = Field(
        default_factory=dict
    )

    @field_validator(
        "min_priority",
        "max_priority",
    )
    @classmethod
    def validate_priority(
        cls,
        value: int | None,
    ) -> int | None:
        if value is None:
            return value

        if not 0 <= value <= 9:
            raise ValueError(
                "filter priority must be between 0 and 9"
            )

        return value

    def model_post_init(
        self,
        __context: object,
    ) -> None:
        if (
            self.min_priority
            is not None
            and self.max_priority
            is not None
            and self.min_priority
            > self.max_priority
        ):
            raise ValueError(
                "min_priority must not exceed max_priority"
            )

    def matches(
        self,
        message: AgentMessage,
    ) -> bool:
        if (
            self.message_types
            and message.message_type
            not in self.message_types
        ):
            return False

        if (
            self.sender_agent_ids
            and message.sender_agent_id
            not in self.sender_agent_ids
        ):
            return False

        if (
            self.recipient_agent_ids
            and message.recipient_agent_id
            not in self.recipient_agent_ids
        ):
            return False

        if (
            self.workspace_ids
            and message.workspace_id
            not in self.workspace_ids
        ):
            return False

        if (
            self.required_capabilities
            and message.required_capability
            not in self.required_capabilities
        ):
            return False

        if (
            self.min_priority
            is not None
            and message.priority
            < self.min_priority
        ):
            return False

        if (
            self.max_priority
            is not None
            and message.priority
            > self.max_priority
        ):
            return False

        for key, expected_value in (
            self.metadata_equals.items()
        ):
            if (
                message.metadata.get(key)
                != expected_value
            ):
                return False

        for key, expected_value in (
            self.payload_contains.items()
        ):
            if (
                message.payload.get(key)
                != expected_value
            ):
                return False

        return True
