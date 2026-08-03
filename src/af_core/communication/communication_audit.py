from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CommunicationAuditEvent(
    str,
    Enum,
):
    MESSAGE_PUBLISHED = (
        "message.published"
    )

    AUTHORITY_NOT_REQUIRED = (
        "authority.not_required"
    )

    AUTHORITY_GRANTED = (
        "authority.granted"
    )

    AUTHORITY_DENIED = (
        "authority.denied"
    )

    MESSAGE_DELIVERED = (
        "message.delivered"
    )

    MESSAGE_PARTIALLY_DELIVERED = (
        "message.partially_delivered"
    )

    MESSAGE_UNDELIVERED = (
        "message.undelivered"
    )

    RETRY_SCHEDULED = (
        "message.retry_scheduled"
    )

    DEAD_LETTERED = (
        "message.dead_lettered"
    )

    DEAD_LETTER_REQUEUED = (
        "message.dead_letter_requeued"
    )


class CommunicationAuditRecord(BaseModel):
    """
    Immutable append-only audit record chained to the previous record.
    """

    model_config = {
        "frozen": True,
    }

    sequence: int

    event: CommunicationAuditEvent

    message_id: str
    topic: str

    workspace_id: str | None = None
    actor_agent_id: str | None = None

    details: dict[str, Any] = Field(
        default_factory=dict
    )

    previous_hash: str
    record_hash: str

    recorded_at: datetime


class CommunicationAuditTrail:
    """
    Append-only cryptographic audit trail.

    The public API returns immutable tuples and frozen records.
    `verify_integrity()` recomputes every record hash and validates
    the complete chain.
    """

    GENESIS_HASH = "0" * 64

    def __init__(self) -> None:
        self._records: list[
            CommunicationAuditRecord
        ] = []

    def append(
        self,
        *,
        event: CommunicationAuditEvent,
        message_id: str,
        topic: str,
        workspace_id: str | None = None,
        actor_agent_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> CommunicationAuditRecord:
        sequence = (
            len(self._records) + 1
        )

        previous_hash = (
            self._records[-1].record_hash
            if self._records
            else self.GENESIS_HASH
        )

        recorded_at = datetime.now(
            timezone.utc
        )

        normalized_details = (
            details or {}
        )

        record_hash = self._calculate_hash(
            sequence=sequence,
            event=event,
            message_id=message_id,
            topic=topic,
            workspace_id=workspace_id,
            actor_agent_id=actor_agent_id,
            details=normalized_details,
            previous_hash=previous_hash,
            recorded_at=recorded_at,
        )

        record = CommunicationAuditRecord(
            sequence=sequence,
            event=event,
            message_id=message_id,
            topic=topic,
            workspace_id=workspace_id,
            actor_agent_id=actor_agent_id,
            details=normalized_details,
            previous_hash=previous_hash,
            record_hash=record_hash,
            recorded_at=recorded_at,
        )

        self._records.append(
            record
        )

        return record

    def records(
        self,
    ) -> tuple[
        CommunicationAuditRecord,
        ...
    ]:
        return tuple(
            self._records
        )

    def for_message(
        self,
        message_id: str,
    ) -> tuple[
        CommunicationAuditRecord,
        ...
    ]:
        return tuple(
            record
            for record in self._records
            if record.message_id
            == message_id
        )

    def verify_integrity(
        self,
    ) -> bool:
        expected_previous_hash = (
            self.GENESIS_HASH
        )

        for expected_sequence, record in enumerate(
            self._records,
            start=1,
        ):
            if (
                record.sequence
                != expected_sequence
            ):
                return False

            if (
                record.previous_hash
                != expected_previous_hash
            ):
                return False

            expected_hash = (
                self._calculate_hash(
                    sequence=record.sequence,
                    event=record.event,
                    message_id=(
                        record.message_id
                    ),
                    topic=record.topic,
                    workspace_id=(
                        record.workspace_id
                    ),
                    actor_agent_id=(
                        record.actor_agent_id
                    ),
                    details=record.details,
                    previous_hash=(
                        record.previous_hash
                    ),
                    recorded_at=(
                        record.recorded_at
                    ),
                )
            )

            if (
                record.record_hash
                != expected_hash
            ):
                return False

            expected_previous_hash = (
                record.record_hash
            )

        return True

    def latest_hash(
        self,
    ) -> str:
        if not self._records:
            return self.GENESIS_HASH

        return (
            self._records[-1]
            .record_hash
        )

    @property
    def count(
        self,
    ) -> int:
        return len(
            self._records
        )

    @staticmethod
    def _calculate_hash(
        *,
        sequence: int,
        event: CommunicationAuditEvent,
        message_id: str,
        topic: str,
        workspace_id: str | None,
        actor_agent_id: str | None,
        details: dict[str, Any],
        previous_hash: str,
        recorded_at: datetime,
    ) -> str:
        canonical = {
            "sequence": sequence,
            "event": event.value,
            "message_id": message_id,
            "topic": topic,
            "workspace_id": workspace_id,
            "actor_agent_id":
                actor_agent_id,
            "details": details,
            "previous_hash":
                previous_hash,
            "recorded_at":
                recorded_at.isoformat(),
        }

        encoded = json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")

        return hashlib.sha256(
            encoded
        ).hexdigest()
