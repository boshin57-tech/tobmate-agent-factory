from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .message_models import AgentMessage


class DeadLetterRecord(BaseModel):
    message: AgentMessage

    reason: str

    failed_agent_ids: list[str] = Field(
        default_factory=list
    )

    attempts: int

    moved_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )


class DeadLetterQueue:
    """
    Stores messages that could not be delivered after retry exhaustion.
    """

    def __init__(self) -> None:
        self._records: list[
            DeadLetterRecord
        ] = []

    def add(
        self,
        *,
        message: AgentMessage,
        reason: str,
        attempts: int,
        failed_agent_ids: list[str] | None = None,
    ) -> DeadLetterRecord:
        if not reason.strip():
            raise ValueError(
                "reason must not be empty"
            )

        record = DeadLetterRecord(
            message=message,
            reason=reason.strip(),
            attempts=attempts,
            failed_agent_ids=(
                failed_agent_ids
                or []
            ),
        )

        self._records.append(
            record
        )

        return record

    def all(
        self,
    ) -> tuple[
        DeadLetterRecord,
        ...
    ]:
        return tuple(
            self._records
        )

    def find(
        self,
        message_id: str,
    ) -> DeadLetterRecord | None:
        for record in self._records:
            if (
                record.message.message_id
                == message_id
            ):
                return record

        return None

    def remove(
        self,
        message_id: str,
    ) -> DeadLetterRecord | None:
        for index, record in enumerate(
            self._records
        ):
            if (
                record.message.message_id
                == message_id
            ):
                return self._records.pop(
                    index
                )

        return None

    def clear(
        self,
    ) -> None:
        self._records.clear()

    @property
    def count(
        self,
    ) -> int:
        return len(
            self._records
        )
