from __future__ import annotations

import asyncio
from decimal import Decimal

from af_core.orchestrator.retry import RetryPolicy
from af_core.runtime.budget import (
    BudgetDecision,
    BudgetLimit,
    BudgetPolicy,
    BudgetScope,
)
from af_core.runtime.provider_protocol import (
    NormalizedTokenUsage,
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


def descriptor() -> ExternalToolDescriptor:
    return ExternalToolDescriptor(
        tool_id="tool.budgeted",
        name="budgeted",
        description="Budget test tool",
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        risk=ExternalToolRisk.READ_ONLY,
    )


def normalized(
    call_id: str = "call-1",
) -> NormalizedToolCall:
    return NormalizedToolCall(
        call_id=call_id,
        tool_name="budgeted",
        arguments={},
    )


def estimator(
    call: ExternalToolCall,
    tool: ExternalToolDescriptor,
    attempts: int,
) -> UsageRecord:
    del call, tool

    return UsageRecord.model_construct(
        provider_id="tool-runtime",
        model_id="external-tool",
        usage=NormalizedTokenUsage(
            input_tokens=10 * attempts,
            output_tokens=5 * attempts,
        ),
        cost=CostBreakdown(
            input_cost_usd=(
                Decimal("0.002")
                * attempts
            ),
            output_cost_usd=(
                Decimal("0.003")
                * attempts
            ),
            total_cost_usd=(
                Decimal("0.005")
                * attempts
            ),
        ),
    )


def governor(
    *,
    maximum_cost: str,
    warning_ratio: str = "0.80",
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
                    warning_ratio=Decimal(
                        warning_ratio
                    ),
                )
            ]
        ),
        estimator=estimator,
    )


async def success_handler(
    call: ExternalToolCall,
) -> ExternalToolResult:
    return ExternalToolResult(
        call_id=call.call_id,
        tool_id=call.tool_id,
        status=ToolExecutionStatus.SUCCEEDED,
    )


def registry_with_handler(
    handler=success_handler,
) -> ExternalToolRegistry:
    registry = ExternalToolRegistry()

    registry.register(
        descriptor=descriptor(),
        handler=handler,
    )

    return registry


def test_budget_allow_executes_and_commits_usage() -> None:
    budget = governor(
        maximum_cost="1.00"
    )

    runtime = ToolCallRuntime(
        registry=registry_with_handler(),
        budget_governor=budget,
    )

    record = asyncio.run(
        runtime.execute_one(
            normalized(),
            run_id="run-1",
        )
    )

    assert record.successful is True

    evaluation = runtime.budget_result(
        "call-1"
    )

    assert evaluation is not None
    assert evaluation.allowed is True
    assert evaluation.warning is False
    assert (
        evaluation.evaluations[0].decision
        is BudgetDecision.ALLOW
    )

    assert (
        budget.current_usage().total_cost_usd
        == Decimal("0.005")
    )

    audit = budget.latest("call-1")

    assert audit is not None
    assert audit.committed is True
    assert audit.actual is not None
    assert (
        audit.actual.cost.total_cost_usd
        == Decimal("0.005")
    )

    assert (
        record.result.metadata["budget"]
        ["committed_usage"]["cost"]
        ["total_cost_usd"]
        == "0.005"
    )


def test_budget_warning_executes_and_commits() -> None:
    budget = governor(
        maximum_cost="0.006",
        warning_ratio="0.80",
    )

    runtime = ToolCallRuntime(
        registry=registry_with_handler(),
        budget_governor=budget,
    )

    record = asyncio.run(
        runtime.execute_one(
            normalized(),
        )
    )

    assert record.successful is True

    evaluation = runtime.budget_result(
        "call-1"
    )

    assert evaluation is not None
    assert evaluation.allowed is True
    assert evaluation.warning is True
    assert (
        evaluation.evaluations[0].decision
        is BudgetDecision.WARN
    )
    assert budget.current_usage().request_count == 1


