from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from decimal import Decimal
from uuid import uuid4

from .benchmark_models import (
    BenchmarkExecutionMetrics,
    BenchmarkResult,
    BenchmarkScenario,
    BenchmarkStatus,
    QualityMetrics,
)
from .model_registry import RegisteredModel
from .provider_protocol import (
    ProviderAdapter,
    ProviderMessage,
)
from .usage import CostCalculator


QualityEvaluator = Callable[
    [BenchmarkScenario, str | None],
    QualityMetrics,
]


class BenchmarkRunner:
    def __init__(
        self,
        *,
        cost_calculator: CostCalculator | None = None,
        quality_evaluator: QualityEvaluator | None = None,
    ) -> None:
        self.cost_calculator = (
            cost_calculator or CostCalculator()
        )
        self.quality_evaluator = (
            quality_evaluator
            or self._default_quality_evaluator
        )

    async def run(
        self,
        *,
        scenario: BenchmarkScenario,
        provider: ProviderAdapter,
        model: RegisteredModel,
        messages: Sequence[ProviderMessage] | None = None,
        parameters: dict | None = None,
    ) -> BenchmarkResult:
        request_messages = list(
            messages
            or [
                ProviderMessage(
                    role="user",
                    content=scenario.prompt,
                )
            ]
        )

        started = time.perf_counter()

        try:
            response = await provider.complete(
                messages=request_messages,
                model_id=model.provider_model_id,
                parameters=parameters,
            )

            latency_ms = (
                time.perf_counter() - started
            ) * 1000.0

            quality = self.quality_evaluator(
                scenario,
                response.content,
            )

            cost = self.cost_calculator.calculate(
                usage=response.usage,
                pricing=model.pricing,
            )

            status = self._status_for(
                scenario=scenario,
                response_text=response.content,
                quality=quality,
                latency_ms=latency_ms,
                cost_usd=cost.total_cost_usd,
            )

            return BenchmarkResult(
                benchmark_id=f"bench_{uuid4().hex}",
                scenario_id=scenario.scenario_id,
                task_type=scenario.task_type,
                provider_id=model.provider_id,
                model_key=model.model_key,
                provider_model_id=model.provider_model_id,
                status=status,
                quality=quality,
                execution=BenchmarkExecutionMetrics(
                    latency_ms=latency_ms,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    reasoning_tokens=(
                        response.usage.reasoning_tokens
                    ),
                    cost_usd=cost.total_cost_usd,
                ),
                response_text=response.content,
                metadata={
                    "request_id": response.request_id,
                    "provider_metadata": response.metadata,
                },
            )

        except Exception as exc:
            latency_ms = (
                time.perf_counter() - started
            ) * 1000.0

            return BenchmarkResult(
                benchmark_id=f"bench_{uuid4().hex}",
                scenario_id=scenario.scenario_id,
                task_type=scenario.task_type,
                provider_id=model.provider_id,
                model_key=model.model_key,
                provider_model_id=model.provider_model_id,
                status=BenchmarkStatus.ERROR,
                execution=BenchmarkExecutionMetrics(
                    latency_ms=latency_ms,
                ),
                error=str(exc),
            )

    async def run_many(
        self,
        *,
        scenarios: Sequence[BenchmarkScenario],
        provider: ProviderAdapter,
        model: RegisteredModel,
        parameters: dict | None = None,
    ) -> list[BenchmarkResult]:
        results: list[BenchmarkResult] = []

        for scenario in scenarios:
            results.append(
                await self.run(
                    scenario=scenario,
                    provider=provider,
                    model=model,
                    parameters=parameters,
                )
            )

        return results

    def _status_for(
        self,
        *,
        scenario: BenchmarkScenario,
        response_text: str | None,
        quality: QualityMetrics,
        latency_ms: float,
        cost_usd: Decimal,
    ) -> BenchmarkStatus:
        if response_text is None:
            return BenchmarkStatus.FAILED

        if quality.aggregate() <= 0:
            return BenchmarkStatus.FAILED

        if (
            scenario.maximum_latency_ms is not None
            and latency_ms > scenario.maximum_latency_ms
        ):
            return BenchmarkStatus.FAILED

        if (
            scenario.maximum_cost_usd is not None
            and cost_usd > scenario.maximum_cost_usd
        ):
            return BenchmarkStatus.FAILED

        return BenchmarkStatus.PASSED

    def _default_quality_evaluator(
        self,
        scenario: BenchmarkScenario,
        response_text: str | None,
    ) -> QualityMetrics:
        if response_text is None:
            return QualityMetrics()

        lowered = response_text.lower()

        required_passed = all(
            keyword.lower() in lowered
            for keyword in scenario.required_keywords
        )
        forbidden_absent = all(
            keyword.lower() not in lowered
            for keyword in scenario.forbidden_keywords
        )

        correctness = 100.0

        if scenario.expected_output is not None:
            correctness = (
                100.0
                if response_text.strip()
                == scenario.expected_output.strip()
                else 0.0
            )

        if not required_passed or not forbidden_absent:
            correctness = 0.0

        structure = 100.0

        if scenario.expected_json is not None:
            try:
                parsed = json.loads(response_text)
            except json.JSONDecodeError:
                structure = 0.0
            else:
                structure = (
                    100.0
                    if parsed == scenario.expected_json
                    else 0.0
                )

        return QualityMetrics(
            correctness_score=correctness,
            structure_score=structure,
            tool_success_score=100.0,
            test_pass_score=100.0,
            review_score=100.0,
        )
