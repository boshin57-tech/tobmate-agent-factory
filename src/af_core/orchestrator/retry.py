from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class RetryReason(StrEnum):
    TRANSIENT_EXECUTION = "TRANSIENT_EXECUTION"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"
    REVIEW_CHANGES_REQUIRED = "REVIEW_CHANGES_REQUIRED"
    TIMEOUT = "TIMEOUT"
    POLICY_BLOCK = "POLICY_BLOCK"
    NON_RETRYABLE = "NON_RETRYABLE"


class RetryDecision(StrEnum):
    RETRY = "RETRY"
    STOP = "STOP"
    ESCALATE = "ESCALATE"


class RetryAttempt(BaseModel):
    attempt: int
    reason: RetryReason
    error: str | None = None
    delay_seconds: float = 0.0


class RetryHistory(BaseModel):
    maximum_attempts: int
    attempts: list[RetryAttempt] = Field(default_factory=list)
    exhausted: bool = False


class RetryPolicy(BaseModel):
    maximum_attempts: int = Field(default=2, ge=1, le=10)
    base_delay_seconds: float = Field(default=0.1, ge=0.0, le=60.0)
    retryable_reasons: set[RetryReason] = Field(
        default_factory=lambda: {
            RetryReason.TRANSIENT_EXECUTION,
            RetryReason.VALIDATION_FAILURE,
            RetryReason.REVIEW_CHANGES_REQUIRED,
            RetryReason.TIMEOUT,
        }
    )

    def decide(
        self,
        *,
        reason: RetryReason,
        completed_attempts: int,
    ) -> RetryDecision:
        if reason is RetryReason.POLICY_BLOCK:
            return RetryDecision.ESCALATE

        if reason not in self.retryable_reasons:
            return RetryDecision.STOP

        if completed_attempts >= self.maximum_attempts:
            return RetryDecision.STOP

        return RetryDecision.RETRY

    def delay_for(self, attempt: int) -> float:
        if attempt <= 1:
            return self.base_delay_seconds

        return min(
            self.base_delay_seconds * (2 ** (attempt - 1)),
            60.0,
        )


RetryOperation = Callable[[int], Awaitable[T]]
RetryClassifier = Callable[[Exception], RetryReason]


class RetryExecutor(Generic[T]):
    def __init__(
        self,
        policy: RetryPolicy,
        classifier: RetryClassifier,
    ) -> None:
        self.policy = policy
        self.classifier = classifier

    async def execute(
        self,
        operation: RetryOperation[T],
    ) -> tuple[T, RetryHistory]:
        history = RetryHistory(
            maximum_attempts=self.policy.maximum_attempts
        )

        attempt = 1

        while True:
            try:
                result = await operation(attempt)
                return result, history
            except Exception as exc:
                reason = self.classifier(exc)
                decision = self.policy.decide(
                    reason=reason,
                    completed_attempts=attempt,
                )

                delay = (
                    self.policy.delay_for(attempt)
                    if decision is RetryDecision.RETRY
                    else 0.0
                )

                history.attempts.append(
                    RetryAttempt(
                        attempt=attempt,
                        reason=reason,
                        error=str(exc),
                        delay_seconds=delay,
                    )
                )

                if decision is RetryDecision.ESCALATE:
                    raise RuntimeError(
                        f"Retry escalation required: {reason}: {exc}"
                    ) from exc

                if decision is RetryDecision.STOP:
                    history.exhausted = True
                    raise

                await asyncio.sleep(delay)
                attempt += 1
