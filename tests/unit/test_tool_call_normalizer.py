import json

import pytest

from af_core.runtime.tool_call_models import (
    ProviderToolCallFormat,
)
from af_core.runtime.tool_call_normalizer import (
    ProviderToolCallNormalizer,
    ToolCallNormalizationError,
)
from af_core.tools.models import (
    ExternalToolResult,
    ToolContent,
    ToolContentType,
    ToolExecutionStatus,
)


def normalizer() -> ProviderToolCallNormalizer:
    return ProviderToolCallNormalizer()


def test_openai_responses_normalization() -> None:
    call = normalizer().normalize(
        provider_format=(
            ProviderToolCallFormat.OPENAI_RESPONSES
        ),
        payload={
            "call_id": "call-1",
            "name": "read_file",
            "arguments": '{"path":"README.md"}',
        },
        provider_id="openai",
        model_id="gpt-test",
    )

    assert call.call_id == "call-1"
    assert call.tool_name == "read_file"
    assert call.arguments == {
        "path": "README.md",
    }
    assert call.provider_id == "openai"
    assert call.model_id == "gpt-test"


def test_openai_compatible_normalization() -> None:
    call = normalizer().normalize(
        provider_format=(
            ProviderToolCallFormat.OPENAI_COMPATIBLE
        ),
        payload={
            "id": "call-2",
            "type": "function",
            "function": {
                "name": "write_file",
                "arguments": {
                    "path": "app.py",
                    "content": "print('ok')",
                },
            },
        },
    )

    assert call.call_id == "call-2"
    assert call.tool_name == "write_file"
    assert call.arguments["path"] == "app.py"


def test_gemini_and_anthropic_normalization() -> None:
    gemini = normalizer().normalize(
        provider_format=ProviderToolCallFormat.GEMINI,
        payload={
            "functionCall": {
                "name": "add_numbers",
                "args": {
                    "left": 4,
                    "right": 5,
                },
            }
        },
    )

    anthropic = normalizer().normalize(
        provider_format=(
            ProviderToolCallFormat.ANTHROPIC
        ),
        payload={
            "id": "toolu_1",
            "name": "search",
            "input": {
                "query": "AF-Core",
            },
        },
    )

    assert gemini.tool_name == "add_numbers"
    assert gemini.arguments == {
        "left": 4,
        "right": 5,
    }
    assert anthropic.call_id == "toolu_1"
    assert anthropic.arguments == {
        "query": "AF-Core",
    }


def test_generic_normalization_and_external_call() -> None:
    call = normalizer().normalize(
        provider_format=ProviderToolCallFormat.GENERIC,
        payload={
            "call_id": "generic-1",
            "tool_name": "echo",
            "arguments": {
                "message": "hello",
            },
        },
    )

    external = call.to_external_call(
        tool_id="tool.echo",
        project_id="project-1",
        run_id="run-1",
        task_id="task-1",
        agent_name="agent-1",
    )

    assert external.tool_id == "tool.echo"
    assert external.call_id == "generic-1"
    assert external.arguments == {
        "message": "hello",
    }
    assert external.project_id == "project-1"


@pytest.mark.parametrize(
    "arguments",
    [
        "[1,2,3]",
        "not-json",
        123,
    ],
)
def test_invalid_arguments_are_rejected(
    arguments,
) -> None:
    with pytest.raises(
        ToolCallNormalizationError,
    ):
        normalizer().normalize(
            provider_format=(
                ProviderToolCallFormat.GENERIC
            ),
            payload={
                "tool_name": "echo",
                "arguments": arguments,
            },
        )


def test_missing_tool_name_is_rejected() -> None:
    with pytest.raises(
        ToolCallNormalizationError,
        match="name is required",
    ):
        normalizer().normalize(
            provider_format=(
                ProviderToolCallFormat.GENERIC
            ),
            payload={
                "arguments": {},
            },
        )


def test_result_message_normalizes_content() -> None:
    call = normalizer().normalize(
        provider_format=ProviderToolCallFormat.GENERIC,
        payload={
            "call_id": "call-3",
            "tool_name": "report",
            "arguments": {},
        },
    )

    result = ExternalToolResult(
        call_id="call-3",
        tool_id="tool.report",
        status=ToolExecutionStatus.SUCCEEDED,
        content=[
            ToolContent(
                type=ToolContentType.TEXT,
                text="completed",
            ),
            ToolContent(
                type=ToolContentType.JSON,
                json_value={
                    "count": 3,
                },
            ),
            ToolContent(
                type=ToolContentType.RESOURCE,
                uri="file:///report.json",
                mime_type="application/json",
            ),
        ],
        duration_ms=12.5,
    )

    message = normalizer().result_message(
        tool_call=call,
        result=result,
    )

    payload = json.loads(message.content)

    assert message.role == "tool"
    assert message.call_id == "call-3"
    assert message.tool_name == "report"
    assert message.is_error is False
    assert payload["status"] == "SUCCEEDED"
    assert payload["text"] == "completed"
    assert payload["json"] == {
        "count": 3,
    }
    assert payload["resources"][0]["uri"] == (
        "file:///report.json"
    )


def test_error_result_message_contains_error() -> None:
    call = normalizer().normalize(
        provider_format=ProviderToolCallFormat.GENERIC,
        payload={
            "call_id": "call-4",
            "tool_name": "fail",
            "arguments": {},
        },
    )

    result = ExternalToolResult(
        call_id="call-4",
        tool_id="tool.fail",
        status=ToolExecutionStatus.FAILED,
        is_error=True,
        error="expected failure",
    )

    message = normalizer().result_message(
        tool_call=call,
        result=result,
    )

    payload = json.loads(message.content)

    assert message.is_error is True
    assert payload["is_error"] is True
    assert payload["error"] == "expected failure"
