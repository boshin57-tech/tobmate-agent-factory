from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from pydantic import BaseModel, Field

from .model_registry import ModelPricing
from .provider_protocol import NormalizedTokenUsage


class CostBreakdown(BaseModel):
    input_cost_usd: Decimal = Decimal("0")
    cached_input_cost_usd: Decimal = Decimal("0")
    output_cost_usd: Decimal = Decimal("0")
    total_cost_usd: Decimal = Decimal("0")


class UsageRecord(BaseModel):
    provider_id: str
    model_key: str
    provider_model_id: str
    request_id: str | None = None
    project_id: str | None = None
    run_id: str | None = None
    task_id: str | None = None
    agent_name: str | None = None
    usage: NormalizedTokenUsage = Field(
        default_factory=NormalizedTokenUsage
    )
    cost: CostBreakdown = Field(
        default_factory=CostBreakdown
    )
    metadata: dict = Field(default_factory=dict)


class UsageSummary(BaseModel):
    request_count: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: Decimal = Decimal("0")


class CostCalculator:
    MILLION = Decimal("1000000")
    PRECISION = Decimal("0.00000001")

    def calculate(
        self,
        *,
        usage: NormalizedTokenUsage,
        pricing: ModelPricing,
    ) -> CostBreakdown:
        normal_input_tokens = max(
            usage.input_tokens
            - usage.cached_input_tokens,
            0,
        )

        input_cost = self._token_cost(
            normal_input_tokens,
            pricing.input_usd_per_million_tokens,
        )
        cached_cost = self._token_cost(
            usage.cached_input_tokens,
            pricing.cached_input_usd_per_million_tokens,
        )
        output_cost = self._token_cost(
            usage.output_tokens,
            pricing.output_usd_per_million_tokens,
        )

        total = (
            input_cost
            + cached_cost
            + output_cost
        ).quantize(
            self.PRECISION,
            rounding=ROUND_HALF_UP,
        )

        return CostBreakdown(
            input_cost_usd=input_cost,
            cached_input_cost_usd=cached_cost,
            output_cost_usd=output_cost,
            total_cost_usd=total,
        )

    def _token_cost(
        self,
        token_count: int,
        price_per_million: float,
    ) -> Decimal:
        value = (
            Decimal(token_count)
            * Decimal(str(price_per_million))
            / self.MILLION
        )

        return value.quantize(
            self.PRECISION,
            rounding=ROUND_HALF_UP,
        )


class UsageAccumulator:
    def __init__(self) -> None:
        self._records: list[UsageRecord] = []

    def add(
        self,
        record: UsageRecord,
    ) -> None:
        self._records.append(record)

    def records(self) -> list[UsageRecord]:
        return list(self._records)

    def summarize(
        self,
        *,
        project_id: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
        provider_id: str | None = None,
        model_key: str | None = None,
    ) -> UsageSummary:
        records = self._filtered(
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            provider_id=provider_id,
            model_key=model_key,
        )

        return UsageSummary(
            request_count=len(records),
            input_tokens=sum(
                item.usage.input_tokens
                for item in records
            ),
            cached_input_tokens=sum(
                item.usage.cached_input_tokens
                for item in records
            ),
            output_tokens=sum(
                item.usage.output_tokens
                for item in records
            ),
            reasoning_tokens=sum(
                item.usage.reasoning_tokens
                for item in records
            ),
            total_tokens=sum(
                item.usage.total_tokens
                for item in records
            ),
            total_cost_usd=sum(
                (
                    item.cost.total_cost_usd
                    for item in records
                ),
                Decimal("0"),
            ),
        )

    def _filtered(
        self,
        *,
        project_id: str | None,
        run_id: str | None,
        task_id: str | None,
        provider_id: str | None,
        model_key: str | None,
    ) -> list[UsageRecord]:
        result: list[UsageRecord] = []

        for record in self._records:
            if (
                project_id is not None
                and record.project_id != project_id
            ):
                continue

            if (
                run_id is not None
                and record.run_id != run_id
            ):
                continue

            if (
                task_id is not None
                and record.task_id != task_id
            ):
                continue

            if (
                provider_id is not None
                and record.provider_id != provider_id
            ):
                continue

            if (
                model_key is not None
                and record.model_key != model_key
            ):
                continue

            result.append(record)

        return result
