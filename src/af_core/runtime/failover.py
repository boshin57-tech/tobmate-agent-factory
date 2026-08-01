from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from .routing import RoutingCandidate, RoutingResult


T = TypeVar("T")


class FailoverOutcome(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    EXHAUSTED = "EXHAUSTED"
    BLOCKED = "BLOCKED"


class FailoverAttempt(BaseModel):
    rank: int
    model_key: str
    provider_id: str
    provider_model_id: str
    successful: bool
    error: str | None = None


class FailoverResult(BaseModel, Generic[T]):
    outcome: FailoverOutcome
    value: T | None = None
    selected_model_key: str | None = None
    selected_provider_id: str | None = None
    attempts: list[FailoverAttempt] = Field(
        default_factory=list
    )
    failure_reason: str | None = None


class FailoverExhaustedError(RuntimeError):
    """Raised when all model candidates fail."""


CandidateOperation = Callable[
    [RoutingCandidate],
    Awaitable[T],
]

RetryClassifier = Callable[
    [Exception],
    bool,
]


class ProviderFailoverExecutor(Generic[T]):
    def __init__(
        self,
        *,
        retry_classifier: RetryClassifier | None = None,
    ) -> None:
        self.retry_classifier = (
            retry_classifier
            or self._default_retry_classifier
        )

    async def execute(
        self,
        *,
        routing: RoutingResult,
        operation: CandidateOperation[T],
        raise_on_exhaustion: bool = False,
    ) -> FailoverResult[T]:
        attempts: list[FailoverAttempt] = []

        if not routing.candidates:
            result = FailoverResult[T](
                outcome=FailoverOutcome.BLOCKED,
                attempts=[],
                failure_reason=(
                    "Routing produced no usable model candidates."
                ),
            )

            if raise_on_exhaustion:
                raise FailoverExhaustedError(
                    result.failure_reason
                )

            return result

        for candidate in routing.candidates:
            model = candidate.model

            try:
                value = await operation(candidate)
            except Exception as exc:
                attempts.append(
                    FailoverAttempt(
                        rank=candidate.rank,
                        model_key=model.model_key,
                        provider_id=model.provider_id,
                        provider_model_id=(
                            model.provider_model_id
                        ),
                        successful=False,
                        error=str(exc),
                    )
                )

                if not self.retry_classifier(exc):
                    return FailoverResult[T](
                        outcome=FailoverOutcome.BLOCKED,
                        attempts=attempts,
                        failure_reason=(
                            "Non-retryable provider failure: "
                            f"{exc}"
                        ),
                    )

                continue

            attempts.append(
                FailoverAttempt(
                    rank=candidate.rank,
                    model_key=model.model_key,
                    provider_id=model.provider_id,
                    provider_model_id=(
                        model.provider_model_id
                    ),
                    successful=True,
                )
            )

            return FailoverResult[T](
                outcome=FailoverOutcome.SUCCEEDED,
                value=value,
                selected_model_key=model.model_key,
                selected_provider_id=model.provider_id,
                attempts=attempts,
            )

        reason = (
            "All routed model candidates failed."
        )

        result = FailoverResult[T](
            outcome=FailoverOutcome.EXHAUSTED,
            attempts=attempts,
            failure_reason=reason,
        )

        if raise_on_exhaustion:
            raise FailoverExhaustedError(reason)

        return result

    def _default_retry_classifier(
        self,
        exc: Exception,
    ) -> bool:
        non_retryable_types = (
            PermissionError,
            ValueError,
            TypeError,
        )

        return not isinstance(
            exc,
            non_retryable_types,
        )
