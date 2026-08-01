import asyncio
from typing import Any

from pydantic import BaseModel

from af_core.runtime.provider_config import (
    ProviderEndpointConfig,
)
from af_core.runtime.provider_protocol import (
    ProviderCapability,
    ProviderHealthStatus,
    ProviderMessage,
)
from af_core.runtime.providers.gemini_adapter import (
    GeminiAdapter,
)
from af_core.runtime.providers.http_client import (
    JSONHTTPResponse,
    ProviderHTTPError,
)


class StructuredAnswer(BaseModel):
    action: str
    value: int


class MockHTTPClient:
    def __init__(
        self,
        responses: list[
            JSONHTTPResponse | Exception
        ],
    ) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def request(self, **kwargs):
        self.calls.append(kwargs)

        if not self.responses:
            raise RuntimeError(
                "No mock HTTP responses remain."
            )

        response = self.responses.pop(0)

        if isinstance(response, Exception):
            raise response

        return response


def config() -> ProviderEndpointConfig:
    return ProviderEndpointConfig(
        provider_id="gemini",
        base_url=(
            "https://generativelanguage.googleapis.com"
        ),
        api_key_environment="GEMINI_API_KEY",
        timeout_seconds=30,
        options={
            "api_version": "v1beta",
            "generation_config": {
                "temperature": 0,
            },
        },
    )


def gemini_response(
    *,
    text: str,
    prompt_tokens: int = 100,
    cached_tokens: int = 20,
    output_tokens: int = 30,
    thought_tokens: int = 5,
) -> JSONHTTPResponse:
    return JSONHTTPResponse(
        status_code=200,
        headers={
            "x-goog-request-id": "gemini-request-id",
        },
        payload={
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [
                            {
                                "text": text,
                            }
                        ],
                    },
                    "finishReason": "STOP",
                    "safetyRatings": [],
                }
            ],
            "usageMetadata": {
                "promptTokenCount": prompt_tokens,
                "cachedContentTokenCount": cached_tokens,
                "candidatesTokenCount": output_tokens,
                "thoughtsTokenCount": thought_tokens,
                "totalTokenCount": (
                    prompt_tokens
                    + output_tokens
                    + thought_tokens
                ),
            },
            "modelVersion": "gemini-test",
            "responseId": "response-1",
        },
    )


def test_complete_normalizes_gemini_response(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "GEMINI_API_KEY",
        "test-key",
    )

    client = MockHTTPClient(
        [
            gemini_response(
                text="completed",
            )
        ]
    )

    response = asyncio.run(
        GeminiAdapter(
            config(),
            client=client,
        ).complete(
            messages=[
                ProviderMessage(
                    role="system",
                    content="Follow instructions.",
                ),
                ProviderMessage(
                    role="user",
                    content="Perform the task.",
                ),
            ],
            model_id="gemini-test-model",
            parameters={
                "temperature": 0.2,
                "seed": 7,
            },
        )
    )

    assert response.provider_id == "gemini"
    assert response.model_id == "gemini-test-model"
    assert response.content == "completed"
    assert response.request_id == "gemini-request-id"

    assert response.usage.input_tokens == 100
    assert response.usage.cached_input_tokens == 20
    assert response.usage.output_tokens == 30
    assert response.usage.reasoning_tokens == 5

    request = client.calls[0]

    assert request["url"].endswith(
        "/v1beta/models/"
        "gemini-test-model:generateContent"
    )
    assert request["headers"]["x-goog-api-key"] == (
        "test-key"
    )

    payload = request["payload"]

    assert payload["systemInstruction"] == {
        "parts": [
            {
                "text": "Follow instructions.",
            }
        ]
    }
    assert payload["contents"] == [
        {
            "role": "user",
            "parts": [
                {
                    "text": "Perform the task.",
                }
            ],
        }
    ]
    assert payload["generationConfig"] == {
        "temperature": 0.2,
        "seed": 7,
    }


def test_structured_adds_json_schema_and_validates() -> None:
    client = MockHTTPClient(
        [
            gemini_response(
                text='{"action":"complete","value":42}'
            )
        ]
    )

    parsed, response = asyncio.run(
        GeminiAdapter(
            config(),
            client=client,
        ).structured(
            messages=[
                ProviderMessage(
                    role="user",
                    content="Return JSON.",
                )
            ],
            model_id="gemini-test-model",
            response_model=StructuredAnswer,
        )
    )

    assert parsed == StructuredAnswer(
        action="complete",
        value=42,
    )
    assert response.parsed == {
        "action": "complete",
        "value": 42,
    }

    generation_config = (
        client.calls[0]
        ["payload"]
        ["generationConfig"]
    )

    assert (
        generation_config["responseMimeType"]
        == "application/json"
    )
    assert (
        generation_config["responseJsonSchema"]["type"]
        == "object"
    )


def test_tool_and_thought_parts_are_normalized() -> None:
    client = MockHTTPClient(
        [
            JSONHTTPResponse(
                status_code=200,
                headers={},
                payload={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "thought": True,
                                        "text": "internal",
                                    },
                                    {
                                        "functionCall": {
                                            "name": "read_file",
                                            "args": {
                                                "path": "app.py",
                                            },
                                        }
                                    },
                                    {
                                        "text": "visible",
                                    },
                                ]
                            },
                            "finishReason": "STOP",
                        }
                    ],
                    "usageMetadata": {},
                },
            )
        ]
    )

    response = asyncio.run(
        GeminiAdapter(
            config(),
            client=client,
        ).complete(
            messages=[
                ProviderMessage(
                    role="user",
                    content="Use a tool.",
                )
            ],
            model_id="gemini-test-model",
        )
    )

    assert response.content == "internal\nvisible"
    assert response.metadata["function_calls"] == [
        {
            "name": "read_file",
            "args": {
                "path": "app.py",
            },
        }
    ]
    assert len(
        response.metadata["thought_parts"]
    ) == 1


def test_health_reports_healthy(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "GEMINI_API_KEY",
        "test-key",
    )

    client = MockHTTPClient(
        [
            JSONHTTPResponse(
                status_code=200,
                headers={},
                payload={
                    "models": [],
                },
            )
        ]
    )

    health = asyncio.run(
        GeminiAdapter(
            config(),
            client=client,
        ).health()
    )

    assert (
        health.status
        is ProviderHealthStatus.HEALTHY
    )
    assert health.latency_ms is not None
    assert client.calls[0]["method"] == "GET"
    assert client.calls[0]["url"].endswith(
        "/v1beta/models"
    )
    assert client.calls[0]["headers"][
        "x-goog-api-key"
    ] == "test-key"


def test_health_reports_unavailable() -> None:
    client = MockHTTPClient(
        [
            ProviderHTTPError(
                "connection refused"
            )
        ]
    )

    health = asyncio.run(
        GeminiAdapter(
            config(),
            client=client,
        ).health()
    )

    assert (
        health.status
        is ProviderHealthStatus.UNAVAILABLE
    )
    assert "connection refused" in health.message


def test_capabilities_include_native_gemini_features() -> None:
    capabilities = GeminiAdapter(
        config(),
        client=MockHTTPClient([]),
    ).capabilities

    assert ProviderCapability.TEXT in capabilities
    assert (
        ProviderCapability.STRUCTURED_OUTPUT
        in capabilities
    )
    assert ProviderCapability.VISION in capabilities
    assert ProviderCapability.REASONING in capabilities
    assert (
        ProviderCapability.CACHED_INPUT
        in capabilities
    )
