from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from af_core.orchestrator.retry import RetryPolicy
from af_core.runtime.budget import (
    BudgetLimit,
    BudgetPolicy,
    BudgetScope,
)
from af_core.runtime.provider_protocol import (
    NormalizedTokenUsage,
)
from af_core.runtime.tool_call_batch import (
    ToolBatchCallStatus,
    ToolBatchGovernancePolicy,
    ToolBatchGovernor,
    ToolBatchLimitError,
    ToolBatchStatus,
)
from af_core.runtime.tool_call_budget import (
    ToolCallBudgetGovernor,
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
    ToolCallRuntimePolicy,
)
from af_core.runtime.usage import (
    CostBreakdown,
    UsageRecord,
)
from af_core.tools.models import (
    ExternalToolCall,
    ExternalToolDescriptor,
    ExternalToolResult,
    ExternalToolRisk,
    ToolExecutionStatus,
)
from af_core.tools.registry import (
    ExternalToolRegistry,
)


def normalized(
    call_id: str,
    *,
    tool_name: str = "batch_tool",
) -> NormalizedToolCall:
    return NormalizedToolCall(
        call_id=call_id,
        tool_name=tool_name,
        arguments={},
    )


def descriptor(
    *,
    tool_id: str = "tool.batch",
    name: str = "batch_tool",
) -> ExternalToolDescriptor:
    return ExternalToolDescriptor(
        tool_id=tool_id,
        name=name,
        description="Batch test tool",
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        risk=ExternalToolRisk.READ_ONLY,
    )


def budget_estimator(
    call: ExternalToolCall,
    tool: ExternalToolDescriptor,
    attempts: int,
) -> UsageRecord:
    del call, tool

    return UsageRecord.model_construct(
        provider_id="tool-runtime",
        model_id="batch-tool",
        usage=NormalizedTokenUsage(
            input_tokens=10 * attempts,
            output_tokens=5 * attempts,
        ),
        cost=CostBreakdown(
            total_cost_usd=(
                Decimal("0.005")
                * attempts
            ),
        ),
    )


def budget_governor(
    maximum_cost: str,
) -> ToolCallBudgetGovernor:
    return ToolCallBudgetGovernor(
        policy=BudgetPolicy(
            [
                BudgetLimit(
                    scope=BudgetScope.GLOBAL,
                    scope_id="global",
                    maximum_cost_usd=Decimal(
                        maximum_cost
                    ),
                )
            ]
        ),
        estimator=budget_estimator,
    )


def registry_with_handler(
    handler,
) -> ExternalToolRegistry:
    registry = ExternalToolRegistry()
    registry.register(
        descriptor=descriptor(),
        handler=handler,
    )
    return registry


def test_batch_limit_rejects_oversized_batch() -> None:
    governor = ToolBatchGovernor(
        ToolBatchGovernancePolicy(
            maximum_calls_per_batch=2,
        )
    )

    runtime = ToolCallRuntime(
        registry=ExternalToolRegistry(),
        batch_governor=governor,
    )

    with pytest.raises(
        ToolBatchLimitError,
        match="exceeds maximum",
    ):
        asyncio.run(
            runtime.execute_many(
                [
                    normalized("call-1"),
                    normalized("call-2"),
                    normalized("call-3"),
                ]
            )
        )


def test_run_limit_accumulates_across_batches() -> None:
    async def handler(
        call: ExternalToolCall,
    ) -> ExternalToolResult:
        return ExternalToolResult(
            call_id=call.call_id,
            tool_id=call.tool_id,
            status=ToolExecutionStatus.SUCCEEDED,
        )

    governor = ToolBatchGovernor(
        ToolBatchGovernancePolicy(
            maximum_calls_per_batch=4,
            maximum_calls_per_run=3,
        )
    )

    runtime = ToolCallRuntime(
        registry=registry_with_handler(handler),
        batch_governor=governor,
    )

    first = asyncio.run(
        runtime.execute_many(
            [
                normalized("call-1"),
                normalized("call-2"),
            ],
            run_id="run-1",
        )
    )

    assert first.successful is True
    assert governor.run_call_count("run-1") == 2

    with pytest.raises(
        ToolBatchLimitError,
        match="run call count",
    ):
        asyncio.run(
            runtime.execute_many(
                [
                    normalized("call-3"),
                    normalized("call-4"),
                ],
                run_id="run-1",
            )
        )


