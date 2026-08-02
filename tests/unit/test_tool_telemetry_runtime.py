from __future__ import annotations

import asyncio

import pytest

from decimal import Decimal

from af_core.orchestrator.retry import RetryPolicy
from af_core.runtime.provider_protocol import (
    NormalizedTokenUsage,
)
from af_core.runtime.tool_call_budget import (
    ToolCallBudgetGovernor,
)
from af_core.runtime.tool_call_resilience import (
    ToolCallResilienceExecutor,
    ToolCallResiliencePolicy,
)
from af_core.runtime.usage import (
    CostBreakdown,
    UsageRecord,
)

from af_core.runtime.tool_call_models import (
    NormalizedToolCall,
)
from af_core.runtime.tool_call_runtime import (
    ToolCallRuntime,
    ToolCallRuntimeError,
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
from af_core.tools.tool_telemetry import (
    InMemoryToolTelemetryStream,
    ToolTelemetryCollector,
    ToolTelemetryEventType,
    ToolTelemetryFilter,
)

from decimal import Decimal

from af_core.runtime.tool_call_budget import (
    ToolCallBudgetGovernor,
)
from af_core.runtime.tool_call_resilience import (
    ToolCallResilienceExecutor,
    ToolCallResiliencePolicy,
)
from af_core.runtime.budget import (
    BudgetLimit,
    BudgetPolicy,
    BudgetScope,
)



async def success_handler(
    call: ExternalToolCall,
) -> ExternalToolResult:
    return ExternalToolResult(
        call_id=call.call_id,
        tool_id=call.tool_id,
        status=ToolExecutionStatus.SUCCEEDED,
        metadata={
            "echo": call.arguments,
        },
    )


async def failure_handler(
    call: ExternalToolCall,
) -> ExternalToolResult:
    return ExternalToolResult(
        call_id=call.call_id,
        tool_id=call.tool_id,
        status=ToolExecutionStatus.FAILED,
        is_error=True,
        error="simulated Tool failure",
    )


def descriptor(
    *,
    tool_id: str,
    name: str,
) -> ExternalToolDescriptor:
    return ExternalToolDescriptor(
        tool_id=tool_id,
        name=name,
        description=name,
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        },
        risk=ExternalToolRisk.READ_ONLY,
    )


def runtime_with_telemetry(
    *,
    use_failure_handler: bool = False,
):
    registry = ExternalToolRegistry()

    registry.register(
        descriptor=descriptor(
            tool_id="tool.echo",
            name="echo",
        ),
        handler=(
            failure_handler
            if use_failure_handler
            else success_handler
        ),
    )

    stream = InMemoryToolTelemetryStream()
    collector = ToolTelemetryCollector(
        stream=stream,
        event_prefix="runtime-event",
    )

    runtime = ToolCallRuntime(
        registry=registry,
        telemetry_collector=collector,
    )

    return registry, stream, collector, runtime


def normalized_call(
    *,
    call_id: str = "call-1",
    tool_name: str = "echo",
) -> NormalizedToolCall:
    return NormalizedToolCall(
        call_id=call_id,
        tool_name=tool_name,
        arguments={
            "message": "hello",
        },
    )


def event_types(
    stream: InMemoryToolTelemetryStream,
) -> list[ToolTelemetryEventType]:
    return [
        event.event_type
        for event in stream.list_events()
    ]


