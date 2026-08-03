from __future__ import annotations

from af_core.capability.capability_models import (
    AgentCapability,
)
from af_core.organization import (
    AgentAvailabilityStatus,
    AgentRuntimeMetrics,
    AgentRuntimeMetricsRepository,
    DynamicRoleAssignmentEngine,
    DynamicRoleRequirement,
    RoleAssignmentRequest,
    RuntimeAgentScorer,
)


def agents() -> tuple[
    AgentCapability,
    ...
]:
    return (
        AgentCapability(
            agent_id="expert-overloaded",
            agent_name="Expert Overloaded",
            capabilities=[
                "sui_move",
                "smart_contract",
            ],
            supported_tasks=[
                "contract_implementation",
            ],
            skill_level=5,
        ),
        AgentCapability(
            agent_id="available-agent",
            agent_name="Available Agent",
            capabilities=[
                "sui_move",
                "smart_contract",
            ],
            supported_tasks=[
                "contract_implementation",
            ],
            skill_level=4,
        ),
        AgentCapability(
            agent_id="offline-agent",
            agent_name="Offline Agent",
            capabilities=[
                "sui_move",
                "smart_contract",
            ],
            supported_tasks=[
                "contract_implementation",
            ],
            skill_level=5,
        ),
    )


def request() -> RoleAssignmentRequest:
    return RoleAssignmentRequest(
        team_id="team-001",
        workspace_id=(
            "blockchain-workspace"
        ),
        requirement=(
            DynamicRoleRequirement(
                role_name="Move Developer",
                required_capabilities={
                    "sui_move",
                    "smart_contract",
                },
                required_tasks={
                    "contract_implementation",
                },
                minimum_skill_level=4,
            )
        ),
        requested_by="manager-agent",
    )


def runtime_repository(
) -> AgentRuntimeMetricsRepository:
    repository = (
        AgentRuntimeMetricsRepository()
    )

    repository.upsert(
        AgentRuntimeMetrics(
            agent_id="expert-overloaded",
            availability=(
                AgentAvailabilityStatus.BUSY
            ),
            current_assignments=4,
            maximum_assignments=5,
            workload_ratio=0.95,
            success_rate=0.80,
            quality_score=80,
            reliability_score=78,
            average_response_ms=3000,
            consecutive_failures=2,
        )
    )

    repository.upsert(
        AgentRuntimeMetrics(
            agent_id="available-agent",
            availability=(
                AgentAvailabilityStatus
                .AVAILABLE
            ),
            current_assignments=1,
            maximum_assignments=5,
            workload_ratio=0.25,
            success_rate=0.98,
            quality_score=96,
            reliability_score=99,
            average_response_ms=400,
            consecutive_failures=0,
        )
    )

    repository.upsert(
        AgentRuntimeMetrics(
            agent_id="offline-agent",
            availability=(
                AgentAvailabilityStatus.OFFLINE
            ),
            current_assignments=0,
            maximum_assignments=5,
            workload_ratio=0.0,
            success_rate=1.0,
            quality_score=100,
            reliability_score=100,
        )
    )

    return repository


def test_available_agent_can_beat_higher_skill_overloaded_agent():

    engine = DynamicRoleAssignmentEngine(
        agent_provider=agents,
        runtime_repository=(
            runtime_repository()
        ),
        require_runtime_metrics=True,
    )

    result = engine.assign(
        request()
    )

    assert result.fulfilled

    assert (
        result.assignments[0].agent_id
        == "available-agent"
    )

    evaluations = {
        candidate.agent_id:
            candidate
        for candidate
        in result.candidates
    }

    assert (
        evaluations[
            "available-agent"
        ].runtime_score
        >
        evaluations[
            "expert-overloaded"
        ].runtime_score
    )

    assert (
        evaluations[
            "available-agent"
        ].score
        >
        evaluations[
            "expert-overloaded"
        ].score
    )


def test_offline_agent_is_runtime_ineligible():

    engine = DynamicRoleAssignmentEngine(
        agent_provider=agents,
        runtime_repository=(
            runtime_repository()
        ),
        require_runtime_metrics=True,
    )

    result = engine.assign(
        request()
    )

    evaluations = {
        candidate.agent_id:
            candidate
        for candidate
        in result.candidates
    }

    offline = evaluations[
        "offline-agent"
    ]

    assert not offline.eligible

    assert (
        "agent runtime status is offline"
        in offline.rejection_reasons
    )


def test_missing_required_runtime_metrics_rejects_agent():

    engine = DynamicRoleAssignmentEngine(
        agent_provider=agents,
        require_runtime_metrics=True,
    )

    result = engine.assign(
        request()
    )

    assert not result.fulfilled

    assert result.assignments == []

    assert all(
        (
            "runtime metrics are required "
            "but unavailable"
        )
        in candidate.rejection_reasons
        for candidate in result.candidates
    )


def test_runtime_metrics_are_optional_by_default():

    engine = DynamicRoleAssignmentEngine(
        agent_provider=agents
    )

    result = engine.assign(
        request()
    )

    assert result.fulfilled

    assert (
        result.assignments[0].agent_id
        in {
            "expert-overloaded",
            "offline-agent",
        }
    )

    assert all(
        not candidate
        .runtime_metrics_available
        for candidate in result.candidates
    )


def test_runtime_scorer_rejects_full_capacity():

    scorer = RuntimeAgentScorer()

    result = scorer.score(
        AgentRuntimeMetrics(
            agent_id="full-agent",
            current_assignments=3,
            maximum_assignments=3,
            workload_ratio=1.0,
        )
    )

    assert not result.eligible

    assert (
        "agent has no remaining runtime capacity"
        in result.reasons
    )


def test_degraded_agent_receives_penalty():

    scorer = RuntimeAgentScorer()

    available = scorer.score(
        AgentRuntimeMetrics(
            agent_id="available-agent",
            availability=(
                AgentAvailabilityStatus.AVAILABLE
            ),
            current_assignments=0,
            maximum_assignments=2,
            workload_ratio=0.2,
        )
    )

    degraded = scorer.score(
        AgentRuntimeMetrics(
            agent_id="degraded-agent",
            availability=(
                AgentAvailabilityStatus.DEGRADED
            ),
            current_assignments=0,
            maximum_assignments=2,
            workload_ratio=0.2,
        )
    )

    assert available.eligible
    assert degraded.eligible

    assert (
        degraded.penalty_score
        > available.penalty_score
    )

    assert (
        available.total_score
        > degraded.total_score
    )


def test_runtime_metrics_can_be_updated_through_engine():

    engine = DynamicRoleAssignmentEngine(
        agent_provider=agents
    )

    metrics = AgentRuntimeMetrics(
        agent_id="available-agent",
        workload_ratio=0.2,
        current_assignments=0,
        maximum_assignments=3,
    )

    stored = engine.update_runtime_metrics(
        metrics
    )

    loaded = engine.runtime_metrics(
        "available-agent"
    )

    assert stored == metrics
    assert loaded == metrics