def test_parallel_failure_isolation_keeps_other_calls() -> None:
    async def handler(
        call: ExternalToolCall,
    ) -> ExternalToolResult:
        await asyncio.sleep(0.01)

        if call.call_id == "call-fail":
            return ExternalToolResult(
                call_id=call.call_id,
                tool_id=call.tool_id,
                status=ToolExecutionStatus.FAILED,
                is_error=True,
                error="isolated failure",
            )

        return ExternalToolResult(
            call_id=call.call_id,
            tool_id=call.tool_id,
            status=ToolExecutionStatus.SUCCEEDED,
        )

    governor = ToolBatchGovernor(
        ToolBatchGovernancePolicy(
            isolate_failures=True,
            cancel_pending_on_failure=False,
        )
    )

    runtime = ToolCallRuntime(
        registry=registry_with_handler(handler),
        policy=ToolCallRuntimePolicy(
            maximum_parallelism=3,
            allow_parallel_execution=True,
            stop_on_failure=False,
        ),
        batch_governor=governor,
    )

    batch = asyncio.run(
        runtime.execute_many(
            [
                normalized("call-ok-1"),
                normalized("call-fail"),
                normalized("call-ok-2"),
            ],
            run_id="run-isolation",
        )
    )

    assert len(batch.records) == 3
    assert batch.successful is False

    audit = runtime.latest_batch_audit()

    assert audit is not None
    assert (
        audit.status
        is ToolBatchStatus.PARTIALLY_SUCCEEDED
    )
    assert audit.succeeded_count == 2
    assert audit.failed_count == 1
    assert audit.cancelled_count == 0
    assert audit.failure_isolated is True

    statuses = {
        item.call_id: item.status
        for item in audit.calls
    }

    assert statuses["call-fail"] is (
        ToolBatchCallStatus.FAILED
    )
    assert statuses["call-ok-1"] is (
        ToolBatchCallStatus.SUCCEEDED
    )
    assert statuses["call-ok-2"] is (
        ToolBatchCallStatus.SUCCEEDED
    )


def test_parallel_stop_on_failure_cancels_pending_calls() -> None:
    started: list[str] = []

    async def handler(
        call: ExternalToolCall,
    ) -> ExternalToolResult:
        started.append(call.call_id)

        if call.call_id == "call-fail":
            await asyncio.sleep(0.01)

            return ExternalToolResult(
                call_id=call.call_id,
                tool_id=call.tool_id,
                status=ToolExecutionStatus.FAILED,
                is_error=True,
                error="stop batch",
            )

        await asyncio.sleep(0.2)

        return ExternalToolResult(
            call_id=call.call_id,
            tool_id=call.tool_id,
            status=ToolExecutionStatus.SUCCEEDED,
        )

    governor = ToolBatchGovernor(
        ToolBatchGovernancePolicy(
            cancel_pending_on_failure=True,
            isolate_failures=False,
        )
    )

    runtime = ToolCallRuntime(
        registry=registry_with_handler(handler),
        policy=ToolCallRuntimePolicy(
            maximum_parallelism=1,
            allow_parallel_execution=True,
            stop_on_failure=True,
        ),
        batch_governor=governor,
    )

    batch = asyncio.run(
        runtime.execute_many(
            [
                normalized("call-fail"),
                normalized("call-slow-1"),
                normalized("call-slow-2"),
            ],
            run_id="run-cancel",
        )
    )

    assert batch.successful is False

    audit = runtime.latest_batch_audit()

    assert audit is not None
    assert audit.cancellation_requested is True
    assert audit.failed_count == 1
    assert audit.cancelled_count == 2
    assert "call-fail" in started

    statuses = {
        item.call_id: item.status
        for item in audit.calls
    }

    assert statuses["call-fail"] is (
        ToolBatchCallStatus.FAILED
    )
    assert statuses["call-slow-1"] is (
        ToolBatchCallStatus.CANCELLED
    )
    assert statuses["call-slow-2"] is (
        ToolBatchCallStatus.CANCELLED
    )


