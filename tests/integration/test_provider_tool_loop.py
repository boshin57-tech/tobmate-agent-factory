from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

from af_core.orchestrator.planner import PlannedTask
from af_core.runtime.agent import (
    AgentProfile,
    AgentRole,
)
from af_core.runtime.executor import AgentExecutor
from af_core.runtime.provider_protocol import (
    NormalizedTokenUsage,
    ProviderCapability,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderMessage,
    ProviderResponse,
    ProviderToolCall,
)
from af_core.runtime.tool_call_runtime import (
    ToolCallRuntime,
)
from af_core.runtime.llm_provider import (
    StaticLLMProvider,
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
from af_core.tools.registry import ExternalToolRegistry


def git(
    repo: Path,
    *args: str,
) -> str:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    return result.stdout.rstrip("\r\n")


def create_repo(
    path: Path,
) -> Path:
    path.mkdir()

    git(path, "init")
    git(
        path,
        "config",
        "user.name",
        "AF Test",
    )
    git(
        path,
        "config",
        "user.email",
        "af@example.com",
    )

    (path / "README.md").write_text(
        "AF-Core tool loop test\n",
        encoding="utf-8",
    )

    git(path, "add", ".")
    git(path, "commit", "-m", "initial")

    return path


def profile(
    *,
    maximum_steps: int = 5,
) -> AgentProfile:
    return AgentProfile(
        name="provider-tool-agent",
        role=AgentRole.IMPLEMENTER,
        allowed_tools={
            "read_file",
            "write_file",
            "run_command",
        },
        maximum_steps=maximum_steps,
    )


def task() -> PlannedTask:
    return PlannedTask(
        id="task-provider-tool",
        title="Read external tool value",
        description=(
            "Use the external echo tool and finish."
        ),
        task_type="implementation",
        agent_role="implementer",
        acceptance_criteria=[
            "External tool result returned",
            "Provider resumed after tool call",
        ],
    )


class MockProviderAdapter:
    def __init__(
        self,
        responses: list[ProviderResponse],
    ) -> None:
        self.responses = list(responses)
        self.calls: list[
            list[ProviderMessage]
        ] = []

    @property
    def provider_id(self) -> str:
        return "mock-provider"

    @property
    def capabilities(self):
        return {
            ProviderCapability.TEXT,
            ProviderCapability.TOOL_CALLING,
        }

    async def complete(
        self,
        *,
        messages,
        model_id,
        parameters=None,
    ) -> ProviderResponse:
        del model_id, parameters

        self.calls.append(
            list(messages)
        )

        if not self.responses:
            raise RuntimeError(
                "No mock provider responses remain."
            )

        return self.responses.pop(0)

    async def structured(self, **kwargs):
        raise NotImplementedError

    async def health(self):
        return ProviderHealth(
            provider_id=self.provider_id,
            status=ProviderHealthStatus.HEALTHY,
        )


async def echo_handler(
    call: ExternalToolCall,
) -> ExternalToolResult:
    return ExternalToolResult(
        call_id=call.call_id,
        tool_id=call.tool_id,
        status=ToolExecutionStatus.SUCCEEDED,
        content=[
            ToolContent(
                type=ToolContentType.TEXT,
                text=call.arguments["message"],
            ),
            ToolContent(
                type=ToolContentType.JSON,
                json_value={
                    "echoed": call.arguments["message"],
                },
            ),
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
        error="intentional external failure",
    )


def registry_with_echo() -> ExternalToolRegistry:
    registry = ExternalToolRegistry()

    registry.register(
        descriptor=ExternalToolDescriptor(
            tool_id="tool.echo",
            name="echo",
            description="Echo text",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                    }
                },
                "required": ["message"],
                "additionalProperties": False,
            },
            risk=ExternalToolRisk.READ_ONLY,
        ),
        handler=echo_handler,
    )

    return registry


