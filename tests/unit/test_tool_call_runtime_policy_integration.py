from __future__ import annotations

import asyncio

from af_core.runtime.runtime_policy_engine import (
    RuntimePolicyEngine,
)
from af_core.runtime.runtime_policy_models import (
    RuntimePolicy,
    RuntimePolicyDecision,
    RuntimePolicyRule,
)
from af_core.runtime.runtime_policy_registry import (
    RuntimePolicyRegistry,
)
from af_core.runtime.tool_call_models import (
    NormalizedToolCall,
)
from af_core.runtime.tool_call_runtime import ToolCallRuntime
from af_core.tools.models import (
    ExternalToolResult,
    ToolExecutionStatus,
)


class FakeRegistry:
    def __init__(self) -> None:
        self.execution_count = 0

    def get(self, tool_id: str) -> object:
        if tool_id != "tool.echo":
            raise KeyError(tool_id)
        return object()

    def list(self) -> list[object]:
        return []

    async def execute(
        self,
        call,
        *,
        approved: bool = False,
    ) -> ExternalToolResult:
        self.execution_count += 1
        return ExternalToolResult(
            call_id=call.call_id,
            tool_id=call.tool_id,
            status=ToolExecutionStatus.SUCCEEDED,
            is_error=False,
        )


def policy_engine(
    decision: RuntimePolicyDecision,
) -> RuntimePolicyEngine:
    registry = RuntimePolicyRegistry()
    registry.register(
        RuntimePolicy(
            policy_id="runtime.integration",
            name="Runtime integration policy",
            rules=(
                RuntimePolicyRule(
                    rule_id=f"rule.{decision.value}",
                    policy_id="runtime.integration",
                    name=decision.value,
                    decision=decision,
                    resources=frozenset({"tool.echo"}),
                    reason=f"Policy decision: {decision.value}",
                ),
            ),
        )
    )
    return RuntimePolicyEngine(registry=registry)


def call() -> NormalizedToolCall:
    return NormalizedToolCall(
        call_id="call-policy-1",
        tool_name="tool.echo",
        arguments={"message": "hello"},
    )


def test_runtime_policy_allows_tool_execution() -> None:
    registry = FakeRegistry()
    engine = policy_engine(RuntimePolicyDecision.ALLOW)

    runtime = ToolCallRuntime(
        registry=registry,
        runtime_policy_engine=engine,
    )

    record = asyncio.run(runtime.execute_one(call()))

    assert record.result.status is (
        ToolExecutionStatus.SUCCEEDED
    )
    assert registry.execution_count == 1
    assert len(engine.history.list_records()) == 1


def test_runtime_policy_denies_before_tool_execution() -> None:
    registry = FakeRegistry()
    engine = policy_engine(RuntimePolicyDecision.DENY)

    runtime = ToolCallRuntime(
        registry=registry,
        runtime_policy_engine=engine,
    )

    record = asyncio.run(runtime.execute_one(call()))

    assert record.result.status is ToolExecutionStatus.BLOCKED
    assert record.result.is_error is True
    assert registry.execution_count == 0
    assert record.result.metadata["runtime_policy"][
        "decision"
    ] == "deny"


def test_runtime_policy_uses_existing_approval_resolver() -> None:
    registry = FakeRegistry()
    engine = policy_engine(
        RuntimePolicyDecision.REQUIRE_APPROVAL
    )

    runtime = ToolCallRuntime(
        registry=registry,
        runtime_policy_engine=engine,
        approval_resolver=lambda call, tool_id: True,
    )

    record = asyncio.run(runtime.execute_one(call()))

    assert record.result.status is (
        ToolExecutionStatus.SUCCEEDED
    )
    assert record.approved is True
    assert registry.execution_count == 1


def test_missing_approval_blocks_execution() -> None:
    registry = FakeRegistry()
    engine = policy_engine(
        RuntimePolicyDecision.REQUIRE_APPROVAL
    )

    runtime = ToolCallRuntime(
        registry=registry,
        runtime_policy_engine=engine,
    )

    record = asyncio.run(runtime.execute_one(call()))

    assert record.result.status is ToolExecutionStatus.BLOCKED
    assert registry.execution_count == 0
