from __future__ import annotations

import pytest

from af_core.orchestrator.coordination_models import (
    CoordinationAgent,
    CoordinationAgentStatus,
    CoordinationTask,
    CoordinationTaskStatus,
)
from af_core.orchestrator.coordination_registry import (
    CoordinationRegistry,
    CoordinationRegistryError,
)
from af_core.orchestrator.team_formation import (
    TeamFormationEngine,
    TeamFormationError,
)


def agent(
    agent_id: str,
    *capabilities: str,
    maximum_parallel_tasks: int = 1,
    status: CoordinationAgentStatus = (
        CoordinationAgentStatus.ACTIVE
    ),
) -> CoordinationAgent:
    return CoordinationAgent(
        agent_id=agent_id,
        name=agent_id,
        role="specialist",
        capability_ids=frozenset(capabilities),
        maximum_parallel_tasks=maximum_parallel_tasks,
        status=status,
    )


def task(
    task_id: str,
    *capabilities: str,
    dependencies: frozenset[str] = frozenset(),
    priority: int = 0,
) -> CoordinationTask:
    return CoordinationTask(
        task_id=task_id,
        name=task_id,
        required_capability_ids=frozenset(capabilities),
        dependency_ids=dependencies,
        priority=priority,
    )


def test_registry_registers_agents_and_tasks() -> None:
    registry = CoordinationRegistry()

    registered_agent = registry.register_agent(
        agent("agent-1", "code")
    )
    registered_task = registry.register_task(
        task("task-1", "code")
    )

    assert registry.get_agent("agent-1") == registered_agent
    assert registry.get_task("task-1") == registered_task


def test_registry_rejects_duplicate_agent() -> None:
    registry = CoordinationRegistry()
    value = agent("agent-1", "code")

    registry.register_agent(value)

    with pytest.raises(
        CoordinationRegistryError,
        match="already registered",
    ):
        registry.register_agent(value)


def test_registry_rejects_unknown_dependency() -> None:
    registry = CoordinationRegistry()

    with pytest.raises(
        CoordinationRegistryError,
        match="Unknown task dependencies",
    ):
        registry.register_task(
            task(
                "task-2",
                "review",
                dependencies=frozenset({"task-1"}),
            )
        )


def test_dependency_completion_is_detected() -> None:
    registry = CoordinationRegistry()

    registry.register_task(task("task-1", "code"))
    registry.register_task(
        task(
            "task-2",
            "review",
            dependencies=frozenset({"task-1"}),
        )
    )

    assert not registry.task_dependencies_completed(
        "task-2"
    )

    completed = registry.get_task("task-1").model_copy(
        update={
            "status": CoordinationTaskStatus.COMPLETED
        }
    )
    registry.update_task(completed)

    assert registry.task_dependencies_completed("task-2")


def test_team_formation_selects_capability_coverage() -> None:
    registry = CoordinationRegistry()
    registry.register_agent(
        agent("agent-code", "code")
    )
    registry.register_agent(
        agent("agent-review", "review")
    )

    target = task("task-1", "code", "review")
    registry.register_task(target)

    result = TeamFormationEngine(
        registry=registry
    ).form_team(target)

    assert result.complete is True
    assert set(result.selected_agent_ids) == {
        "agent-code",
        "agent-review",
    }


def test_team_formation_prefers_broad_candidate() -> None:
    registry = CoordinationRegistry()
    registry.register_agent(
        agent("agent-a", "code")
    )
    registry.register_agent(
        agent("agent-b", "code", "review")
    )

    target = task("task-1", "code", "review")
    registry.register_task(target)

    result = TeamFormationEngine(
        registry=registry
    ).form_team(target)

    assert result.selected_agent_ids == ("agent-b",)


def test_team_formation_reports_uncovered_capability() -> None:
    registry = CoordinationRegistry()
    registry.register_agent(
        agent("agent-code", "code")
    )

    target = task("task-1", "code", "security")
    registry.register_task(target)

    result = TeamFormationEngine(
        registry=registry
    ).form_team(target)

    assert result.complete is False
    assert result.uncovered_capability_ids == frozenset(
        {"security"}
    )


def test_complete_team_requirement_raises() -> None:
    registry = CoordinationRegistry()
    registry.register_agent(
        agent("agent-code", "code")
    )

    target = task("task-1", "code", "security")
    registry.register_task(target)

    with pytest.raises(
        TeamFormationError,
        match="Unable to cover",
    ):
        TeamFormationEngine(
            registry=registry
        ).require_complete_team(target)


def test_offline_agent_is_not_selected() -> None:
    registry = CoordinationRegistry()
    registry.register_agent(
        agent(
            "agent-offline",
            "code",
            status=CoordinationAgentStatus.OFFLINE,
        )
    )

    target = task("task-1", "code")
    registry.register_task(target)

    result = TeamFormationEngine(
        registry=registry
    ).form_team(target)

    assert result.selected_agent_ids == ()

from af_core.orchestrator.coordination_engine import (
    CoordinationEngine,
    CoordinationEngineError,
)
from af_core.orchestrator.coordination_models import (
    CoordinationConflictType,
    CoordinationDecision,
)


