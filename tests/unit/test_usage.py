from decimal import Decimal

from af_core.runtime.model_registry import ModelPricing
from af_core.runtime.provider_protocol import (
    NormalizedTokenUsage,
)
from af_core.runtime.usage import (
    CostCalculator,
    UsageAccumulator,
    UsageRecord,
)


def pricing() -> ModelPricing:
    return ModelPricing(
        input_usd_per_million_tokens=2.0,
        cached_input_usd_per_million_tokens=0.5,
        output_usd_per_million_tokens=8.0,
    )


def record(
    *,
    provider_id: str = "provider-a",
    model_key: str = "model-a",
    project_id: str = "project-1",
    run_id: str = "run-1",
    task_id: str = "task-1",
    input_tokens: int = 1000,
    cached_input_tokens: int = 200,
    output_tokens: int = 500,
) -> UsageRecord:
    usage = NormalizedTokenUsage(
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=100,
    )

    cost = CostCalculator().calculate(
        usage=usage,
        pricing=pricing(),
    )

    return UsageRecord(
        provider_id=provider_id,
        model_key=model_key,
        provider_model_id="provider-model-a",
        request_id="request-1",
        project_id=project_id,
        run_id=run_id,
        task_id=task_id,
        agent_name="implementer-1",
        usage=usage,
        cost=cost,
    )


def test_cost_calculator_separates_cached_input() -> None:
    usage = NormalizedTokenUsage(
        input_tokens=1_000_000,
        cached_input_tokens=250_000,
        output_tokens=500_000,
    )

    result = CostCalculator().calculate(
        usage=usage,
        pricing=pricing(),
    )

    assert result.input_cost_usd == Decimal("1.50000000")
    assert result.cached_input_cost_usd == Decimal(
        "0.12500000"
    )
    assert result.output_cost_usd == Decimal("4.00000000")
    assert result.total_cost_usd == Decimal("5.62500000")


def test_cost_calculator_handles_zero_pricing() -> None:
    result = CostCalculator().calculate(
        usage=NormalizedTokenUsage(
            input_tokens=10_000,
            output_tokens=5_000,
        ),
        pricing=ModelPricing(),
    )

    assert result.total_cost_usd == Decimal("0E-8")


def test_cached_tokens_never_create_negative_input_cost() -> None:
    result = CostCalculator().calculate(
        usage=NormalizedTokenUsage(
            input_tokens=100,
            cached_input_tokens=200,
            output_tokens=0,
        ),
        pricing=pricing(),
    )

    assert result.input_cost_usd == Decimal("0E-8")
    assert result.cached_input_cost_usd == Decimal(
        "0.00010000"
    )


def test_usage_accumulator_summarizes_records() -> None:
    accumulator = UsageAccumulator()

    accumulator.add(
        record(
            input_tokens=1000,
            cached_input_tokens=200,
            output_tokens=500,
        )
    )
    accumulator.add(
        record(
            input_tokens=2000,
            cached_input_tokens=500,
            output_tokens=1000,
        )
    )

    summary = accumulator.summarize()

    assert summary.request_count == 2
    assert summary.input_tokens == 3000
    assert summary.cached_input_tokens == 700
    assert summary.output_tokens == 1500
    assert summary.reasoning_tokens == 200
    assert summary.total_tokens == 4500
    assert summary.total_cost_usd == Decimal(
        "0.01695000"
    )


def test_usage_accumulator_filters_scopes() -> None:
    accumulator = UsageAccumulator()

    first = record(
        provider_id="provider-a",
        model_key="model-a",
        project_id="project-1",
        run_id="run-1",
        task_id="task-1",
    )
    second = record(
        provider_id="provider-b",
        model_key="model-b",
        project_id="project-2",
        run_id="run-2",
        task_id="task-2",
    )

    accumulator.add(first)
    accumulator.add(second)

    assert accumulator.summarize(
        project_id="project-1"
    ).request_count == 1

    assert accumulator.summarize(
        run_id="run-2"
    ).request_count == 1

    assert accumulator.summarize(
        task_id="task-1"
    ).request_count == 1

    assert accumulator.summarize(
        provider_id="provider-b"
    ).request_count == 1

    assert accumulator.summarize(
        model_key="missing"
    ).request_count == 0


def test_usage_records_returns_copy() -> None:
    accumulator = UsageAccumulator()
    accumulator.add(record())

    returned = accumulator.records()
    returned.clear()

    assert len(accumulator.records()) == 1
