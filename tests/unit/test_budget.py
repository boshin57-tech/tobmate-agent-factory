from decimal import Decimal

import pytest

from af_core.runtime.budget import (
    BudgetDecision,
    BudgetExceededError,
    BudgetLimit,
    BudgetPolicy,
    BudgetScope,
)
from af_core.runtime.model_registry import ModelPricing
from af_core.runtime.provider_protocol import (
    NormalizedTokenUsage,
)
from af_core.runtime.usage import (
    CostCalculator,
    UsageRecord,
    UsageSummary,
)


def projected_record(
    *,
    input_tokens: int = 100,
    output_tokens: int = 50,
    total_cost: Decimal | None = None,
) -> UsageRecord:
    usage = NormalizedTokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

    if total_cost is None:
        cost = CostCalculator().calculate(
            usage=usage,
            pricing=ModelPricing(
                input_usd_per_million_tokens=2.0,
                output_usd_per_million_tokens=8.0,
            ),
        )
    else:
        from af_core.runtime.usage import CostBreakdown

        cost = CostBreakdown(
            total_cost_usd=total_cost,
        )

    return UsageRecord(
        provider_id="provider-a",
        model_key="model-a",
        provider_model_id="provider-model-a",
        project_id="project-1",
        run_id="run-1",
        task_id="task-1",
        usage=usage,
        cost=cost,
    )


def current_summary(
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_cost: Decimal = Decimal("0"),
) -> UsageSummary:
    return UsageSummary(
        request_count=1,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        total_cost_usd=total_cost,
    )


def test_budget_allows_when_no_limit_exists() -> None:
    evaluation = BudgetPolicy().evaluate(
        current=current_summary(),
        projected=projected_record(),
        scope=BudgetScope.RUN,
        scope_id="run-1",
    )

    assert evaluation.decision is BudgetDecision.ALLOW
    assert evaluation.reasons == []


def test_budget_allows_usage_below_warning_threshold() -> None:
    policy = BudgetPolicy(
        [
            BudgetLimit(
                scope=BudgetScope.RUN,
                scope_id="run-1",
                maximum_cost_usd=Decimal("10"),
                maximum_total_tokens=10_000,
            )
        ]
    )

    evaluation = policy.evaluate(
        current=current_summary(
            input_tokens=100,
            output_tokens=100,
            total_cost=Decimal("1"),
        ),
        projected=projected_record(
            input_tokens=100,
            output_tokens=50,
            total_cost=Decimal("1"),
        ),
        scope=BudgetScope.RUN,
        scope_id="run-1",
    )

    assert evaluation.decision is BudgetDecision.ALLOW
    assert evaluation.projected_cost_usd == Decimal("2")
    assert evaluation.projected_total_tokens == 350


def test_budget_warns_at_configured_threshold() -> None:
    policy = BudgetPolicy(
        [
            BudgetLimit(
                scope=BudgetScope.RUN,
                scope_id="run-warning",
                maximum_cost_usd=Decimal("10"),
                warning_ratio=Decimal("0.80"),
            )
        ]
    )

    evaluation = policy.evaluate(
        current=current_summary(
            total_cost=Decimal("7"),
        ),
        projected=projected_record(
            total_cost=Decimal("1"),
        ),
        scope=BudgetScope.RUN,
        scope_id="run-warning",
    )

    assert evaluation.decision is BudgetDecision.WARN
    assert evaluation.projected_cost_usd == Decimal("8")
    assert evaluation.reasons


@pytest.mark.parametrize(
    (
        "limit_kwargs",
        "current_kwargs",
        "projected_kwargs",
        "reason_fragment",
    ),
    [
        (
            {
                "maximum_cost_usd": Decimal("2"),
            },
            {
                "total_cost": Decimal("1.50"),
            },
            {
                "total_cost": Decimal("0.75"),
            },
            "cost",
        ),
        (
            {
                "maximum_input_tokens": 1000,
            },
            {
                "input_tokens": 900,
            },
            {
                "input_tokens": 200,
                "output_tokens": 0,
            },
            "input tokens",
        ),
        (
            {
                "maximum_output_tokens": 500,
            },
            {
                "output_tokens": 450,
            },
            {
                "input_tokens": 0,
                "output_tokens": 100,
            },
            "output tokens",
        ),
        (
            {
                "maximum_total_tokens": 1000,
            },
            {
                "input_tokens": 700,
                "output_tokens": 200,
            },
            {
                "input_tokens": 100,
                "output_tokens": 100,
            },
            "total tokens",
        ),
    ],
)
def test_budget_blocks_each_limit_type(
    limit_kwargs,
    current_kwargs,
    projected_kwargs,
    reason_fragment: str,
) -> None:
    policy = BudgetPolicy(
        [
            BudgetLimit(
                scope=BudgetScope.TASK,
                scope_id="task-1",
                **limit_kwargs,
            )
        ]
    )

    evaluation = policy.evaluate(
        current=current_summary(**current_kwargs),
        projected=projected_record(
            **projected_kwargs
        ),
        scope=BudgetScope.TASK,
        scope_id="task-1",
    )

    assert evaluation.decision is BudgetDecision.BLOCK
    assert any(
        reason_fragment in reason
        for reason in evaluation.reasons
    )

    with pytest.raises(BudgetExceededError):
        policy.enforce(evaluation)


def test_budget_enforce_accepts_warning() -> None:
    policy = BudgetPolicy(
        [
            BudgetLimit(
                scope=BudgetScope.AGENT,
                scope_id="agent-1",
                maximum_total_tokens=1000,
                warning_ratio=Decimal("0.50"),
            )
        ]
    )

    evaluation = policy.evaluate(
        current=current_summary(
            input_tokens=400,
        ),
        projected=projected_record(
            input_tokens=100,
            output_tokens=0,
        ),
        scope=BudgetScope.AGENT,
        scope_id="agent-1",
    )

    assert evaluation.decision is BudgetDecision.WARN
    policy.enforce(evaluation)


def test_disabled_budget_limit_does_not_block() -> None:
    policy = BudgetPolicy(
        [
            BudgetLimit(
                scope=BudgetScope.PROJECT,
                scope_id="project-1",
                maximum_total_tokens=1,
                enabled=False,
            )
        ]
    )

    evaluation = policy.evaluate(
        current=current_summary(
            input_tokens=1000,
        ),
        projected=projected_record(
            input_tokens=1000,
        ),
        scope=BudgetScope.PROJECT,
        scope_id="project-1",
    )

    assert evaluation.decision is BudgetDecision.ALLOW


def test_duplicate_budget_limits_are_rejected() -> None:
    policy = BudgetPolicy(
        [
            BudgetLimit(
                scope=BudgetScope.RUN,
                scope_id="run-duplicate",
                maximum_total_tokens=100,
            ),
            BudgetLimit(
                scope=BudgetScope.RUN,
                scope_id="run-duplicate",
                maximum_total_tokens=200,
            ),
        ]
    )

    with pytest.raises(
        ValueError,
        match="Multiple budget limits",
    ):
        policy.evaluate(
            current=current_summary(),
            projected=projected_record(),
            scope=BudgetScope.RUN,
            scope_id="run-duplicate",
        )


def test_budget_limits_can_be_added_dynamically() -> None:
    policy = BudgetPolicy()

    policy.add_limit(
        BudgetLimit(
            scope=BudgetScope.GLOBAL,
            scope_id="global",
            maximum_total_tokens=10_000,
        )
    )

    limits = policy.list_limits()

    assert len(limits) == 1
    assert limits[0].scope is BudgetScope.GLOBAL
    assert limits[0].scope_id == "global"