def test_successful_call_emits_requested_started_succeeded() -> None:
    (
        registry,
        stream,
        collector,
        runtime,
    ) = runtime_with_telemetry()

    del registry, collector

    record = asyncio.run(
        runtime.execute_one(
            normalized_call(),
            project_id="project-1",
            run_id="run-1",
            task_id="task-1",
            agent_name="agent-reviewer",
        )
    )

    assert record.successful is True

    assert event_types(stream) == [
        ToolTelemetryEventType.CALL_REQUESTED,
        ToolTelemetryEventType.CALL_STARTED,
        ToolTelemetryEventType.CALL_SUCCEEDED,
    ]

    succeeded = stream.latest(
        ToolTelemetryFilter(
            event_types={
                ToolTelemetryEventType
                .CALL_SUCCEEDED
            }
        )
    )

    assert succeeded is not None
    assert succeeded.tool_id == "tool.echo"
    assert succeeded.call_id == "call-1"
    assert succeeded.project_id == "project-1"
    assert succeeded.run_id == "run-1"
    assert succeeded.task_id == "task-1"
    assert succeeded.agent_id == (
        "agent-reviewer"
    )
    assert succeeded.successful is True
    assert succeeded.duration_ms is not None
    assert succeeded.duration_ms >= 0


def test_failed_result_emits_call_failed() -> None:
    (
        registry,
        stream,
        collector,
        runtime,
    ) = runtime_with_telemetry(
        use_failure_handler=True
    )

    del registry, collector

    record = asyncio.run(
        runtime.execute_one(
            normalized_call(
                call_id="call-failed"
            )
        )
    )

    assert record.successful is False
    assert record.result.status is (
        ToolExecutionStatus.FAILED
    )

    assert event_types(stream) == [
        ToolTelemetryEventType.CALL_REQUESTED,
        ToolTelemetryEventType.CALL_STARTED,
        ToolTelemetryEventType.CALL_FAILED,
    ]

    failed = stream.latest()

    assert failed is not None
    assert failed.call_id == "call-failed"
    assert failed.tool_id == "tool.echo"
    assert failed.successful is False
    assert failed.error_message == (
        "simulated Tool failure"
    )
    assert failed.duration_ms is not None


def test_execution_exception_emits_call_failed_and_reraises() -> None:
    async def raising_handler(
        call: ExternalToolCall,
    ) -> ExternalToolResult:
        raise RuntimeError(
            "simulated handler exception"
        )

    registry = ExternalToolRegistry()

    registry.register(
        descriptor=descriptor(
            tool_id="tool.raise",
            name="raise_tool",
        ),
        handler=raising_handler,
    )

    stream = InMemoryToolTelemetryStream()
    collector = ToolTelemetryCollector(
        stream=stream
    )

    runtime = ToolCallRuntime(
        registry=registry,
        telemetry_collector=collector,
    )

    record = asyncio.run(
        runtime.execute_one(
            normalized_call(
                call_id="call-exception",
                tool_name="raise_tool",
            )
        )
    )

    assert record.successful is False
    assert record.result.status is (
        ToolExecutionStatus.FAILED
    )
    assert record.result.error == (
        "simulated handler exception"
    )

    assert event_types(stream) == [
        ToolTelemetryEventType.CALL_REQUESTED,
        ToolTelemetryEventType.CALL_STARTED,
        ToolTelemetryEventType.CALL_FAILED,
    ]

    failed = stream.latest()

    assert failed is not None
    assert failed.call_id == "call-exception"
    assert failed.tool_id == "tool.raise"
    assert failed.successful is False
    assert failed.error_type == "RuntimeError"
    assert failed.error_message == (
        "simulated handler exception"
    )


