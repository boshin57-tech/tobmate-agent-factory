from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BenchmarkTaskType(StrEnum):
    PLANNING = "PLANNING"
    CODING = "CODING"
    TESTING = "TESTING"
    REVIEW = "REVIEW"
    CLASSIFICATION = "CLASSIFICATION"
    SUMMARIZATION = "SUMMARIZATION"
    STRUCTURED_OUTPUT = "STRUCTURED_OUTPUT"
    TOOL_USE = "TOOL_USE"
    REPOSITORY_ANALYSIS = "REPOSITORY_ANALYSIS"


class BenchmarkStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


class BenchmarkScenario(BaseModel):
    scenario_id: str
    name: str
    task_type: BenchmarkTaskType
    prompt: str
    expected_output: str | None = None
    expected_json: dict[str, Any] | None = None
    maximum_latency_ms: float | None = Field(
        default=None,
        gt=0,
    )
    maximum_cost_usd: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
    )
    required_keywords: set[str] = Field(
        default_factory=set
    )
    forbidden_keywords: set[str] = Field(
        default_factory=set
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict
    )


class QualityMetrics(BaseModel):
    correctness_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
    )
    structure_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
    )
    tool_success_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
    )
    test_pass_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
    )
    review_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
    )
    retry_penalty: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
    )
    hallucination_penalty: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
    )

    def aggregate(self) -> float:
        positive = (
            self.correctness_score * 0.40
            + self.structure_score * 0.15
            + self.tool_success_score * 0.15
            + self.test_pass_score * 0.15
            + self.review_score * 0.15
        )

        penalty = (
            self.retry_penalty
            + self.hallucination_penalty
        )

        return round(
            max(
                min(positive - penalty, 100.0),
                0.0,
            ),
            4,
        )


class BenchmarkExecutionMetrics(BaseModel):
    latency_ms: float = Field(
        default=0.0,
        ge=0.0,
    )
    input_tokens: int = Field(
        default=0,
        ge=0,
    )
    output_tokens: int = Field(
        default=0,
        ge=0,
    )
    reasoning_tokens: int = Field(
        default=0,
        ge=0,
    )
    cost_usd: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("0"),
    )
    retry_count: int = Field(
        default=0,
        ge=0,
    )
    tool_call_count: int = Field(
        default=0,
        ge=0,
    )

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def tokens_per_second(self) -> float:
        if self.latency_ms <= 0:
            return 0.0

        return round(
            self.output_tokens
            / (self.latency_ms / 1000.0),
            4,
        )


class BenchmarkResult(BaseModel):
    benchmark_id: str
    scenario_id: str
    task_type: BenchmarkTaskType
    provider_id: str
    model_key: str
    provider_model_id: str
    status: BenchmarkStatus
    quality: QualityMetrics = Field(
        default_factory=QualityMetrics
    )
    execution: BenchmarkExecutionMetrics = Field(
        default_factory=BenchmarkExecutionMetrics
    )
    response_text: str | None = None
    error: str | None = None
    created_at: datetime = Field(
        default_factory=utc_now
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict
    )


class BenchmarkAggregate(BaseModel):
    provider_id: str
    model_key: str
    task_type: BenchmarkTaskType
    sample_count: int = Field(
        default=0,
        ge=0,
    )
    success_count: int = Field(
        default=0,
        ge=0,
    )
    failure_count: int = Field(
        default=0,
        ge=0,
    )
    success_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
    )
    average_quality_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
    )
    average_latency_ms: float = Field(
        default=0.0,
        ge=0.0,
    )
    average_cost_usd: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("0"),
    )
    average_retry_count: float = Field(
        default=0.0,
        ge=0.0,
    )
    average_tokens_per_second: float = Field(
        default=0.0,
        ge=0.0,
    )


class RecommendationWeights(BaseModel):
    quality: float = Field(
        default=0.45,
        ge=0.0,
        le=1.0,
    )
    cost: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
    )
    latency: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
    )
    health: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
    )
    success_rate: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
    )

    def validate_total(self) -> None:
        total = (
            self.quality
            + self.cost
            + self.latency
            + self.health
            + self.success_rate
        )

        if abs(total - 1.0) > 0.000001:
            raise ValueError(
                "Recommendation weights must total 1.0; "
                f"received {total:.6f}"
            )


class RecommendationCandidate(BaseModel):
    rank: int
    provider_id: str
    model_key: str
    task_type: BenchmarkTaskType
    final_score: float = Field(
        ge=0.0,
        le=100.0,
    )
    quality_score: float = Field(
        ge=0.0,
        le=100.0,
    )
    cost_score: float = Field(
        ge=0.0,
        le=100.0,
    )
    latency_score: float = Field(
        ge=0.0,
        le=100.0,
    )
    health_score: float = Field(
        ge=0.0,
        le=100.0,
    )
    success_rate_score: float = Field(
        ge=0.0,
        le=100.0,
    )
    reasons: list[str] = Field(
        default_factory=list
    )


class ModelRecommendation(BaseModel):
    task_type: BenchmarkTaskType
    recommended_model_key: str | None = None
    recommended_provider_id: str | None = None
    candidates: list[RecommendationCandidate] = Field(
        default_factory=list
    )
    generated_at: datetime = Field(
        default_factory=utc_now
    )
