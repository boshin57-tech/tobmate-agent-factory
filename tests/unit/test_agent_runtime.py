import pytest

from af_core.runtime.agent import (
    AgentAction,
    AgentExecutionState,
    AgentRole,
    AgentStatus,
    ToolCall,
)


def test_agent_state_lifecycle() -> None:
    state = AgentExecutionState(
        agent_name="implementer-1",
        role=AgentRole.IMPLEMENTER,
    )

    state.begin()

    call = ToolCall(
        tool_name="read_file",
        arguments={"path": "app.py"},
        reason="Inspect implementation target",
    )

    state.record_tool_call(call)
    state.complete("Implementation inspected")

    assert state.status is AgentStatus.COMPLETED
    assert state.step == 1
    assert state.tool_calls == [call]
    assert state.summaries == ["Implementation inspected"]


def test_agent_cannot_record_tool_call_before_start() -> None:
    state = AgentExecutionState(
        agent_name="tester-1",
        role=AgentRole.TESTER,
    )

    with pytest.raises(ValueError):
        state.record_tool_call(
            ToolCall(
                tool_name="run_tests",
                reason="Run tests",
            )
        )


def test_agent_action_contracts() -> None:
    complete = AgentAction(
        action_type="complete",
        summary="Task complete",
    )

    tool_action = AgentAction(
        action_type="tool_call",
        tool_call=ToolCall(
            tool_name="git_diff",
            reason="Review changes",
        ),
    )

    assert complete.summary == "Task complete"
    assert tool_action.tool_call is not None

    with pytest.raises(ValueError):
        AgentAction(action_type="complete")

    with pytest.raises(ValueError):
        AgentAction(
            action_type="fail",
            summary="wrong field",
        )
