from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import TypeVar

from pydantic import BaseModel, Field

from af_core.orchestrator.retry import (
    RetryAttempt,
    RetryExecutor,
    RetryHistory,
    RetryPolicy,
    RetryReason,
)
from af_core.tools.models import (
    ExternalToolResult,
    ToolExecutionStatus,
)


T = TypeVar("T")


class ToolRetryClassification(StrEnum):
    RESULT = "RESULT"
    EXCEPTION = "EXCEPTION"


class ToolCallTimeoutError(TimeoutError):
    """Raised when one tool attempt exceeds its timeout."""


class RetryableToolResultError(RuntimeError):
    def __init__(
        self,
        *,
        result: ExternalToolResult,
        reason: RetryReason,
    ) -> None:
        self.result = result
        self.reason = reason

        super().__init__(
            result.error
            or (
                "Tool returned retryable status "
                f"{result.status.value}."
            )
        )


class ToolAttemptRecord(BaseModel):
    attempt: int
    status: ToolExecutionStatus
    successful: bool
    error: str | None = None
    timed_out: bool = False


class ResilientToolExecutionResult(BaseModel):
    result: ExternalToolResult
    retry_history: RetryHistory
    attempts: list[ToolAttemptRecord] = Field(
        default_factory=list
    )

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)

    @property
    def retried(self) -> bool:
        return self.attempt_count > 1


ToolOperation = Callable[
    [int],
    Awaitable[ExternalToolResult],
]


class ToolCallResiliencePolicy(BaseModel):
    timeout_seconds: float = Field(
        default=60.0,
        gt=0.0,
        le=3600.0,
    )
    retry: RetryPolicy = Field(
        default_factory=RetryPolicy
    )
    retryable_statuses: set[
        ToolExecutionStatus
    ] = Field(
        default_factory=lambda: {
            ToolExecutionStatus.TIMED_OUT,
        }
    )
    retry_failed_results: bool = False


class ToolCallResilienceExecutor:
    def __init__(
        self,
        policy: ToolCallResiliencePolicy | None = None,
    ) -> None:
        self.policy = (
            policy or ToolCallResiliencePolicy()
        )

    async def execute(
        self,
        operation: ToolOperation,
    ) -> ResilientToolExecutionResult:
        attempts: list[ToolAttemptRecord] = []

        retry_executor = RetryExecutor[
            ExternalToolResult
        ](
            policy=self.policy.retry,
            classifier=self._classify_exception,
        )

        async def guarded_operation(
            attempt: int,
        ) -> ExternalToolResult:
            try:
                result = await asyncio.wait_for(
                    operation(attempt),
                    timeout=self.policy.timeout_seconds,
                )
            except TimeoutError as exc:
                attempts.append(
                    ToolAttemptRecord(
                        attempt=attempt,
                        status=(
                            ToolExecutionStatus.TIMED_OUT
                        ),
                        successful=False,
                        error=(
                            "Tool attempt exceeded "
                            f"{self.policy.timeout_seconds} "
                            "seconds."
                        ),
                        timed_out=True,
                    )
                )

                raise ToolCallTimeoutError(
                    "Tool attempt exceeded "
                    f"{self.policy.timeout_seconds} "
                    "seconds."
                ) from exc

            successful = (
                result.status
                is ToolExecutionStatus.SUCCEEDED
                and not result.is_error
            )

            attempts.append(
                ToolAttemptRecord(
                    attempt=attempt,
                    status=result.status,
                    successful=successful,
                    error=result.error,
                    timed_out=(
                        result.status
                        is ToolExecutionStatus.TIMED_OUT
                    ),
                )
            )

            retry_reason = self._result_retry_reason(
                result
            )

            if retry_reason is not None:
                raise RetryableToolResultError(
                    result=result,
                    reason=retry_reason,
                )

            return result

        try:
            result, history = await retry_executor.execute(
                guarded_operation
            )

            return ResilientToolExecutionResult(
                result=result,
                retry_history=history,
                attempts=attempts,
            )

        except RetryableToolResultError as exc:
            return ResilientToolExecutionResult(
                result=exc.result,
                retry_history=self._history_from_attempts(
                    attempts=attempts,
                    exhausted=True,
                ),
                attempts=attempts,
            )

        except ToolCallTimeoutError as exc:
            result = ExternalToolResult(
                call_id="",
                tool_id="",
                status=ToolExecutionStatus.TIMED_OUT,
                is_error=True,
                error=str(exc),
            )

            return ResilientToolExecutionResult(
                result=result,
                retry_history=self._history_from_attempts(
                    attempts=attempts,
                    exhausted=True,
                ),
                attempts=attempts,
            )

    def _result_retry_reason(
        self,
        result: ExternalToolResult,
    ) -> RetryReason | None:
        if (
            result.status
            is ToolExecutionStatus.TIMED_OUT
        ):
            return RetryReason.TIMEOUT

        if (
            result.status
            in self.policy.retryable_statuses
        ):
            return RetryReason.TRANSIENT_EXECUTION

        if (
            self.policy.retry_failed_results
            and result.status
            is ToolExecutionStatus.FAILED
        ):
            return RetryReason.TRANSIENT_EXECUTION

        return None

    def _classify_exception(
        self,
        exc: Exception,
    ) -> RetryReason:
        if isinstance(
            exc,
            ToolCallTimeoutError,
        ):
            return RetryReason.TIMEOUT

        if isinstance(
            exc,
            RetryableToolResultError,
        ):
            return exc.reason

        if isinstance(
            exc,
            (
                ConnectionError,
                OSError,
            ),
        ):
            return RetryReason.TRANSIENT_EXECUTION

        return RetryReason.NON_RETRYABLE

    def _history_from_attempts(
        self,
        *,
        attempts: list[ToolAttemptRecord],
        exhausted: bool,
    ) -> RetryHistory:
        history = RetryHistory(
            maximum_attempts=(
                self.policy.retry.maximum_attempts
            ),
            exhausted=exhausted,
        )

        for item in attempts:
            if item.successful:
                continue

            reason = (
                RetryReason.TIMEOUT
                if item.timed_out
                else RetryReason.TRANSIENT_EXECUTION
            )

            history.attempts.append(
                RetryAttempt(
                    attempt=item.attempt,
                    reason=reason,
                    error=item.error,
                    delay_seconds=0.0,
                )
            )

        return history
