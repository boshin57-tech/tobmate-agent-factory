import asyncio
import json

import pytest

from af_core.runtime.tool_call_models import (
    NormalizedToolCall,
)
from af_core.runtime.tool_call_runtime import (
    ToolCallRuntime,
    ToolCallRuntimeError,
    ToolCallRuntimePolicy,
    ToolNameMapping,
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
from af_core.tools.policy import ExternalToolPolicy
from af_core.tools.registry import ExternalToolRegistry


def descriptor(
    *,
    tool_id: str,
    name: str,
    risk: ExternalToolRisk = ExternalToolRisk.READ_ONLY,
) -> ExternalToolDescriptor:
    return ExternalToolDescriptor(
        tool_id=tool_id,
        name=name,
        description=f"Tool {name}",
        input_schema={
            "type": "object",
            "properties": {
                "value": {
                    "type": "integer",
                },
                "message": {
                    "type": "string",
                },
            },
            "additionalProperties": False,
        },
        risk=risk,
        tags={"runtime-test"},
    )


async def success_handler(
    call: ExternalToolCall,
) -> ExternalToolResult:
    return ExternalToolResult(
        call_id=call.call_id,
        tool_id=call.tool_id,
        status=ToolExecutionStatus.SUCCEEDED,
        content=[
            ToolContent(
                type=ToolContentType.JSON,
                json_value={
                    "tool_id": call.tool_id,
                    "arguments": call.arguments,
                },
            )
        ],
    )


async def failing_handler(
    call: ExternalToolCall,
) -> ExternalToolResult:
    return ExternalToolResult(
        call_id=call.call_id,
        tool_id=call.tool_id,
        status=ToolExecutionStatus.FAILED,
        is_error=True,
        error=f"failed:{call.tool_id}",
    )


def normalized(
    *,
    call_id: str,
    name: str,
    arguments=None,
) -> NormalizedToolCall:
    return NormalizedToolCall(
        call_id=call_id,
        tool_name=name,
        arguments=arguments or {},
    )


def test_explicit_mapping_resolves_external_tool() -> None:
    registry = ExternalToolRegistry()
    registry.register(
        descriptor=descriptor(
            tool_id="mcp:filesystem:read_file",
            name="read_file",
        ),
        handler=success_handler,
    )

    runtime = ToolCallRuntime(
        registry=registry,
        mappings=[
            ToolNameMapping(
                provider_tool_name="read_file",
                external_tool_id=(
                    "mcp:filesystem:read_file"
                ),
            )
        ],
    )

    record = asyncio.run(
        runtime.execute_one(
            normalized(
                call_id="call-1",
                name="read_file",
                arguments={
                    "message": "hello",
                },
            ),
            project_id="project-1",
            run_id="run-1",
            task_id="task-1",
            agent_name="agent-1",
        )
    )

    assert record.successful is True
    assert record.external_call.tool_id == (
        "mcp:filesystem:read_file"
    )
    assert record.external_call.project_id == "project-1"
    assert record.external_call.run_id == "run-1"
    assert record.external_call.task_id == "task-1"
    assert record.external_call.agent_name == "agent-1"


def test_unique_descriptor_name_resolves_without_mapping() -> None:
    registry = ExternalToolRegistry()
    registry.register(
        descriptor=descriptor(
            tool_id="tool.echo",
            name="echo",
        ),
        handler=success_handler,
    )

    runtime = ToolCallRuntime(
        registry=registry
    )

    assert runtime.resolve_tool_id("echo") == (
        "tool.echo"
    )


def test_ambiguous_tool_name_requires_mapping() -> None:
    registry = ExternalToolRegistry()

    for tool_id in (
        "mcp:first:search",
        "mcp:second:search",
    ):
        registry.register(
            descriptor=descriptor(
                tool_id=tool_id,
                name="search",
            ),
            handler=success_handler,
        )

    runtime = ToolCallRuntime(
        registry=registry
    )

    with pytest.raises(
        ToolCallRuntimeError,
        match="Multiple external tools",
    ):
        runtime.resolve_tool_id("search")


def test_missing_tool_is_rejected() -> None:
    runtime = ToolCallRuntime(
        registry=ExternalToolRegistry()
    )

    with pytest.raises(
        ToolCallRuntimeError,
        match="No external tool",
    ):
        runtime.resolve_tool_id("missing")


def test_mapping_conflict_is_rejected() -> None:
    runtime = ToolCallRuntime(
        registry=ExternalToolRegistry(),
        mappings=[
            ToolNameMapping(
                provider_tool_name="search",
                external_tool_id="tool.one",
            )
        ],
    )

    with pytest.raises(
        ToolCallRuntimeError,
        match="already mapped",
    ):
        runtime.add_mapping(
            ToolNameMapping(
                provider_tool_name="search",
                external_tool_id="tool.two",
            )
        )


def test_approval_resolver_allows_external_write() -> None:
    registry = ExternalToolRegistry(
        policy=ExternalToolPolicy(
            maximum_risk=ExternalToolRisk.EXTERNAL_WRITE,
        )
    )
    registry.register(
        descriptor=descriptor(
            tool_id="tool.publish",
            name="publish",
            risk=ExternalToolRisk.EXTERNAL_WRITE,
        ),
        handler=success_handler,
    )

    approvals = []

    async def approve(call, tool_id):
        approvals.append(
            (call.call_id, tool_id)
        )
        return True

    runtime = ToolCallRuntime(
        registry=registry,
        approval_resolver=approve,
    )

    record = asyncio.run(
        runtime.execute_one(
            normalized(
                call_id="call-approval",
                name="publish",
            )
        )
    )

    assert record.successful is True
    assert record.approved is True
    assert approvals == [
        (
            "call-approval",
            "tool.publish",
        )
    ]


def test_no_approval_blocks_external_write() -> None:
    registry = ExternalToolRegistry(
        policy=ExternalToolPolicy(
            maximum_risk=ExternalToolRisk.EXTERNAL_WRITE,
        )
    )
    registry.register(
        descriptor=descriptor(
            tool_id="tool.publish",
            name="publish",
            risk=ExternalToolRisk.EXTERNAL_WRITE,
        ),
        handler=success_handler,
    )

    runtime = ToolCallRuntime(
        registry=registry
    )

    record = asyncio.run(
        runtime.execute_one(
            normalized(
                call_id="call-blocked",
                name="publish",
            )
        )
    )

    assert record.successful is False
    assert (
        record.result.status
        is ToolExecutionStatus.BLOCKED
    )


def test_sequential_execution_preserves_order() -> None:
    registry = ExternalToolRegistry()
    calls_seen = []

    async def ordered_handler(
        call: ExternalToolCall,
    ) -> ExternalToolResult:
        calls_seen.append(call.call_id)

        return await success_handler(call)

    registry.register(
        descriptor=descriptor(
            tool_id="tool.echo",
            name="echo",
        ),
        handler=ordered_handler,
    )

    runtime = ToolCallRuntime(
        registry=registry,
        policy=ToolCallRuntimePolicy(
            allow_parallel_execution=False,
        ),
    )

    batch = asyncio.run(
        runtime.execute_many(
            [
                normalized(
                    call_id="call-1",
                    name="echo",
                ),
                normalized(
                    call_id="call-2",
                    name="echo",
                ),
                normalized(
                    call_id="call-3",
                    name="echo",
                ),
            ]
        )
    )

    assert batch.successful is True
    assert calls_seen == [
        "call-1",
        "call-2",
        "call-3",
    ]
    assert [
        record.call.call_id
        for record in batch.records
    ] == calls_seen


def test_parallel_execution_honors_maximum_parallelism() -> None:
    registry = ExternalToolRegistry()
    active = 0
    maximum_active = 0

    async def parallel_handler(
        call: ExternalToolCall,
    ) -> ExternalToolResult:
        nonlocal active
        nonlocal maximum_active

        active += 1
        maximum_active = max(
            maximum_active,
            active,
        )

        await asyncio.sleep(0.03)

        active -= 1
        return await success_handler(call)

    registry.register(
        descriptor=descriptor(
            tool_id="tool.parallel",
            name="parallel",
        ),
        handler=parallel_handler,
    )

    runtime = ToolCallRuntime(
        registry=registry,
        policy=ToolCallRuntimePolicy(
            maximum_parallelism=2,
            allow_parallel_execution=True,
        ),
    )

    batch = asyncio.run(
        runtime.execute_many(
            [
                normalized(
                    call_id=f"call-{index}",
                    name="parallel",
                )
                for index in range(5)
            ]
        )
    )

    assert batch.successful is True
    assert len(batch.records) == 5
    assert maximum_active == 2


def test_sequential_stop_on_failure_stops_remaining_calls() -> None:
    registry = ExternalToolRegistry()
    calls_seen = []

    async def mixed_handler(
        call: ExternalToolCall,
    ) -> ExternalToolResult:
        calls_seen.append(call.call_id)

        if call.call_id == "call-2":
            return await failing_handler(call)

        return await success_handler(call)

    registry.register(
        descriptor=descriptor(
            tool_id="tool.mixed",
            name="mixed",
        ),
        handler=mixed_handler,
    )

    runtime = ToolCallRuntime(
        registry=registry,
        policy=ToolCallRuntimePolicy(
            allow_parallel_execution=False,
            stop_on_failure=True,
        ),
    )

    batch = asyncio.run(
        runtime.execute_many(
            [
                normalized(
                    call_id="call-1",
                    name="mixed",
                ),
                normalized(
                    call_id="call-2",
                    name="mixed",
                ),
                normalized(
                    call_id="call-3",
                    name="mixed",
                ),
            ]
        )
    )

    assert batch.successful is False
    assert batch.failed_call_ids == [
        "call-2",
    ]
    assert calls_seen == [
        "call-1",
        "call-2",
    ]
    assert len(batch.records) == 2


def test_result_messages_are_generated_for_batch() -> None:
    registry = ExternalToolRegistry()
    registry.register(
        descriptor=descriptor(
            tool_id="tool.echo",
            name="echo",
        ),
        handler=success_handler,
    )

    runtime = ToolCallRuntime(
        registry=registry
    )

    batch = asyncio.run(
        runtime.execute_many(
            [
                normalized(
                    call_id="call-1",
                    name="echo",
                    arguments={
                        "message": "hello",
                    },
                )
            ]
        )
    )

    messages = runtime.result_messages(batch)

    assert len(messages) == 1
    assert messages[0].role == "tool"
    assert messages[0].call_id == "call-1"

    payload = json.loads(
        messages[0].content
    )

    assert payload["status"] == "SUCCEEDED"
    assert payload["json"]["tool_id"] == (
        "tool.echo"
    )
    assert payload["json"]["arguments"] == {
        "message": "hello",
    }


def test_empty_batch_is_successful() -> None:
    runtime = ToolCallRuntime(
        registry=ExternalToolRegistry()
    )

    batch = asyncio.run(
        runtime.execute_many([])
    )

    assert batch.successful is True
    assert batch.records == []
    assert batch.failed_call_ids == []
