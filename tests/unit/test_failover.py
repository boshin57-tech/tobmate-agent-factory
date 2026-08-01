import asyncio

import pytest

from af_core.runtime.failover import (
    FailoverExhaustedError,
    FailoverOutcome,
    ProviderFailoverExecutor,
)
from af_core.runtime.model_registry import (
    ModelTier,
    RegisteredModel,
)
from af_core.runtime.provider_protocol import (
    ProviderHealth,
    ProviderHealthStatus,
)
from af_core.runtime.routing import (
    RoutingCandidate,
    RoutingResult,
)


def candidate(
    rank: int,
    model_key: str,
    provider_id: str,
) -> RoutingCandidate:
    return RoutingCandidate(
        rank=rank,
        model=RegisteredModel(
            model_key=model_key,
            provider_id=provider_id,
            provider_model_id=f"{provider_id}/{model_key}",
            display_name=model_key,
            tier=ModelTier.STANDARD,
        ),
        provider_health=ProviderHealth(
            provider_id=provider_id,
            status=ProviderHealthStatus.HEALTHY,
        ),
        score=100 - rank,
    )


def routing() -> RoutingResult:
    return RoutingResult(
        candidates=[
            candidate(1, "model-a", "provider-a"),
            candidate(2, "model-b", "provider-b"),
            candidate(3, "model-c", "provider-c"),
        ]
    )


def test_failover_uses_second_candidate_after_retryable_failure() -> None:
    calls: list[str] = []

    async def operation(item):
        calls.append(item.model.model_key)

        if item.model.model_key == "model-a":
            raise RuntimeError("temporary provider failure")

        return f"success:{item.model.model_key}"

    result = asyncio.run(
        ProviderFailoverExecutor[str]().execute(
            routing=routing(),
            operation=operation,
        )
    )

    assert result.outcome is FailoverOutcome.SUCCEEDED
    assert result.value == "success:model-b"
    assert result.selected_model_key == "model-b"
    assert result.selected_provider_id == "provider-b"
    assert calls == ["model-a", "model-b"]
    assert [item.successful for item in result.attempts] == [
        False,
        True,
    ]


def test_non_retryable_failure_blocks_immediately() -> None:
    calls: list[str] = []

    async def operation(item):
        calls.append(item.model.model_key)
        raise ValueError("invalid request")

    result = asyncio.run(
        ProviderFailoverExecutor[str]().execute(
            routing=routing(),
            operation=operation,
        )
    )

    assert result.outcome is FailoverOutcome.BLOCKED
    assert calls == ["model-a"]
    assert len(result.attempts) == 1
    assert "Non-retryable" in (
        result.failure_reason or ""
    )


def test_all_candidates_failing_returns_exhausted() -> None:
    async def operation(item):
        raise RuntimeError(
            f"{item.model.model_key} failed"
        )

    result = asyncio.run(
        ProviderFailoverExecutor[str]().execute(
            routing=routing(),
            operation=operation,
        )
    )

    assert result.outcome is FailoverOutcome.EXHAUSTED
    assert len(result.attempts) == 3
    assert all(
        not attempt.successful
        for attempt in result.attempts
    )


def test_empty_routing_is_blocked() -> None:
    result = asyncio.run(
        ProviderFailoverExecutor[str]().execute(
            routing=RoutingResult(),
            operation=lambda item: None,
        )
    )

    assert result.outcome is FailoverOutcome.BLOCKED
    assert result.attempts == []


def test_raise_on_exhaustion_raises() -> None:
    async def operation(item):
        raise RuntimeError("unavailable")

    with pytest.raises(
        FailoverExhaustedError,
        match="All routed model candidates failed",
    ):
        asyncio.run(
            ProviderFailoverExecutor[str]().execute(
                routing=routing(),
                operation=operation,
                raise_on_exhaustion=True,
            )
        )


def test_custom_retry_classifier_controls_failover() -> None:
    calls: list[str] = []

    async def operation(item):
        calls.append(item.model.model_key)
        raise RuntimeError("do not retry")

    result = asyncio.run(
        ProviderFailoverExecutor[str](
            retry_classifier=lambda exc: False
        ).execute(
            routing=routing(),
            operation=operation,
        )
    )

    assert result.outcome is FailoverOutcome.BLOCKED
    assert calls == ["model-a"]
