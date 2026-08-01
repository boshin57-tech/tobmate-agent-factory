from __future__ import annotations

import argparse
import asyncio

from af_core.runtime.provider_config import (
    ProviderEndpointConfig,
)
from af_core.runtime.provider_protocol import (
    ProviderMessage,
)
from af_core.runtime.providers.ollama_adapter import (
    OllamaAdapter,
)


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check an Ollama provider without modifying "
            "the repository."
        )
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:11434",
    )
    parser.add_argument(
        "--model",
        default=None,
    )
    args = parser.parse_args()

    adapter = OllamaAdapter(
        ProviderEndpointConfig(
            provider_id="ollama-local",
            base_url=args.base_url,
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
                        "Reply with exactly: AF-CORE-OLLAMA-OK"
                    ),
                )
            ],
            model_id=args.model,
            parameters={
                "options": {
                    "temperature": 0,
                }
            },
        )

        print(f"model={args.model}")
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
