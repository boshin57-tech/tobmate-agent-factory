from __future__ import annotations

import argparse
import asyncio
import os

from af_core.runtime.provider_config import (
    ProviderEndpointConfig,
)
from af_core.runtime.provider_protocol import (
    ProviderMessage,
)
from af_core.runtime.providers.gemini_adapter import (
    GeminiAdapter,
)


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check Google Gemini API without modifying "
            "the repository."
        )
    )
    parser.add_argument(
        "--base-url",
        default=(
            "https://generativelanguage.googleapis.com"
        ),
    )
    parser.add_argument(
        "--model",
        required=True,
    )
    parser.add_argument(
        "--api-key-env",
        default="GEMINI_API_KEY",
    )
    args = parser.parse_args()

    if not os.environ.get(args.api_key_env):
        print(
            "API key environment variable is not set: "
            f"{args.api_key_env}"
        )
        return 2

    adapter = GeminiAdapter(
        ProviderEndpointConfig(
            provider_id="gemini",
            base_url=args.base_url,
            api_key_environment=args.api_key_env,
            timeout_seconds=30,
            options={
                "api_version": "v1beta",
                "generation_config": {
                    "temperature": 0,
                },
            },
        )
    )

    health = await adapter.health()

    print(
        f"provider={health.provider_id} "
        f"status={health.status.value} "
        f"latency_ms={health.latency_ms}"
    )

    if health.status.value != "HEALTHY":
        print(health.message)
        return 1

    response = await adapter.complete(
        messages=[
            ProviderMessage(
                role="user",
                content=(
                    "Reply with exactly: "
                    "AF-CORE-GEMINI-OK"
                ),
            )
        ],
        model_id=args.model,
        parameters={
            "temperature": 0,
        },
    )

    print(f"model={response.model_id}")
    print(f"content={response.content}")
    print(
        "usage="
        f"{response.usage.input_tokens}/"
        f"{response.usage.output_tokens}/"
        f"{response.usage.reasoning_tokens}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        asyncio.run(main())
    )
