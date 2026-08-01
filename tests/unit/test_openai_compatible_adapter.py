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
from af_core.runtime.providers.http_client import (
    JSONHTTPResponse,
    ProviderHTTPError,
)
from af_core.runtime.providers.openai_compatible import (
    OpenAICompatibleAdapter,
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
        provider_id="vllm-local",
        base_url="http://127.0.0.1:8000/",
        timeout_seconds=30,
        headers={
            "X-Test": "enabled",
        },
        options={
            "generation_parameters": {
                "temperature": 0,
            },
            "capabilities": [
                "REASONING",
            ],
        },
    )


def completion_response(
    *,
    content: Any,
    prompt_tokens: int = 100,
    cached_tokens: int = 20,
    completion_tokens: int = 30,
    reasoning_tokens: int = 5,
) -> JSONHTTPResponse:
    return JSONHTTPResponse(
        status_code=200,
        headers={
            "x-request-id": "header-request-id",
        },
        payload={
            "id": "completion-request-id",
            "model": "served-model",
            "created": 1234567890,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": (
                    prompt_tokens + completion_tokens
                ),
                "prompt_tokens_details": {
                    "cached_tokens": cached_tokens,
                },
                "completion_tokens_details": {
                    "reasoning_tokens": reasoning_tokens,
                },
            },
        },
    )


def test_complete_normalizes_openai_compatible_response() -> None:
    client = MockHTTPClient(
        [
            completion_response(
                content="completed",
            )
        ]
    )

    adapter = OpenAICompatibleAdapter(
        config(),
        client=client,
    )

    response = asyncio.run(
        adapter.complete(
            messages=[
                ProviderMessage(
                    role="user",
                    content="Perform task.",
                )
            ],
            model_id="requested-model",
            parameters={
                "seed": 7,
                "temperature": 0.2,
            },
        )
    )

    assert response.provider_id == "vllm-local"
    assert response.model_id == "served-model"
    assert response.content == "completed"
    assert response.request_id == "completion-request-id"

    assert response.usage.input_tokens == 100
    assert response.usage.cached_input_tokens == 20
    assert response.usage.output_tokens == 30
    assert response.usage.reasoning_tokens == 5

    request = client.calls[0]

    assert request["url"] == (
        "http://127.0.0.1:8000/v1/chat/completions"
    )
    assert request["headers"]["X-Test"] == "enabled"
    assert request["payload"]["model"] == "requested-model"
    assert request["payload"]["stream"] is False
    assert request["payload"]["temperature"] == 0.2
    assert request["payload"]["seed"] == 7


def test_structured_adds_json_schema_and_validates() -> None:
    client = MockHTTPClient(
        [
            completion_response(
                content='{"action":"complete","value":42}'
            )
        ]
    )

    adapter = OpenAICompatibleAdapter(
        config(),
        client=client,
    )

    parsed, response = asyncio.run(
        adapter.structured(
            messages=[
                ProviderMessage(
                    role="user",
                    content="Return JSON.",
                )
            ],
            model_id="requested-model",
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

    response_format = (
        client.calls[0]
        ["payload"]
        ["response_format"]
    )

    assert response_format["type"] == "json_schema"
    assert (
        response_format["json_schema"]["strict"]
        is True
    )
    assert (
        response_format["json_schema"]["schema"]["type"]
        == "object"
    )


def test_content_parts_are_joined() -> None:
    client = MockHTTPClient(
        [
            completion_response(
                content=[
                    {
                        "type": "text",
                        "text": "first",
                    },
                    {
                        "type": "output_text",
                        "text": "second",
                    },
                    {
                        "type": "ignored",
                        "value": "skip",
                    },
                ]
            )
        ]
    )

    response = asyncio.run(
        OpenAICompatibleAdapter(
            config(),
            client=client,
        ).complete(
            messages=[
                ProviderMessage(
                    role="user",
                    content="Respond.",
                )
            ],
            model_id="model",
        )
    )

    assert response.content == "first\nsecond"


def test_health_reports_healthy() -> None:
    client = MockHTTPClient(
        [
            JSONHTTPResponse(
                status_code=200,
                headers={},
                payload={
                    "data": [],
                },
            )
        ]
    )

    health = asyncio.run(
        OpenAICompatibleAdapter(
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
        "/v1/models"
    )


def test_health_reports_unavailable() -> None:
    client = MockHTTPClient(
        [
            ProviderHTTPError(
                "connection refused"
            )
        ]
    )

    health = asyncio.run(
        OpenAICompatibleAdapter(
            config(),
            client=client,
        ).health()
    )

    assert (
        health.status
        is ProviderHealthStatus.UNAVAILABLE
    )
    assert "connection refused" in health.message


def test_configured_capabilities_are_added() -> None:
    capabilities = OpenAICompatibleAdapter(
        config(),
        client=MockHTTPClient([]),
    ).capabilities

    assert ProviderCapability.TEXT in capabilities
    assert (
        ProviderCapability.STRUCTURED_OUTPUT
        in capabilities
    )
    assert ProviderCapability.REASONING in capabilities
