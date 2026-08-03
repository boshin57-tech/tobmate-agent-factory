from __future__ import annotations

from af_core.organization import (
    CoordinatedTask,
    TaskAgentAvailability,
    TaskAgentRuntimeProfile,
    TaskWorkloadBalancingEngine,
)


def make_task() -> CoordinatedTask:
    return CoordinatedTask(
        task_id="move-implementation",
        workflow_id="workflow-001",
        title="Implement Move module",
        description=(
            "Implement and test a governed "
            "Sui Move module"
        ),
        required_capabilities={
            "sui_move",
            "smart_contract",
        },
        required_tasks={
            "contract_implementation",
        },
    )


def profile(
    agent_id: str,
    *,
    capabilities: set[str] | None = None,
    supported_tasks: set[str] | None = None,
    availability: TaskAgentAvailability = (
        TaskAgentAvailability.AVAILABLE
    ),
    current_task_count: int = 0,
    maximum_task_count: int = 4,
    workload_ratio: float = 0.0,
    success_rate: float = 1.0,
    quality_score: float = 100.0,
    reliability_score: float = 100.0,
    consecutive_failures: int = 0,
) -> TaskAgentRuntimeProfile:
    return TaskAgentRuntimeProfile(
        agent_id=agent_id,
        capabilities=(
            capabilities
            if capabilities is not None
            else {
                "sui_move",
                "smart_contract",
            }
        ),
        supported_tasks=(
            supported_tasks
            if supported_tasks is not None
            else {
                "contract_implementation",
            }
        ),
        availability=availability,
        current_task_count=(
            current_task_count
        ),
        maximum_task_count=(
            maximum_task_count
        ),
        workload_ratio=workload_ratio,
        success_rate=success_rate,
        quality_score=quality_score,
        reliability_score=(
            reliability_score
        ),
        consecutive_failures=(
            consecutive_failures
        ),
    )


def test_capability_matching_agent_is_selected():
    agents = [
        profile(
            "documentation-agent",
            capabilities={
                "documentation",
            },
            supported_tasks={
                "technical_writing",
            },
        ),
        profile(
            "move-agent",
        ),
    ]

    engine = TaskWorkloadBalancingEngine(
        agent_provider=lambda: agents
    )

    result = engine.select_agent(
        task=make_task()
    )

    assert result.fulfilled

    assert (
        result.selected_agent_id
        == "move-agent"
    )

    assert result.eligible_agent_ids == [
        "move-agent"
    ]


def test_lower_workload_agent_is_preferred():
    agents = [
        profile(
            "busy-agent",
            current_task_count=3,
            maximum_task_count=4,
            workload_ratio=0.75,
        ),
        profile(
            "available-agent",
            current_task_count=1,
            maximum_task_count=4,
            workload_ratio=0.25,
        ),
    ]

    engine = TaskWorkloadBalancingEngine(
        agent_provider=lambda: agents
    )

    result = engine.select_agent(
        task=make_task()
    )

    assert (
        result.selected_agent_id
        == "available-agent"
    )

    assert (
        result.ranked_candidates[0]
        .total_score
        > result.ranked_candidates[1]
        .total_score
    )


def test_offline_agent_is_excluded():
    agents = [
        profile(
            "offline-agent",
            availability=(
                TaskAgentAvailability
                .OFFLINE
            ),
        ),
        profile(
            "online-agent",
        ),
    ]

    engine = TaskWorkloadBalancingEngine(
        agent_provider=lambda: agents
    )

    result = engine.select_agent(
        task=make_task()
    )

    assert (
        result.selected_agent_id
        == "online-agent"
    )

    offline_score = next(
        score
        for score in result.ranked_candidates
        if score.agent_id
        == "offline-agent"
    )

    assert not offline_score.eligible


def test_overloaded_agent_is_excluded():
    agents = [
        profile(
            "overloaded-agent",
            availability=(
                TaskAgentAvailability
                .OVERLOADED
            ),
            current_task_count=4,
            maximum_task_count=4,
            workload_ratio=1.0,
        ),
        profile(
            "replacement-agent",
        ),
    ]

    engine = TaskWorkloadBalancingEngine(
        agent_provider=lambda: agents
    )

    result = engine.select_agent(
        task=make_task()
    )

    assert (
        result.selected_agent_id
        == "replacement-agent"
    )


def test_explicitly_excluded_agent_is_not_selected():
    agents = [
        profile(
            "highest-score-agent",
            workload_ratio=0.0,
        ),
        profile(
            "second-agent",
            workload_ratio=0.2,
        ),
    ]

    engine = TaskWorkloadBalancingEngine(
        agent_provider=lambda: agents
    )

    result = engine.select_agent(
        task=make_task(),
        excluded_agent_ids={
            "highest-score-agent"
        },
    )

    assert (
        result.selected_agent_id
        == "second-agent"
    )

    excluded_score = next(
        score
        for score in result.ranked_candidates
        if score.agent_id
        == "highest-score-agent"
    )

    assert not excluded_score.eligible

    assert (
        "Agent explicitly excluded"
        in excluded_score.reasons
    )


def test_missing_capability_prevents_assignment():
    agents = [
        profile(
            "partial-agent",
            capabilities={
                "sui_move",
            },
        )
    ]

    engine = TaskWorkloadBalancingEngine(
        agent_provider=lambda: agents
    )

    result = engine.select_agent(
        task=make_task()
    )

    assert not result.fulfilled
    assert result.selected_agent_id is None

    score = result.ranked_candidates[0]

    assert not score.eligible

    assert score.missing_capabilities == {
        "smart_contract"
    }


def test_low_reliability_agent_is_excluded():
    agents = [
        profile(
            "unreliable-agent",
            reliability_score=20.0,
        ),
        profile(
            "reliable-agent",
            reliability_score=95.0,
        ),
    ]

    engine = TaskWorkloadBalancingEngine(
        agent_provider=lambda: agents
    )

    result = engine.select_agent(
        task=make_task()
    )

    assert (
        result.selected_agent_id
        == "reliable-agent"
    )


def test_repeated_failures_reduce_agent_score():
    agents = [
        profile(
            "failing-agent",
            consecutive_failures=5,
        ),
        profile(
            "stable-agent",
            consecutive_failures=0,
            workload_ratio=0.1,
        ),
    ]

    engine = TaskWorkloadBalancingEngine(
        agent_provider=lambda: agents
    )

    result = engine.select_agent(
        task=make_task()
    )

    failing = next(
        score
        for score in result.ranked_candidates
        if score.agent_id
        == "failing-agent"
    )

    stable = next(
        score
        for score in result.ranked_candidates
        if score.agent_id
        == "stable-agent"
    )

    assert (
        stable.total_score
        > failing.total_score
    )
