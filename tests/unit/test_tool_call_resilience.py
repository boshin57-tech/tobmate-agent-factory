from __future__ import annotations

import asyncio

from af_core.orchestrator.retry import (
    RetryPolicy,
    RetryReason,
)
from af_core.runtime.tool_call_models import (
    NormalizedToolCall,
)
from af_core.runtime.tool_call_resilience import (
    ToolCallResilienceExecutor,
    ToolCallResiliencePolicy,
)
from af_core.runtime.tool_call_runtime import (
    ToolCallRuntime,
)
from af_core.tools.models import (
    ExternalToolCall,
    ExternalToolDescriptor,
    ExternalToolResult,
    ExternalToolRisk,
    ToolContent,
    ToolContentType,
    ToolExecutionStatus,
)
from af_core.tools.registry import (
    ExternalToolRegistry,
)


def descriptor(
    *,
    tool_id: str = "tool.resilient",
    name: str = "resilient",
) -> ExternalToolDescriptor:
    return ExternalToolDescriptor(
        tool_id=tool_id,
        name=name,
        description="Resilience test tool",
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        risk=ExternalToolRisk.READ_ONLY,
        timeout_seconds=2,
    )


def call(
    call_id: str = "call-1",
) -> NormalizedToolCall:
    return NormalizedToolCall(
        call_id=call_id,
        tool_name="resilient",
        arguments={},
    )


def resilience(
    *,
    timeout_seconds: float = 1,
    maximum_attempts: int = 3,
    retry_failed_results: bool = False,
) -> ToolCallResilienceExecutor:
    return ToolCallResilienceExecutor(
        ToolCallResiliencePolicy(
            timeout_seconds=timeout_seconds,
            retry=RetryPolicy(
                maximum_attempts=maximum_attempts,
                base_delay_seconds=0,
            ),
            retry_failed_results=(
                retry_failed_results
            ),
        )
    )


def test_timeout_retries_then_succeeds() -> None:
    registry = ExternalToolRegistry()
    attempts = 0

    async def handler(
        external_call: ExternalToolCall,
    ) -> ExternalToolResult:
        nonlocal attempts
        attempts += 1

        if attempts == 1:
            await asyncio.sleep(0.05)

        return ExternalToolResult(
            call_id=external_call.call_id,
            tool_id=external_call.tool_id,
            status=ToolExecutionStatus.SUCCEEDED,
            content=[
                ToolContent(
                    type=ToolContentType.TEXT,
                    text="completed",
                )
            ],
        )

    registry.register(
        descriptor=descriptor(),
        handler=handler,
    )

    runtime = ToolCallRuntime(
        registry=registry,
        resilience_executor=resilience(
            timeout_seconds=0.01,
            maximum_attempts=2,
        ),
    )

    record = asyncio.run(
        runtime.execute_one(call())
    )

    assert record.successful is True
    assert attempts == 2

    result = runtime.resilience_result("call-1")

    assert result is not None
    assert result.attempt_count == 2
    assert result.retried is True
    assert result.attempts[0].timed_out is True
    assert result.attempts[1].successful is True
    assert len(result.retry_history.attempts) == 1
    assert (
        result.retry_history.attempts[0].reason
        is RetryReason.TIMEOUT
    )

    metadata = record.result.metadata["resilience"]

    assert metadata["attempt_count"] == 2
    assert metadata["retried"] is True


def test_timeout_exhaustion_returns_timed_out_result() -> None:
    registry = ExternalToolRegistry()
    attempts = 0

    async def handler(
        external_call: ExternalToolCall,
    ) -> ExternalToolResult:
        nonlocal attempts
        attempts += 1
        await asyncio.sleep(0.05)

        return ExternalToolResult(
            call_id=external_call.call_id,
            tool_id=external_call.tool_id,
            status=ToolExecutionStatus.SUCCEEDED,
        )

    registry.register(
        descriptor=descriptor(),
        handler=handler,
    )

    runtime = ToolCallRuntime(
        registry=registry,
        resilience_executor=resilience(
            timeout_seconds=0.01,
            maximum_attempts=2,
        ),
    )

    record = asyncio.run(
        runtime.execute_one(call())
    )

    assert record.successful is False
    assert attempts == 2
    assert (
        record.result.status
        is ToolExecutionStatus.TIMED_OUT
    )
    assert record.result.call_id == "call-1"
    assert record.result.tool_id == "tool.resilient"

    result = runtime.resilience_result("call-1")

    assert result is not None
    assert result.attempt_count == 2
    assert result.retry_history.exhausted is True
    assert all(
        attempt.timed_out
        for attempt in result.attempts
    )


