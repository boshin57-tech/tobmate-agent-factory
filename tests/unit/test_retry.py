import asyncio

import pytest

from af_core.orchestrator.retry import (
    RetryDecision,
    RetryExecutor,
    RetryPolicy,
    RetryReason,
)


def run(coro):
    return asyncio.run(coro)


def classify(exc: Exception) -> RetryReason:
    if isinstance(exc, TimeoutError):
        return RetryReason.TIMEOUT

    if isinstance(exc, PermissionError):
        return RetryReason.POLICY_BLOCK

    return RetryReason.TRANSIENT_EXECUTION


def test_retry_executor_succeeds_after_transient_failure() -> None:
    attempts: list[int] = []

    async def operation(attempt: int) -> str:
        attempts.append(attempt)

        if attempt == 1:
            raise RuntimeError("temporary failure")

        return "success"

    executor = RetryExecutor(
        RetryPolicy(
            maximum_attempts=3,
            base_delay_seconds=0,
        ),
        classify,
    )

    result, history = run(
        executor.execute(operation)
    )

    assert result == "success"
    assert attempts == [1, 2]
    assert len(history.attempts) == 1
    assert history.attempts[0].reason is (
        RetryReason.TRANSIENT_EXECUTION
    )
    assert history.exhausted is False


def test_retry_executor_exhausts_attempts() -> None:
    async def operation(attempt: int) -> str:
        raise TimeoutError(f"timeout-{attempt}")

    executor = RetryExecutor(
        RetryPolicy(
            maximum_attempts=2,
            base_delay_seconds=0,
        ),
        classify,
    )

    with pytest.raises(
        TimeoutError,
        match="timeout-2",
    ):
        run(executor.execute(operation))


def test_retry_policy_escalates_policy_block() -> None:
    policy = RetryPolicy()

    assert policy.decide(
        reason=RetryReason.POLICY_BLOCK,
        completed_attempts=1,
    ) is RetryDecision.ESCALATE


def test_retry_executor_escalates_policy_block() -> None:
    async def operation(attempt: int) -> str:
        raise PermissionError("policy denied")

    executor = RetryExecutor(
        RetryPolicy(
            maximum_attempts=3,
            base_delay_seconds=0,
        ),
        classify,
    )

    with pytest.raises(
        RuntimeError,
        match="Retry escalation required",
    ):
        run(executor.execute(operation))


def test_non_retryable_reason_stops() -> None:
    policy = RetryPolicy()

    assert policy.decide(
        reason=RetryReason.NON_RETRYABLE,
        completed_attempts=1,
    ) is RetryDecision.STOP
