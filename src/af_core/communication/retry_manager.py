from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .message_models import AgentMessage


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3

    def __post_init__(
        self,
    ) -> None:
        if self.max_attempts < 1:
            raise ValueError(
                "max_attempts must be at least 1"
            )


@dataclass(frozen=True)
class RetryState:
    message_id: str
    attempts: int
    max_attempts: int
    exhausted: bool

    updated_at: datetime


class RetryManager:
    """
    Tracks delivery attempts without mutating immutable messages.

    Attempt 1 is the initial delivery.
    """

    def __init__(
        self,
        policy: RetryPolicy | None = None,
    ) -> None:
        self._policy = (
            policy
            or RetryPolicy()
        )

        self._attempts: dict[
            str,
            int,
        ] = {}

    def register_attempt(
        self,
        message: AgentMessage,
    ) -> RetryState:
        attempts = (
            self._attempts.get(
                message.message_id,
                0,
            )
            + 1
        )

        self._attempts[
            message.message_id
        ] = attempts

        return self.state(
            message.message_id
        )

    def can_retry(
        self,
        message_id: str,
    ) -> bool:
        attempts = self._attempts.get(
            message_id,
            0,
        )

        return (
            attempts
            < self._policy.max_attempts
        )

    def attempts(
        self,
        message_id: str,
    ) -> int:
        return self._attempts.get(
            message_id,
            0,
        )

    def state(
        self,
        message_id: str,
    ) -> RetryState:
        attempts = self.attempts(
            message_id
        )

        return RetryState(
            message_id=message_id,
            attempts=attempts,
            max_attempts=(
                self._policy.max_attempts
            ),
            exhausted=(
                attempts
                >= self._policy.max_attempts
            ),
            updated_at=(
                datetime.now(
                    timezone.utc
                )
            ),
        )

    def clear(
        self,
        message_id: str,
    ) -> None:
        self._attempts.pop(
            message_id,
            None,
        )

    @property
    def max_attempts(
        self,
    ) -> int:
        return (
            self._policy.max_attempts
        )
