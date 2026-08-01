import asyncio
from typing import Any

import pytest
from pydantic import BaseModel

from af_core.runtime.provider_config import ProviderEndpointConfig
from af_core.runtime.provider_protocol import (
    ProviderAdapterError,
    ProviderCapability,
    ProviderHealthStatus,
    ProviderMessage,
)
from af_core.runtime.providers.http_client import (
    JSONHTTPResponse,
    ProviderHTTPError,
)
from af_core.runtime.providers.openai_adapter import OpenAIAdapter


class StructuredAnswer(BaseModel):
    action: str
    value: int


class MockHTTPClient:
    def __init__(
        self,
        responses: list[JSONHTTPResponse | Exception],
    ) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def request(self, **kwargs):
        self.calls.append(kwargs)

        if not self.responses:
            raise RuntimeError("No mock HTTP responses remain.")

        response = self.responses.pop(0)

        if isinstance(response, Exception):
            raise response

        return response


def config() -> ProviderEndpointConfig:
    return ProviderEndpointConfig(
        provider_id="openai",
        base_url="https://api.openai.com",
        api_key_environment="OPENAI_API_KEY",
        timeout_seconds=30,
        options={
            "organization": "org-test",
            "project": "proj-test",
            "response_parameters": {
                "store": False,
            },
        },
    )


def response_payload(
    *,
    content: str = "completed",
) -> JSONHTTPResponse:
    return JSONHTTPResponse(
        status_code=200,
        headers={
            "x-request-id": "header-request-id",
        },
        payload={
            "id": "resp_123",
            "object": "response",
            "status": "completed",
            "model": "gpt-test",
            "created_at": 1234567890,
            "completed_at": 1234567891,
            "output": [
                {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": content,
                            "annotations": [],
                        }
                    ],
                }
            ],
            "usage": {
                "input_tokens": 120,
                "input_tokens_details": {
                    "cached_tokens": 20,
                },
                "output_tokens": 40,
                "output_tokens_details": {
                    "reasoning_tokens": 10,
                },
                "total_tokens": 160,
            },
            "store": False,
        },
    )


def test_complete_normalizes_responses_api(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    client = MockHTTPClient(
        [response_payload()]
    )

    response = asyncio.run(
        OpenAIAdapter(
            config(),
            client=client,
        ).complete(
            messages=[
                ProviderMessage(
                    role="developer",
                    content="Follow policy.",
                ),
                ProviderMessage(
                    role="user",
                    content="Perform task.",
                ),
            ],
            model_id="gpt-test",
            parameters={
                "temperature": 0,
            },
        )
    )

    assert response.provider_id == "openai"
    assert response.model_id == "gpt-test"
    assert response.content == "completed"
    assert response.request_id == "resp_123"

    assert response.usage.input_tokens == 120
    assert response.usage.cached_input_tokens == 20
    assert response.usage.output_tokens == 40
    assert response.usage.reasoning_tokens == 10

    request = client.calls[0]

    assert request["url"] == (
        "https://api.openai.com/v1/responses"
    )
    assert request["headers"]["Authorization"] == (
        "Bearer test-key"
    )
    assert request["headers"]["OpenAI-Organization"] == (
        "org-test"
    )
    assert request["headers"]["OpenAI-Project"] == (
        "proj-test"
    )

    assert request["payload"]["input"] == [
        {
            "role": "developer",
            "content": "Follow policy.",
        },
        {
            "role": "user",
            "content": "Perform task.",
        },
    ]
    assert request["payload"]["temperature"] == 0
    assert request["payload"]["store"] is False


def test_structured_adds_json_schema_and_validates() -> None:
    client = MockHTTPClient(
        [
            response_payload(
                content='{"action":"complete","value":42}'
            )
        ]
    )

    parsed, response = asyncio.run(
        OpenAIAdapter(
            config(),
            client=client,
        ).structured(
            messages=[
                ProviderMessage(
                    role="user",
                    content="Return JSON.",
                )
            ],
            model_id="gpt-test",
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

    format_payload = (
        client.calls[0]
        ["payload"]
        ["text"]
        ["format"]
    )

    assert format_payload["type"] == "json_schema"
    assert format_payload["strict"] is True
    assert format_payload["schema"]["type"] == "object"


def test_refusal_is_normalized_and_blocks_structured() -> None:
    client = MockHTTPClient(
        [
            JSONHTTPResponse(
                status_code=200,
                headers={},
                payload={
                    "id": "resp_refusal",
                    "status": "completed",
                    "model": "gpt-test",
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "refusal",
                                    "refusal": "Request refused.",
                                }
                            ],
                        }
                    ],
                    "usage": {},
                },
            )
        ]
    )

    with pytest.raises(
        ProviderAdapterError,
        match="refused structured output",
    ):
        asyncio.run(
            OpenAIAdapter(
                config(),
                client=client,
            ).structured(
                messages=[
                    ProviderMessage(
                        role="user",
                        content="Return JSON.",
                    )
                ],
                model_id="gpt-test",
                response_model=StructuredAnswer,
            )
        )


def test_tool_calls_are_normalized() -> None:
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
                                '{"path":"app.py"}'
                            ),
                            "call_id": "call_1",
                        },
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "Tool requested.",
                                }
                            ],
                        },
                    ],
                    "usage": {},
                },
            )
        ]
    )

    response = asyncio.run(
        OpenAIAdapter(
            config(),
            client=client,
        ).complete(
            messages=[
                ProviderMessage(
                    role="user",
                    content="Use tool.",
                )
            ],
            model_id="gpt-test",
        )
    )

    assert response.content == "Tool requested."
    assert response.metadata["tool_calls"] == [
        {
            "type": "function_call",
            "name": "read_file",
            "arguments": '{"path":"app.py"}',
            "call_id": "call_1",
        }
    ]


def test_health_reports_healthy(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

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
        OpenAIAdapter(
            config(),
            client=client,
        ).health()
    )

    assert (
        health.status
        is ProviderHealthStatus.HEALTHY
    )
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
        OpenAIAdapter(
            config(),
            client=client,
        ).health()
    )

    assert (
        health.status
        is ProviderHealthStatus.UNAVAILABLE
    )
    assert "connection refused" in health.message


def test_capabilities_include_native_openai_features() -> None:
    capabilities = OpenAIAdapter(
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
    assert ProviderCapability.REASONING in capabilities
    assert (
        ProviderCapability.CACHED_INPUT
        in capabilities
    )
