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
from af_core.runtime.providers.ollama_adapter import (
    OllamaAdapter,
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
        provider_id="ollama-local",
        base_url="http://127.0.0.1:11434/",
        timeout_seconds=30,
        options={
            "generation_options": {
                "temperature": 0,
            }
        },
    )


def chat_response(
    *,
    content: str,
    prompt_tokens: int = 10,
    output_tokens: int = 5,
) -> JSONHTTPResponse:
    return JSONHTTPResponse(
        status_code=200,
        headers={},
        payload={
            "model": "test-model",
            "message": {
                "role": "assistant",
                "content": content,
            },
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": prompt_tokens,
            "eval_count": output_tokens,
            "total_duration": 100,
        },
    )


def test_ollama_complete_normalizes_response() -> None:
    client = MockHTTPClient(
        [
            chat_response(
                content="completed",
                prompt_tokens=120,
                output_tokens=30,
            )
        ]
    )

    adapter = OllamaAdapter(
        config(),
        client=client,
    )

    response = asyncio.run(
        adapter.complete(
            messages=[
                ProviderMessage(
                    role="user",
                    content="Perform the task.",
                )
            ],
            model_id="qwen-test",
            parameters={
                "options": {
                    "seed": 7,
                },
                "think": False,
            },
        )
    )

    assert response.provider_id == "ollama-local"
    assert response.model_id == "qwen-test"
    assert response.content == "completed"
    assert response.usage.input_tokens == 120
    assert response.usage.output_tokens == 30
    assert response.metadata["done_reason"] == "stop"

    request = client.calls[0]

    assert request["url"] == (
        "http://127.0.0.1:11434/api/chat"
    )
    assert request["payload"]["stream"] is False
    assert request["payload"]["think"] is False
    assert request["payload"]["options"] == {
        "temperature": 0,
        "seed": 7,
    }


def test_ollama_structured_validates_pydantic_model() -> None:
    client = MockHTTPClient(
        [
            chat_response(
                content='{"action":"complete","value":42}'
            )
        ]
    )

    adapter = OllamaAdapter(
        config(),
        client=client,
    )

    parsed, response = asyncio.run(
        adapter.structured(
            messages=[
                ProviderMessage(
                    role="user",
                    content="Return structured output.",
                )
            ],
            model_id="qwen-test",
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

    schema = client.calls[0]["payload"]["format"]

    assert schema["type"] == "object"
    assert "action" in schema["properties"]
    assert "value" in schema["properties"]


def test_ollama_health_reports_healthy() -> None:
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
        OllamaAdapter(
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
        "/api/tags"
    )


def test_ollama_health_reports_unavailable() -> None:
    client = MockHTTPClient(
        [
            ProviderHTTPError(
                "connection refused"
            )
        ]
    )

    health = asyncio.run(
        OllamaAdapter(
            config(),
            client=client,
        ).health()
    )

    assert (
        health.status
        is ProviderHealthStatus.UNAVAILABLE
    )
    assert "connection refused" in health.message


def test_ollama_capabilities_are_provider_neutral() -> None:
    capabilities = OllamaAdapter(
        config(),
        client=MockHTTPClient([]),
    ).capabilities

    assert ProviderCapability.TEXT in capabilities
    assert (
        ProviderCapability.STRUCTURED_OUTPUT
        in capabilities
    )
    assert (
        ProviderCapability.TOOL_CALLING
        in capabilities
    )
