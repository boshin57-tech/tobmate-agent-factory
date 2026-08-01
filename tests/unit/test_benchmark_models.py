from af_core.runtime.benchmark_models import (
    BenchmarkExecutionMetrics,
    QualityMetrics,
    RecommendationWeights,
)


def test_quality_metrics_apply_penalties() -> None:
    metrics = QualityMetrics(
        correctness_score=100,
        structure_score=100,
        tool_success_score=100,
        test_pass_score=100,
        review_score=100,
        retry_penalty=10,
        hallucination_penalty=5,
    )

    assert metrics.aggregate() == 85.0


def test_execution_metrics_calculate_throughput() -> None:
    metrics = BenchmarkExecutionMetrics(
        latency_ms=2000,
        output_tokens=100,
    )

    assert metrics.total_tokens == 100
    assert metrics.tokens_per_second == 50.0


def test_recommendation_weights_must_total_one() -> None:
    RecommendationWeights().validate_total()

    invalid = RecommendationWeights(
        quality=0.5,
        cost=0.5,
        latency=0.5,
        health=0,
        success_rate=0,
    )

    try:
        invalid.validate_total()
    except ValueError as exc:
        assert "must total 1.0" in str(exc)
    else:
        raise AssertionError(
            "Invalid recommendation weights were accepted"
        )
