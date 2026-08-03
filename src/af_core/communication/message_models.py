from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class MessageType(str, Enum):
    TASK_REQUESTED = "task.requested"
    TASK_ASSIGNED = "task.assigned"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"

    EVENT_PUBLISHED = "event.published"
    STATUS_UPDATED = "status.updated"
    HEARTBEAT = "agent.heartbeat"

    KNOWLEDGE_UPDATED = "knowledge.updated"

    AUTHORITY_REQUESTED = "authority.requested"
    AUTHORITY_GRANTED = "authority.granted"
    AUTHORITY_DENIED = "authority.denied"

    WORKFLOW_UPDATED = "workflow.updated"

    AUDIT_RECORDED = "audit.recorded"
    LEARNING_GENERATED = "learning.generated"


class DeliveryStatus(str, Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    PARTIALLY_DELIVERED = "partially_delivered"
    UNDELIVERED = "undelivered"
    DENIED = "denied"


class AgentMessage(BaseModel):
    """
    Immutable communication envelope exchanged between agents.

    The bus routes messages by topic, direct recipient, or required
    capability without requiring agents to know each other's internals.
    """

    message_id: str = Field(
        default_factory=lambda: str(uuid4())
    )

    topic: str
    message_type: MessageType

    sender_agent_id: str

    recipient_agent_id: str | None = None
    required_capability: str | None = None

    workspace_id: str
    correlation_id: str | None = None
    causation_id: str | None = None

    priority: int = 5

    payload: dict[str, Any] = Field(
        default_factory=dict
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    metadata: dict[str, str] = Field(
        default_factory=dict
    )

    @field_validator(
        "topic",
        "sender_agent_id",
        "workspace_id",
    )
    @classmethod
    def validate_required_text(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "value must not be empty"
            )

        return normalized

    @field_validator("priority")
    @classmethod
    def validate_priority(
        cls,
        value: int,
    ) -> int:
        if not 0 <= value <= 9:
            raise ValueError(
                "priority must be between 0 and 9"
            )

        return value


class MessageDelivery(BaseModel):
    message_id: str
    topic: str

    attempted_subscribers: int
    successful_deliveries: int
    failed_deliveries: int

    status: DeliveryStatus

    attempt: int = 1
    retry_scheduled: bool = False
    dead_lettered: bool = False

    authority_granted: bool = True
    authority_reason: str | None = None

    delivered_agent_ids: list[str] = Field(
        default_factory=list
    )

    failed_agent_ids: list[str] = Field(
        default_factory=list
    )

    delivered_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