def test_budget_block_emits_call_blocked() -> None:
    handler_calls = 0

    async def handler(
        call: ExternalToolCall,
    ) -> ExternalToolResult:
        nonlocal handler_calls
        handler_calls += 1

        return ExternalToolResult(
            call_id=call.call_id,
            tool_id=call.tool_id,
            status=ToolExecutionStatus.SUCCEEDED,
        )

    stream = InMemoryToolTelemetryStream()
    collector = ToolTelemetryCollector(
        stream=stream
    )

    runtime = ToolCallRuntime(
        registry=budget_registry(handler),
        budget_governor=budget_governor(
            maximum_cost="0.004"
        ),
        telemetry_collector=collector,
    )

    record = asyncio.run(
        runtime.execute_one(
            budget_call(),
            project_id="project-budget",
            run_id="run-budget",
        )
    )

    assert record.successful is False
    assert record.result.status is (
        ToolExecutionStatus.BLOCKED
    )
    assert handler_calls == 0

    assert event_types(stream) == [
        ToolTelemetryEventType.CALL_REQUESTED,
        ToolTelemetryEventType.CALL_STARTED,
        ToolTelemetryEventType.CALL_BLOCKED,
    ]

    blocked = stream.latest()

    assert blocked is not None
    assert blocked.successful is False
    assert blocked.call_id == "call-1"
    assert blocked.project_id == (
        "project-budget"
    )
    assert blocked.run_id == "run-budget"
    assert blocked.error_message is not None
    assert "projected cost" in (
        blocked.error_message.casefold()
    )
    assert "exceeds maximum" in (
        blocked.error_message.casefold()
    )


def budget_descriptor() -> ExternalToolDescriptor:
    return ExternalToolDescriptor(
        tool_id="tool.budgeted",
        name="budgeted",
        description="Budget telemetry Tool",
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        risk=ExternalToolRisk.READ_ONLY,
    )


def budget_call(
    call_id: str = "call-1",
) -> NormalizedToolCall:
    return NormalizedToolCall(
        call_id=call_id,
        tool_name="budgeted",
        arguments={},
    )


def budget_estimator(
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
                Decimal("0.002") * attempts
            ),
            output_cost_usd=(
                Decimal("0.003") * attempts
            ),
            total_cost_usd=(
                Decimal("0.005") * attempts
            ),
        ),
    )


def budget_governor(
    *,
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
                    warning_ratio=Decimal("0.80"),
                )
            ]
        ),
        estimator=budget_estimator,
    )


def budget_registry(
    handler,
) -> ExternalToolRegistry:
    registry = ExternalToolRegistry()

    registry.register(
        descriptor=budget_descriptor(),
        handler=handler,
    )

    return registry


def resilient_descriptor() -> (
    ExternalToolDescriptor
):
    return ExternalToolDescriptor(
        tool_id="tool.resilient",
        name="resilient",
        description="Resilience telemetry Tool",
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        risk=ExternalToolRisk.READ_ONLY,
        timeout_seconds=2,
    )


def resilient_call(
    call_id: str = "call-1",
) -> NormalizedToolCall:
    return NormalizedToolCall(
        call_id=call_id,
        tool_name="resilient",
        arguments={},
    )


def resilience_executor(
    *,
    timeout_seconds: float = 1,
    maximum_attempts: int = 3,
) -> ToolCallResilienceExecutor:
    return ToolCallResilienceExecutor(
        ToolCallResiliencePolicy(
            timeout_seconds=timeout_seconds,
            retry=RetryPolicy(
                maximum_attempts=maximum_attempts,
                base_delay_seconds=0,
            ),
        )
    )


def test_timeout_exhaustion_emits_timed_out() -> None:
    registry = ExternalToolRegistry()
    attempts = 0

    async def slow_handler(
        call: ExternalToolCall,
    ) -> ExternalToolResult:
        nonlocal attempts
        attempts += 1

        await asyncio.sleep(0.05)

        return ExternalToolResult(
            call_id=call.call_id,
            tool_id=call.tool_id,
            status=ToolExecutionStatus.SUCCEEDED,
        )

    registry.register(
        descriptor=resilient_descriptor(),
        handler=slow_handler,
    )

    stream = InMemoryToolTelemetryStream()
    collector = ToolTelemetryCollector(
        stream=stream
    )

    runtime = ToolCallRuntime(
        registry=registry,
        resilience_executor=(
            resilience_executor(
                timeout_seconds=0.01,
                maximum_attempts=2,
            )
        ),
        telemetry_collector=collector,
    )

    record = asyncio.run(
        runtime.execute_one(
            resilient_call(
                call_id="call-timeout"
            ),
            project_id="project-timeout",
        )
    )

    assert record.successful is False
    assert record.result.status is (
        ToolExecutionStatus.TIMED_OUT
    )
    assert attempts == 2

    assert event_types(stream) == [
        ToolTelemetryEventType.CALL_REQUESTED,
        ToolTelemetryEventType.CALL_STARTED,
        ToolTelemetryEventType.CALL_TIMED_OUT,
    ]

    timed_out = stream.latest()

    assert timed_out is not None
    assert timed_out.call_id == "call-timeout"
    assert timed_out.tool_id == (
        "tool.resilient"
    )
    assert timed_out.successful is False
    assert timed_out.duration_ms is not None
    assert timed_out.duration_ms >= 0
    assert timed_out.retry_count == 1
    assert timed_out.error_message == (
        "Tool Call timed out."
    )