def test_provider_tool_loop_executes_and_resumes(
    tmp_path: Path,
) -> None:
    repo = create_repo(
        tmp_path / "repo"
    )

    provider = MockProviderAdapter(
        [
            ProviderResponse(
                provider_id="mock-provider",
                model_id="mock-model",
                content=None,
                tool_calls=[
                    ProviderToolCall(
                        call_id="call-echo-1",
                        tool_name="echo",
                        arguments={
                            "message": (
                                "AF-CORE-TOOL-LOOP-OK"
                            ),
                        },
                        provider_format="GENERIC",
                    )
                ],
                usage=NormalizedTokenUsage(
                    input_tokens=10,
                    output_tokens=2,
                ),
            ),
            ProviderResponse(
                provider_id="mock-provider",
                model_id="mock-model",
                content=(
                    "Completed after receiving the "
                    "external tool result."
                ),
                usage=NormalizedTokenUsage(
                    input_tokens=20,
                    output_tokens=8,
                ),
            ),
        ]
    )

    runtime = ToolCallRuntime(
        registry=registry_with_echo()
    )

    executor = AgentExecutor(
        provider=StaticLLMProvider([]),
        profile=profile(),
        workspace_path=repo,
    )

    result = asyncio.run(
        executor.execute_provider_tool_loop(
            task=task(),
            provider_adapter=provider,
            tool_runtime=runtime,
            model_id="mock-model",
            project_id="project-1",
            run_id="run-1",
        )
    )

    assert result.successful is True
    assert result.error is None
    assert result.summary == (
        "Completed after receiving the "
        "external tool result."
    )

    assert len(
        result.provider_tool_records
    ) == 1

    record = result.provider_tool_records[0]

    assert record.successful is True
    assert record.call.call_id == "call-echo-1"
    assert record.call.tool_name == "echo"
    assert record.external_call.tool_id == (
        "tool.echo"
    )
    assert record.external_call.project_id == (
        "project-1"
    )
    assert record.external_call.run_id == "run-1"
    assert record.external_call.task_id == (
        "task-provider-tool"
    )
    assert record.external_call.agent_name == (
        "provider-tool-agent"
    )

    assert len(provider.calls) == 2

    second_messages = provider.calls[1]

    assistant_messages = [
        message
        for message in second_messages
        if message.role == "assistant"
    ]
    tool_messages = [
        message
        for message in second_messages
        if message.role == "tool"
    ]

    assert len(assistant_messages) == 1
    assert len(tool_messages) == 1

    assistant_payload = json.loads(
        assistant_messages[0].content
    )

    assert assistant_payload[
        "tool_calls"
    ][0]["call_id"] == "call-echo-1"

    tool_payload = json.loads(
        tool_messages[0].content
    )

    assert tool_payload["call_id"] == (
        "call-echo-1"
    )
    assert tool_payload["tool_name"] == "echo"
    assert tool_payload["is_error"] is False

    normalized_result = json.loads(
        tool_payload["content"]
    )

    assert normalized_result["status"] == (
        "SUCCEEDED"
    )
    assert normalized_result["text"] == (
        "AF-CORE-TOOL-LOOP-OK"
    )
    assert normalized_result["json"] == {
        "echoed": "AF-CORE-TOOL-LOOP-OK",
    }


def test_provider_tool_loop_returns_failed_tool_to_provider(
    tmp_path: Path,
) -> None:
    repo = create_repo(
        tmp_path / "repo"
    )

    registry = ExternalToolRegistry()
    registry.register(
        descriptor=ExternalToolDescriptor(
            tool_id="tool.fail",
            name="fail",
            description="Fail intentionally",
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            risk=ExternalToolRisk.READ_ONLY,
        ),
        handler=failing_handler,
    )

    provider = MockProviderAdapter(
        [
            ProviderResponse(
                provider_id="mock-provider",
                model_id="mock-model",
                tool_calls=[
                    ProviderToolCall(
                        call_id="call-fail-1",
                        tool_name="fail",
                        arguments={},
                    )
                ],
            ),
            ProviderResponse(
                provider_id="mock-provider",
                model_id="mock-model",
                content=(
                    "Handled the external tool failure."
                ),
            ),
        ]
    )

    result = asyncio.run(
        AgentExecutor(
            provider=StaticLLMProvider([]),
            profile=profile(),
            workspace_path=repo,
        ).execute_provider_tool_loop(
            task=task(),
            provider_adapter=provider,
            tool_runtime=ToolCallRuntime(
                registry=registry
            ),
            model_id="mock-model",
        )
    )

    assert result.successful is True
    assert len(
        result.provider_tool_records
    ) == 1
    assert (
        result.provider_tool_records[0]
        .successful
    ) is False

    second_messages = provider.calls[1]

    tool_message = next(
        message
        for message in second_messages
        if message.role == "tool"
    )

    payload = json.loads(
        tool_message.content
    )

    assert payload["is_error"] is True

    result_payload = json.loads(
        payload["content"]
    )

    assert result_payload["status"] == "FAILED"
    assert result_payload["error"] == (
        "intentional external failure"
    )


def test_provider_tool_loop_stops_at_maximum_steps(
    tmp_path: Path,
) -> None:
    repo = create_repo(
        tmp_path / "repo"
    )

    repeating_response = ProviderResponse(
        provider_id="mock-provider",
        model_id="mock-model",
        tool_calls=[
            ProviderToolCall(
                call_id="call-repeat",
                tool_name="echo",
                arguments={
                    "message": "repeat",
                },
            )
        ],
    )

    provider = MockProviderAdapter(
        [
            repeating_response,
            repeating_response.model_copy(
                deep=True
            ),
        ]
    )

    result = asyncio.run(
        AgentExecutor(
            provider=StaticLLMProvider([]),
            profile=profile(
                maximum_steps=2
            ),
            workspace_path=repo,
        ).execute_provider_tool_loop(
            task=task(),
            provider_adapter=provider,
            tool_runtime=ToolCallRuntime(
                registry=registry_with_echo()
            ),
            model_id="mock-model",
        )
    )

    assert result.successful is False
    assert "maximum provider tool" in (
        result.error or ""
    )
    assert len(
        result.provider_tool_records
    ) == 2