def test_budget_block_prevents_tool_execution() -> None:
    calls = 0

    async def handler(
        call: ExternalToolCall,
    ) -> ExternalToolResult:
        nonlocal calls
        calls += 1

        return await success_handler(call)

    budget = governor(
        maximum_cost="0.004"
    )

    runtime = ToolCallRuntime(
        registry=registry_with_handler(handler),
        budget_governor=budget,
    )

    record = asyncio.run(
        runtime.execute_one(
            normalized(),
        )
    )

    assert record.successful is False
    assert (
        record.result.status
        is ToolExecutionStatus.BLOCKED
    )
    assert calls == 0

    evaluation = runtime.budget_result(
        "call-1"
    )

    assert evaluation is not None
    assert evaluation.allowed is False
    assert (
        evaluation.evaluations[0].decision
        is BudgetDecision.BLOCK
    )

    assert budget.current_usage().request_count == 0

    audit = budget.latest("call-1")

    assert audit is not None
    assert audit.committed is False


def test_multiple_calls_accumulate_usage() -> None:
    budget = governor(
        maximum_cost="1.00"
    )

    runtime = ToolCallRuntime(
        registry=registry_with_handler(),
        budget_governor=budget,
    )

    first = asyncio.run(
        runtime.execute_one(
            normalized("call-1"),
        )
    )
    second = asyncio.run(
        runtime.execute_one(
            normalized("call-2"),
        )
    )

    assert first.successful is True
    assert second.successful is True

    summary = budget.current_usage()

    assert summary.request_count == 2
    assert summary.input_tokens == 20
    assert summary.output_tokens == 10
    assert summary.total_tokens == 30
    assert (
        summary.total_cost_usd
        == Decimal("0.010")
    )


def test_retry_attempt_count_is_reflected_in_budget() -> None:
    attempts = 0

    async def transient_handler(
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
                error="temporary failure",
            )

        return await success_handler(call)

    budget = governor(
        maximum_cost="1.00"
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
        registry=registry_with_handler(
            transient_handler
        ),
        resilience_executor=resilience,
        budget_governor=budget,
    )

    record = asyncio.run(
        runtime.execute_one(
            normalized(),
        )
    )

    assert record.successful is True
    assert attempts == 2

    evaluation = runtime.budget_result(
        "call-1"
    )

    assert evaluation is not None
    assert (
        evaluation.projected.cost.total_cost_usd
        == Decimal("0.010")
    )
    assert evaluation.projected.usage.input_tokens == 20
    assert evaluation.projected.usage.output_tokens == 10

    summary = budget.current_usage()

    assert summary.request_count == 1
    assert summary.input_tokens == 20
    assert summary.output_tokens == 10
    assert (
        summary.total_cost_usd
        == Decimal("0.010")
    )


def test_retry_cost_can_exceed_budget_after_execution() -> None:
    attempts = 0

    async def transient_handler(
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
                error="temporary failure",
            )

        return await success_handler(call)

    budget = governor(
        maximum_cost="0.007"
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
        registry=registry_with_handler(
            transient_handler
        ),
        resilience_executor=resilience,
        budget_governor=budget,
    )

    record = asyncio.run(
        runtime.execute_one(
            normalized(),
        )
    )

    assert record.successful is True
    assert attempts == 2

    evaluation = runtime.budget_result(
        "call-1"
    )

    assert evaluation is not None
    assert evaluation.allowed is False
    assert (
        evaluation.evaluations[0].decision
        is BudgetDecision.BLOCK
    )

    assert budget.current_usage().request_count == 0

    audit = budget.latest("call-1")

    assert audit is not None
    assert audit.committed is False


def test_budget_results_returns_copy() -> None:
    runtime = ToolCallRuntime(
        registry=registry_with_handler(),
        budget_governor=governor(
            maximum_cost="1.00"
        ),
    )

    asyncio.run(
        runtime.execute_one(
            normalized(),
        )
    )

    results = runtime.budget_results()
    results.clear()

    assert runtime.budget_result(
        "call-1"
    ) is not None