def test_tool_resolution_failure_emits_failed_event() -> None:
    (
        registry,
        stream,
        collector,
        runtime,
    ) = runtime_with_telemetry()

    del registry, collector

    with pytest.raises(
        ToolCallRuntimeError,
        match="No external tool is registered",
    ):
        asyncio.run(
            runtime.execute_one(
                normalized_call(
                    call_id="call-missing",
                    tool_name="missing_tool",
                ),
                project_id="project-resolution",
                run_id="run-resolution",
                task_id="task-resolution",
                agent_name="agent-resolution",
            )
        )

    assert event_types(stream) == [
        ToolTelemetryEventType.CALL_FAILED,
    ]

    failed = stream.latest()

    assert failed is not None
    assert failed.tool_id is None
    assert failed.call_id == "call-missing"
    assert failed.successful is False
    assert failed.error_type == (
        "ToolCallRuntimeError"
    )
    assert failed.project_id == (
        "project-resolution"
    )
    assert failed.run_id == "run-resolution"
    assert failed.task_id == "task-resolution"
    assert failed.agent_id == (
        "agent-resolution"
    )
    assert failed.metadata == {
        "provider_tool_name": "missing_tool",
        "phase": "tool_resolution",
    }


def test_execute_many_collects_events_for_each_call() -> None:
    (
        registry,
        stream,
        collector,
        runtime,
    ) = runtime_with_telemetry()

    del registry, collector

    result = asyncio.run(
        runtime.execute_many(
            [
                normalized_call(
                    call_id="batch-call-1"
                ),
                normalized_call(
                    call_id="batch-call-2"
                ),
            ],
            project_id="project-batch",
            run_id="run-batch",
            task_id="task-batch",
            agent_name="agent-batch",
        )
    )

    assert result.successful is True
    assert len(result.records) == 2

    events = stream.list_events()

    assert len(events) == 6

    events_by_call = {
        call_id: [
            event.event_type
            for event in events
            if event.call_id == call_id
        ]
        for call_id in {
            "batch-call-1",
            "batch-call-2",
        }
    }

    assert events_by_call == {
        "batch-call-1": [
            ToolTelemetryEventType.CALL_REQUESTED,
            ToolTelemetryEventType.CALL_STARTED,
            ToolTelemetryEventType.CALL_SUCCEEDED,
        ],
        "batch-call-2": [
            ToolTelemetryEventType.CALL_REQUESTED,
            ToolTelemetryEventType.CALL_STARTED,
            ToolTelemetryEventType.CALL_SUCCEEDED,
        ],
    }

    succeeded = stream.list_events(
        ToolTelemetryFilter(
            event_types={
                ToolTelemetryEventType
                .CALL_SUCCEEDED
            },
            project_ids={"project-batch"},
            agent_ids={"agent-batch"},
        )
    )

    assert [
        event.call_id
        for event in succeeded
    ] == [
        "batch-call-1",
        "batch-call-2",
    ]

    assert all(
        event.run_id == "run-batch"
        and event.task_id == "task-batch"
        for event in succeeded
    )
