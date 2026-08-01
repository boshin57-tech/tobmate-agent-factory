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
from af_core.runtime.providers.openai_compatible import (
    OpenAICompatibleAdapter,
)


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check an OpenAI-compatible provider such as "
            "vLLM, LM Studio, or LocalAI."
        )
    )
    parser.add_argument(
        "--provider-id",
        default="openai-compatible-local",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
    )
    parser.add_argument(
        "--model",
        default=None,
    )
    parser.add_argument(
        "--api-key-env",
        default=None,
    )
    args = parser.parse_args()

    if (
        args.api_key_env
        and not os.environ.get(args.api_key_env)
    ):
        print(
            "API key environment variable is not set: "
            f"{args.api_key_env}"
        )
        return 2

    adapter = OpenAICompatibleAdapter(
        ProviderEndpointConfig(
            provider_id=args.provider_id,
            base_url=args.base_url,
            api_key_environment=args.api_key_env,
            timeout_seconds=30,
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

    if args.model:
        response = await adapter.complete(
            messages=[
                ProviderMessage(
                    role="user",
                    content=(
                        "Reply with exactly: "
                        "AF-CORE-OPENAI-COMPATIBLE-OK"
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
            f"{response.usage.output_tokens}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        asyncio.run(main())
    )
