import asyncio

from af_core.runtime.benchmark_models import (
    BenchmarkScenario,
    BenchmarkStatus,
    BenchmarkTaskType,
)
from af_core.runtime.benchmark_runner import BenchmarkRunner
from af_core.runtime.model_registry import (
    ModelPricing,
    ModelTier,
    RegisteredModel,
)
from af_core.runtime.provider_protocol import (
    NormalizedTokenUsage,
    ProviderCapability,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderResponse,
)


class MockProvider:
    @property
    def provider_id(self) -> str:
        return "mock"

    @property
    def capabilities(self):
        return {
            ProviderCapability.TEXT,
        }

    async def complete(
        self,
        *,
        messages,
        model_id,
        parameters=None,
    ):
        return ProviderResponse(
            provider_id="mock",
            model_id=model_id,
            content="AF-CORE-OK",
            usage=NormalizedTokenUsage(
                input_tokens=100,
                output_tokens=50,
            ),
        )

    async def structured(self, **kwargs):
        raise NotImplementedError

    async def health(self):
        return ProviderHealth(
            provider_id="mock",
            status=ProviderHealthStatus.HEALTHY,
        )


class FailingProvider(MockProvider):
    async def complete(self, **kwargs):
        raise RuntimeError("provider failed")


def model() -> RegisteredModel:
    return RegisteredModel(
        model_key="mock-model",
        provider_id="mock",
        provider_model_id="mock-model-id",
        display_name="Mock Model",
        tier=ModelTier.STANDARD,
        pricing=ModelPricing(
            input_usd_per_million_tokens=1,
            output_usd_per_million_tokens=2,
        ),
    )


def scenario() -> BenchmarkScenario:
    return BenchmarkScenario(
        scenario_id="scenario-1",
        name="Exact response",
        task_type=BenchmarkTaskType.STRUCTURED_OUTPUT,
        prompt="Reply exactly.",
        expected_output="AF-CORE-OK",
        required_keywords={"AF-CORE"},
    )


def test_runner_records_success_usage_and_cost() -> None:
    result = asyncio.run(
        BenchmarkRunner().run(
            scenario=scenario(),
            provider=MockProvider(),
            model=model(),
        )
    )

    assert result.status is BenchmarkStatus.PASSED
    assert result.quality.aggregate() == 100.0
    assert result.execution.input_tokens == 100
    assert result.execution.output_tokens == 50
    assert result.execution.cost_usd > 0


def test_runner_records_provider_error() -> None:
    result = asyncio.run(
        BenchmarkRunner().run(
            scenario=scenario(),
            provider=FailingProvider(),
            model=model(),
        )
    )

    assert result.status is BenchmarkStatus.ERROR
    assert result.error == "provider failed"


def test_run_many_executes_all_scenarios() -> None:
    runner = BenchmarkRunner()

    results = asyncio.run(
        runner.run_many(
            scenarios=[
                scenario(),
                scenario().model_copy(
                    update={
                        "scenario_id": "scenario-2",
                    }
                ),
            ],
            provider=MockProvider(),
            model=model(),
        )
    )

    assert len(results) == 2
    assert all(
        result.status is BenchmarkStatus.PASSED
        for result in results
    )