def test_post_execution_budget_violation_is_audited() -> None:
    attempts = 0

    async def handler(
        call: ExternalToolCall,
    ) -> ExternalToolResult:
        nonlocal attempts
        attempts += 1

        if attempts == 1:
            return ExternalToolResult(
                call_id=call.call_id,
                tool_id=call.tool_id,
                status=ToolExecutionStatus.FAILED,
                is_error=True,
                error="retry me",
            )

        return ExternalToolResult(
            call_id=call.call_id,
            tool_id=call.tool_id,
            status=ToolExecutionStatus.SUCCEEDED,
        )

    resilience = ToolCallResilienceExecutor(
        ToolCallResiliencePolicy(
            timeout_seconds=1,
            retry=RetryPolicy(
                maximum_attempts=2,
                base_delay_seconds=0,
            ),
            retry_failed_results=True,
        )
    )

    runtime = ToolCallRuntime(
        registry=registry_with_handler(handler),
        resilience_executor=resilience,
        budget_governor=budget_governor(
            "0.007"
        ),
        batch_governor=ToolBatchGovernor(
            ToolBatchGovernancePolicy(
                mark_post_budget_violation=True,
            )
        ),
    )

    batch = asyncio.run(
        runtime.execute_many(
            [
                normalized("call-budget"),
            ],
            run_id="run-budget",
        )
    )

    assert len(batch.records) == 1
    assert batch.records[0].successful is True
    assert attempts == 2

    budget = runtime.budget_result(
        "call-budget"
    )

    assert budget is not None
    assert budget.allowed is False

    audit = runtime.latest_batch_audit()

    assert audit is not None
    assert audit.failed_count == 1
    assert audit.succeeded_count == 0
    assert (
        audit.calls[0].status
        is ToolBatchCallStatus.POST_BUDGET_VIOLATION
    )
    assert audit.status is ToolBatchStatus.FAILED


def test_blocked_budget_is_not_post_execution_violation() -> None:
    calls = 0

    async def handler(
        call: ExternalToolCall,
    ) -> ExternalToolResult:
        nonlocal calls
        calls += 1

        return ExternalToolResult(
            call_id=call.call_id,
            tool_id=call.tool_id,
            status=ToolExecutionStatus.SUCCEEDED,
        )

    runtime = ToolCallRuntime(
        registry=registry_with_handler(handler),
        budget_governor=budget_governor(
            "0.004"
        ),
        batch_governor=ToolBatchGovernor(),
    )

    batch = asyncio.run(
        runtime.execute_many(
            [
                normalized("call-blocked"),
            ]
        )
    )

    assert batch.successful is False
    assert calls == 0

    audit = runtime.latest_batch_audit()

    assert audit is not None
    assert (
        audit.calls[0].status
        is ToolBatchCallStatus.BLOCKED
    )
    assert audit.status is ToolBatchStatus.BLOCKED


def test_batch_audits_returns_copy() -> None:
    async def handler(
        call: ExternalToolCall,
    ) -> ExternalToolResult:
        return ExternalToolResult(
            call_id=call.call_id,
            tool_id=call.tool_id,
            status=ToolExecutionStatus.SUCCEEDED,
        )

    runtime = ToolCallRuntime(
        registry=registry_with_handler(handler),
        batch_governor=ToolBatchGovernor(),
    )

    asyncio.run(
        runtime.execute_many(
            [
                normalized("call-1"),
            ]
        )
    )

    audits = runtime.batch_audits()
    audits.clear()

    assert runtime.latest_batch_audit() is not None
