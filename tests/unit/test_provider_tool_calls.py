import asyncio
from typing import Any

from af_core.runtime.provider_config import (
    ProviderEndpointConfig,
)
from af_core.runtime.provider_protocol import (
    ProviderMessage,
)
from af_core.runtime.providers.gemini_adapter import (
    GeminiAdapter,
)
from af_core.runtime.providers.http_client import (
    JSONHTTPResponse,
)
from af_core.runtime.providers.openai_adapter import (
    OpenAIAdapter,
)
from af_core.runtime.providers.openai_compatible import (
    OpenAICompatibleAdapter,
)


class MockHTTPClient:
    def __init__(
        self,
        responses: list[JSONHTTPResponse],
    ) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def request(self, **kwargs):
        self.calls.append(kwargs)

        if not self.responses:
            raise RuntimeError(
                "No mock HTTP responses remain."
            )

        return self.responses.pop(0)


def openai_config() -> ProviderEndpointConfig:
    return ProviderEndpointConfig(
        provider_id="openai",
        base_url="https://api.openai.com",
        timeout_seconds=30,
    )


def gemini_config() -> ProviderEndpointConfig:
    return ProviderEndpointConfig(
        provider_id="gemini",
        base_url=(
            "https://generativelanguage.googleapis.com"
        ),
        timeout_seconds=30,
    )


def compatible_config() -> ProviderEndpointConfig:
    return ProviderEndpointConfig(
        provider_id="compatible",
        base_url="http://127.0.0.1:8000",
        timeout_seconds=30,
    )


def test_openai_native_populates_provider_tool_calls() -> None:
    client = MockHTTPClient(
        [
            JSONHTTPResponse(
                status_code=200,
                headers={},
                payload={
                    "id": "resp_tool",
                    "status": "completed",
                    "model": "gpt-test",
                    "output": [
                        {
                            "type": "function_call",
                            "name": "read_file",
                            "arguments": (
                                '{"path":"README.md"}'
                            ),
                            "call_id": "call_openai_1",
                        }
                    ],
                    "usage": {},
                },
            )
        ]
    )

    response = asyncio.run(
        OpenAIAdapter(
            openai_config(),
            client=client,
        ).complete(
            messages=[
                ProviderMessage(
                    role="user",
                    content="Read the README.",
                )
            ],
            model_id="gpt-test",
        )
    )

    assert response.has_tool_calls is True
    assert len(response.tool_calls) == 1

    call = response.tool_calls[0]

    assert call.call_id == "call_openai_1"
    assert call.tool_name == "read_file"
    assert call.arguments == {
        "path": "README.md",
    }
    assert call.provider_format == (
        "OPENAI_RESPONSES"
    )
    assert response.metadata["tool_calls"]


def test_gemini_populates_provider_tool_calls() -> None:
    client = MockHTTPClient(
        [
            JSONHTTPResponse(
                status_code=200,
                headers={},
                payload={
                    "candidates": [
                        {
                            "content": {
                                "role": "model",
                                "parts": [
                                    {
                                        "functionCall": {
                                            "name": (
                                                "add_numbers"
                                            ),
                                            "args": {
                                                "left": 7,
                                                "right": 8,
                                            },
                                        }
                                    }
                                ],
                            },
                            "finishReason": "STOP",
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 10,
                        "candidatesTokenCount": 5,
                        "totalTokenCount": 15,
                    },
                    "modelVersion": "gemini-test",
                },
            )
        ]
    )

    response = asyncio.run(
        GeminiAdapter(
            gemini_config(),
            client=client,
        ).complete(
            messages=[
                ProviderMessage(
                    role="user",
                    content="Add 7 and 8.",
                )
            ],
            model_id="gemini-test",
        )
    )

    assert response.has_tool_calls is True
    assert len(response.tool_calls) == 1

    call = response.tool_calls[0]

    assert call.tool_name == "add_numbers"
    assert call.arguments == {
        "left": 7,
        "right": 8,
    }
    assert call.provider_format == "GEMINI"


def test_openai_compatible_populates_provider_tool_calls() -> None:
    client = MockHTTPClient(
        [
            JSONHTTPResponse(
                status_code=200,
                headers={},
                payload={
                    "id": "chatcmpl-tool",
                    "model": "local-model",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_local_1",
                                        "type": "function",
                                        "function": {
                                            "name": "search_text",
                                            "arguments": (
                                                '{"query":"AF-Core"}'
                                            ),
                                        },
                                    }
                                ],
                            },
                            "finish_reason": (
                                "tool_calls"
                            ),
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 20,
                        "completion_tokens": 4,
                        "total_tokens": 24,
                    },
                },
            )
        ]
    )

    response = asyncio.run(
        OpenAICompatibleAdapter(
            compatible_config(),
            client=client,
        ).complete(
            messages=[
                ProviderMessage(
                    role="user",
                    content="Search for AF-Core.",
                )
            ],
            model_id="local-model",
        )
    )

    assert response.has_tool_calls is True
    assert len(response.tool_calls) == 1

    call = response.tool_calls[0]

    assert call.call_id == "call_local_1"
    assert call.tool_name == "search_text"
    assert call.arguments == {
        "query": "AF-Core",
    }
    assert call.provider_format == (
        "OPENAI_COMPATIBLE"
    )


def test_text_only_responses_keep_empty_tool_calls() -> None:
    client = MockHTTPClient(
        [
            JSONHTTPResponse(
                status_code=200,
                headers={},
                payload={
                    "id": "resp_text",
                    "status": "completed",
                    "model": "gpt-test",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "Done.",
                                }
                            ],
                        }
                    ],
                    "usage": {},
                },
            )
        ]
    )

    response = asyncio.run(
        OpenAIAdapter(
            openai_config(),
            client=client,
        ).complete(
            messages=[
                ProviderMessage(
                    role="user",
                    content="Finish.",
                )
            ],
            model_id="gpt-test",
        )
    )

    assert response.content == "Done."
    assert response.has_tool_calls is False
    assert response.tool_calls == []