def test_failed_result_retries_when_enabled() -> None:
    registry = ExternalToolRegistry()
    attempts = 0

    async def handler(
        external_call: ExternalToolCall,
    ) -> ExternalToolResult:
        nonlocal attempts
        attempts += 1

        if attempts == 1:
            return ExternalToolResult(
                call_id=external_call.call_id,
                tool_id=external_call.tool_id,
                status=ToolExecutionStatus.FAILED,
                is_error=True,
                error="temporary failure",
            )

        return ExternalToolResult(
            call_id=external_call.call_id,
            tool_id=external_call.tool_id,
            status=ToolExecutionStatus.SUCCEEDED,
        )

    registry.register(
        descriptor=descriptor(),
        handler=handler,
    )

    runtime = ToolCallRuntime(
        registry=registry,
        resilience_executor=resilience(
            maximum_attempts=2,
            retry_failed_results=True,
        ),
    )

    record = asyncio.run(
        runtime.execute_one(call())
    )

    assert record.successful is True
    assert attempts == 2

    result = runtime.resilience_result("call-1")

    assert result is not None
    assert result.retried is True
    assert (
        result.attempts[0].status
        is ToolExecutionStatus.FAILED
    )
    assert result.attempts[1].successful is True


def test_failed_result_is_not_retried_by_default() -> None:
    registry = ExternalToolRegistry()
    attempts = 0

    async def handler(
        external_call: ExternalToolCall,
    ) -> ExternalToolResult:
        nonlocal attempts
        attempts += 1

        return ExternalToolResult(
            call_id=external_call.call_id,
            tool_id=external_call.tool_id,
            status=ToolExecutionStatus.FAILED,
            is_error=True,
            error="non-retryable failure",
        )

    registry.register(
        descriptor=descriptor(),
        handler=handler,
    )

    runtime = ToolCallRuntime(
        registry=registry,
        resilience_executor=resilience(
            maximum_attempts=3,
            retry_failed_results=False,
        ),
    )

    record = asyncio.run(
        runtime.execute_one(call())
    )

    assert record.successful is False
    assert attempts == 1
    assert record.result.error == (
        "non-retryable failure"
    )

    result = runtime.resilience_result("call-1")

    assert result is not None
    assert result.attempt_count == 1
    assert result.retried is False
    assert result.retry_history.attempts == []
    assert result.retry_history.exhausted is False


def test_successful_first_attempt_has_no_retry_history() -> None:
    registry = ExternalToolRegistry()

    async def handler(
        external_call: ExternalToolCall,
    ) -> ExternalToolResult:
        return ExternalToolResult(
            call_id=external_call.call_id,
            tool_id=external_call.tool_id,
            status=ToolExecutionStatus.SUCCEEDED,
        )

    registry.register(
        descriptor=descriptor(),
        handler=handler,
    )

    runtime = ToolCallRuntime(
        registry=registry,
        resilience_executor=resilience(),
    )

    record = asyncio.run(
        runtime.execute_one(call())
    )

    assert record.successful is True

    result = runtime.resilience_result("call-1")

    assert result is not None
    assert result.attempt_count == 1
    assert result.retried is False
    assert result.retry_history.attempts == []


def test_resilience_results_returns_copy() -> None:
    registry = ExternalToolRegistry()

    async def handler(
        external_call: ExternalToolCall,
    ) -> ExternalToolResult:
        return ExternalToolResult(
            call_id=external_call.call_id,
            tool_id=external_call.tool_id,
            status=ToolExecutionStatus.SUCCEEDED,
        )

    registry.register(
        descriptor=descriptor(),
        handler=handler,
    )

    runtime = ToolCallRuntime(
        registry=registry,
        resilience_executor=resilience(),
    )

    asyncio.run(
        runtime.execute_one(call())
    )

    results = runtime.resilience_results()
    results.clear()

    assert runtime.resilience_result(
        "call-1"
    ) is not None