def coordination_fixture() -> tuple[
    CoordinationRegistry,
    CoordinationEngine,
]:
    registry = CoordinationRegistry()
    registry.register_agent(
        agent(
            "agent-1",
            "code",
            maximum_parallel_tasks=1,
        )
    )
    registry.register_agent(
        agent(
            "agent-2",
            "review",
            maximum_parallel_tasks=1,
        )
    )
    registry.register_task(
        task("task-1", "code")
    )

    return registry, CoordinationEngine(
        registry=registry
    )


def test_task_assignment_succeeds() -> None:
    registry, engine = coordination_fixture()

    assignment = engine.assign(
        task_id="task-1",
        agent_id="agent-1",
    )

    assigned = registry.get_task("task-1")

    assert assignment.decision is (
        CoordinationDecision.ASSIGN
    )
    assert assigned.status is (
        CoordinationTaskStatus.ASSIGNED
    )
    assert assigned.assigned_agent_id == "agent-1"


def test_duplicate_assignment_creates_conflict() -> None:
    _, engine = coordination_fixture()

    engine.assign(
        task_id="task-1",
        agent_id="agent-1",
    )
    blocked = engine.assign(
        task_id="task-1",
        agent_id="agent-2",
    )

    assert blocked.decision is (
        CoordinationDecision.BLOCK
    )
    assert engine.conflicts()[0].conflict_type is (
        CoordinationConflictType.DUPLICATE_ASSIGNMENT
    )


def test_capability_mismatch_blocks_assignment() -> None:
    _, engine = coordination_fixture()

    blocked = engine.assign(
        task_id="task-1",
        agent_id="agent-2",
    )

    assert blocked.decision is (
        CoordinationDecision.BLOCK
    )
    assert engine.conflicts()[0].conflict_type is (
        CoordinationConflictType.CAPABILITY_MISMATCH
    )


def test_agent_capacity_conflict() -> None:
    registry, engine = coordination_fixture()

    registry.register_task(
        task("task-2", "code")
    )

    first = engine.assign(
        task_id="task-1",
        agent_id="agent-1",
    )
    second = engine.assign(
        task_id="task-2",
        agent_id="agent-1",
    )

    assert first.decision is (
        CoordinationDecision.ASSIGN
    )
    assert second.decision is (
        CoordinationDecision.BLOCK
    )
    assert engine.conflicts()[-1].conflict_type is (
        CoordinationConflictType.RESOURCE_CONFLICT
    )


def test_dependency_blocks_assignment() -> None:
    registry = CoordinationRegistry()
    registry.register_agent(
        agent("agent-1", "review")
    )
    registry.register_task(
        task("task-parent", "code")
    )
    registry.register_task(
        task(
            "task-child",
            "review",
            dependencies=frozenset(
                {"task-parent"}
            ),
        )
    )

    engine = CoordinationEngine(
        registry=registry
    )

    blocked = engine.assign(
        task_id="task-child",
        agent_id="agent-1",
    )

    assert blocked.decision is (
        CoordinationDecision.BLOCK
    )
    assert engine.conflicts()[0].conflict_type is (
        CoordinationConflictType.DEPENDENCY_BLOCKED
    )


def test_task_start_and_completion_lifecycle() -> None:
    registry, engine = coordination_fixture()

    engine.assign(
        task_id="task-1",
        agent_id="agent-1",
    )

    running = engine.start_task("task-1")
    completed = engine.complete_task("task-1")

    assert running.status is (
        CoordinationTaskStatus.RUNNING
    )
    assert completed.status is (
        CoordinationTaskStatus.COMPLETED
    )
    assert engine.assignments()[-1].decision is (
        CoordinationDecision.COMPLETE
    )


def test_unassigned_task_cannot_start() -> None:
    _, engine = coordination_fixture()

    with pytest.raises(
        CoordinationEngineError,
        match="must be assigned",
    ):
        engine.start_task("task-1")


def test_only_running_task_can_complete() -> None:
    _, engine = coordination_fixture()

    with pytest.raises(
        CoordinationEngineError,
        match="Only running tasks",
    ):
        engine.complete_task("task-1")


def test_reassignment_updates_agent() -> None:
    registry = CoordinationRegistry()
    registry.register_agent(
        agent("agent-1", "code")
    )
    registry.register_agent(
        agent("agent-2", "code")
    )
    registry.register_task(
        task("task-1", "code")
    )

    engine = CoordinationEngine(
        registry=registry
    )

    engine.assign(
        task_id="task-1",
        agent_id="agent-1",
    )
    reassigned = engine.reassign(
        task_id="task-1",
        agent_id="agent-2",
    )

    assert reassigned.decision is (
        CoordinationDecision.REASSIGN
    )
    assert registry.get_task(
        "task-1"
    ).assigned_agent_id == "agent-2"


def test_conflict_can_be_resolved() -> None:
    _, engine = coordination_fixture()

    engine.assign(
        task_id="task-1",
        agent_id="agent-2",
    )

    conflict = engine.conflicts()[0]
    resolved = engine.resolve_conflict(
        conflict.conflict_id
    )

    assert resolved.resolved is True
    assert engine.conflicts(
        unresolved_only=True
    ) == ()


def test_snapshot_counts_runtime_state() -> None:
    _, engine = coordination_fixture()

    engine.assign(
        task_id="task-1",
        agent_id="agent-1",
    )

    snapshot = engine.snapshot()

    assert snapshot.agent_count == 2
    assert snapshot.task_count == 1
    assert snapshot.active_assignment_count == 1
    assert snapshot.unresolved_conflict_count == 0
