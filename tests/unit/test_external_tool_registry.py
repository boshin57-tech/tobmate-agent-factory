import asyncio

import pytest

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
from af_core.tools.registry import (
    ExternalToolRegistry,
    ExternalToolRegistryError,
)


def descriptor(
    *,
    tool_id: str = "tool.echo",
    timeout_seconds: float = 1.0,
    risk: ExternalToolRisk = ExternalToolRisk.READ_ONLY,
) -> ExternalToolDescriptor:
    return ExternalToolDescriptor(
        tool_id=tool_id,
        name="Echo",
        description="Echo a message",
        input_schema={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                },
                "count": {
                    "type": "integer",
                },
            },
            "required": ["message"],
            "additionalProperties": False,
        },
        risk=risk,
        timeout_seconds=timeout_seconds,
        tags={"test", "echo"},
    )


def call(
    *,
    tool_id: str = "tool.echo",
    arguments=None,
) -> ExternalToolCall:
    resolved_arguments = (
        {
            "message": "hello",
        }
        if arguments is None
        else arguments
    )

    return ExternalToolCall(
        call_id="call-1",
        tool_id=tool_id,
        arguments=resolved_arguments,
        project_id="project-1",
        run_id="run-1",
        task_id="task-1",
        agent_name="agent-1",
    )


async def successful_handler(
    item: ExternalToolCall,
) -> ExternalToolResult:
    return ExternalToolResult(
        call_id=item.call_id,
        tool_id=item.tool_id,
        status=ToolExecutionStatus.SUCCEEDED,
        content=[
            ToolContent(
                type=ToolContentType.TEXT,
                text=item.arguments["message"],
            )
        ],
    )


def test_register_list_and_unregister() -> None:
    registry = ExternalToolRegistry()
    registry.register(
        descriptor=descriptor(),
        handler=successful_handler,
    )

    assert registry.get("tool.echo").name == "Echo"
    assert len(registry.list()) == 1
    assert len(registry.list(tags={"echo"})) == 1
    assert registry.list(tags={"missing"}) == []

    with pytest.raises(
        ExternalToolRegistryError,
        match="already registered",
    ):
        registry.register(
            descriptor=descriptor(),
            handler=successful_handler,
        )

    registry.unregister("tool.echo")

    with pytest.raises(
        ExternalToolRegistryError,
        match="Unknown external tool",
    ):
        registry.get("tool.echo")


def test_execute_and_audit_success() -> None:
    registry = ExternalToolRegistry()
    registry.register(
        descriptor=descriptor(),
        handler=successful_handler,
    )

    result = asyncio.run(
        registry.execute(call())
    )

    assert result.status is ToolExecutionStatus.SUCCEEDED
    assert result.content[0].text == "hello"
    assert result.duration_ms >= 0

    audit = registry.audit_records()

    assert len(audit) == 1
    assert audit[0].call.call_id == "call-1"
    assert (
        audit[0].result.status
        is ToolExecutionStatus.SUCCEEDED
    )


@pytest.mark.parametrize(
    ("arguments", "fragment"),
    [
        (
            {},
            "Missing required",
        ),
        (
            {
                "message": 123,
            },
            "must be string",
        ),
        (
            {
                "message": "hello",
                "unknown": True,
            },
            "Unknown tool arguments",
        ),
    ],
)
def test_argument_validation(
    arguments,
    fragment: str,
) -> None:
    registry = ExternalToolRegistry()
    registry.register(
        descriptor=descriptor(),
        handler=successful_handler,
    )

    result = asyncio.run(
        registry.execute(
            call(arguments=arguments)
        )
    )

    assert result.status is ToolExecutionStatus.FAILED
    assert fragment in (result.error or "")


def test_policy_block_and_approval() -> None:
    denied_registry = ExternalToolRegistry(
        policy=ExternalToolPolicy(
            denied_tool_ids={"tool.echo"},
        )
    )
    denied_registry.register(
        descriptor=descriptor(),
        handler=successful_handler,
    )

    blocked = asyncio.run(
        denied_registry.execute(call())
    )

    assert blocked.status is ToolExecutionStatus.BLOCKED

    approval_registry = ExternalToolRegistry(
        policy=ExternalToolPolicy(
            maximum_risk=ExternalToolRisk.EXTERNAL_WRITE,
        )
    )
    approval_registry.register(
        descriptor=descriptor(
            risk=ExternalToolRisk.EXTERNAL_WRITE
        ),
        handler=successful_handler,
    )

    without_approval = asyncio.run(
        approval_registry.execute(call())
    )
    with_approval = asyncio.run(
        approval_registry.execute(
            call(),
            approved=True,
        )
    )

    assert (
        without_approval.status
        is ToolExecutionStatus.BLOCKED
    )
    assert (
        with_approval.status
        is ToolExecutionStatus.SUCCEEDED
    )


def test_handler_exception_and_timeout() -> None:
    async def failing_handler(
        item: ExternalToolCall,
    ) -> ExternalToolResult:
        raise RuntimeError(
            f"failed:{item.tool_id}"
        )

    failing_registry = ExternalToolRegistry()
    failing_registry.register(
        descriptor=descriptor(),
        handler=failing_handler,
    )

    failed = asyncio.run(
        failing_registry.execute(call())
    )

    assert failed.status is ToolExecutionStatus.FAILED
    assert failed.error == "failed:tool.echo"

    async def slow_handler(
        item: ExternalToolCall,
    ) -> ExternalToolResult:
        await asyncio.sleep(0.05)

        return ExternalToolResult(
            call_id=item.call_id,
            tool_id=item.tool_id,
            status=ToolExecutionStatus.SUCCEEDED,
        )

    slow_registry = ExternalToolRegistry()
    slow_registry.register(
        descriptor=descriptor(
            timeout_seconds=0.01,
        ),
        handler=slow_handler,
    )

    timed_out = asyncio.run(
        slow_registry.execute(call())
    )

    assert (
        timed_out.status
        is ToolExecutionStatus.TIMED_OUT
    )


def test_audit_records_returns_copy() -> None:
    registry = ExternalToolRegistry()
    registry.register(
        descriptor=descriptor(),
        handler=successful_handler,
    )

    asyncio.run(
        registry.execute(call())
    )

    returned = registry.audit_records()
    returned.clear()

    assert len(registry.audit_records()) == 1
