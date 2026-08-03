from __future__ import annotations

from af_core.capability.capability_models import (
    AgentCapability,
)
from af_core.organization import (
    AgentAvailabilityStatus,
    AgentRuntimeMetrics,
    AutomatedRoleFailoverEngine,
    DynamicRoleAssignmentEngine,
    DynamicRoleRequirement,
    ReassignmentPolicy,
    RoleAssignmentRequest,
    RoleAssignmentStatus,
    RoleFailoverRequest,
    RoleHealthDecision,
    RoleReassignmentPolicyEngine,
)


def agents() -> tuple[
    AgentCapability,
    ...
]:
    return (
        AgentCapability(
            agent_id="move-agent-1",
            agent_name="Move Agent 1",
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
            agent_id="move-agent-2",
            agent_name="Move Agent 2",
            capabilities=[
                "sui_move",
                "smart_contract",
            ],
            supported_tasks=[
                "contract_implementation",
            ],
            skill_level=4,
        ),
    )


def requirement() -> DynamicRoleRequirement:
    return DynamicRoleRequirement(
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


def active_assignment(
    engine: DynamicRoleAssignmentEngine,
):
    result = engine.assign(
        RoleAssignmentRequest(
            team_id="team-001",
            workspace_id=(
                "blockchain-workspace"
            ),
            requirement=requirement(),
            requested_by="manager-agent",
        )
    )

    assignment = result.assignments[0]

    return engine.activate(
        assignment.assignment_id
    )


def make_engine(
) -> DynamicRoleAssignmentEngine:
    engine = DynamicRoleAssignmentEngine(
        agent_provider=agents,
        require_runtime_metrics=True,
    )

    engine.update_runtime_metrics(
        AgentRuntimeMetrics(
            agent_id="move-agent-1",
            availability=(
                AgentAvailabilityStatus
                .AVAILABLE
            ),
            current_assignments=1,
            maximum_assignments=4,
            workload_ratio=0.2,
            success_rate=0.99,
            quality_score=98,
            reliability_score=99,
        )
    )

    engine.update_runtime_metrics(
        AgentRuntimeMetrics(
            agent_id="move-agent-2",
            availability=(
                AgentAvailabilityStatus
                .AVAILABLE
            ),
            current_assignments=0,
            maximum_assignments=4,
            workload_ratio=0.2,
            success_rate=0.97,
            quality_score=96,
            reliability_score=98,
        )
    )

    return engine


def test_healthy_assignment_is_not_replaced():

    engine = make_engine()

    active = active_assignment(engine)

    failover = (
        AutomatedRoleFailoverEngine(
            assignment_engine=engine
        )
    )

    result = failover.execute(
        RoleFailoverRequest(
            assignment_id=(
                active.assignment_id
            ),
            team_id="team-001",
            workspace_id=(
                "blockchain-workspace"
            ),
            requirement=requirement(),
            requested_by="monitor-agent",
        )
    )

    assert (
        result.assessment.decision
        is RoleHealthDecision.KEEP
    )

    assert not result.completed

    assert (
        result.replacement_assignment
        is None
    )


def test_offline_agent_is_automatically_failed_over():

    engine = make_engine()

    active = active_assignment(engine)

    engine.update_runtime_metrics(
        AgentRuntimeMetrics(
            agent_id=active.agent_id,
            availability=(
                AgentAvailabilityStatus
                .OFFLINE
            ),
            current_assignments=1,
            maximum_assignments=4,
            workload_ratio=0.2,
        )
    )

    failover = (
        AutomatedRoleFailoverEngine(
            assignment_engine=engine
        )
    )

    result = failover.execute(
        RoleFailoverRequest(
            assignment_id=(
                active.assignment_id
            ),
            team_id="team-001",
            workspace_id=(
                "blockchain-workspace"
            ),
            requirement=requirement(),
            requested_by="monitor-agent",
        )
    )

    assert (
        result.assessment.decision
        is RoleHealthDecision.FAILOVER
    )

    assert result.completed

    assert (
        result.replacement_assignment
        is not None
    )

    expected_replacement_id = (
        "move-agent-2"
        if active.agent_id == "move-agent-1"
        else "move-agent-1"
    )

    assert (
        result.replacement_assignment.agent_id
        == expected_replacement_id
    )

    assert (
        result.replacement_assignment.agent_id
        != active.agent_id
    )

    assert (
        result.replacement_assignment.status
        is RoleAssignmentStatus.ACTIVE
    )

    assert (
        result.previous_assignment_released
    )

    active_assignments = (
        engine.assignments_for_role(
            team_id="team-001",
            role_name="Move Developer",
        )
    )

    assert len(active_assignments) == 1

    assert (
        active_assignments[0].agent_id
        == expected_replacement_id
    )

    assert (
        active_assignments[0].agent_id
        != active.agent_id
    )


def test_overloaded_agent_is_reassigned():

    engine = make_engine()

    active = active_assignment(engine)

    current_metrics = (
        engine.runtime_metrics(
            active.agent_id
        )
    )

    assert current_metrics is not None

    engine.update_runtime_metrics(
        current_metrics.model_copy(
            update={
                "workload_ratio": 0.96,
            }
        )
    )

    failover = (
        AutomatedRoleFailoverEngine(
            assignment_engine=engine
        )
    )

    result = failover.execute(
        RoleFailoverRequest(
            assignment_id=(
                active.assignment_id
            ),
            team_id="team-001",
            workspace_id=(
                "blockchain-workspace"
            ),
            requirement=requirement(),
            requested_by="monitor-agent",
        )
    )

    assert (
        result.assessment.decision
        is RoleHealthDecision.REASSIGN
    )

    assert result.completed

    assert (
        result.replacement_assignment
        is not None
    )

    expected_replacement_id = (
        "move-agent-2"
        if active.agent_id == "move-agent-1"
        else "move-agent-1"
    )

    assert (
        result.replacement_assignment.agent_id
        == expected_replacement_id
    )

    assert (
        result.replacement_assignment.agent_id
        != active.agent_id
    )


def test_no_replacement_keeps_previous_assignment_active():

    only_one_agent = (
        agents()[0],
    )

    engine = DynamicRoleAssignmentEngine(
        agent_provider=(
            lambda: only_one_agent
        ),
        require_runtime_metrics=True,
    )

    engine.update_runtime_metrics(
        AgentRuntimeMetrics(
            agent_id="move-agent-1",
            availability=(
                AgentAvailabilityStatus
                .AVAILABLE
            ),
            current_assignments=0,
            maximum_assignments=4,
            workload_ratio=0.2,
        )
    )

    active = active_assignment(engine)

    engine.update_runtime_metrics(
        AgentRuntimeMetrics(
            agent_id="move-agent-1",
            availability=(
                AgentAvailabilityStatus
                .OFFLINE
            ),
            current_assignments=1,
            maximum_assignments=4,
            workload_ratio=0.2,
        )
    )

    failover = (
        AutomatedRoleFailoverEngine(
            assignment_engine=engine
        )
    )

    result = failover.execute(
        RoleFailoverRequest(
            assignment_id=(
                active.assignment_id
            ),
            team_id="team-001",
            workspace_id=(
                "blockchain-workspace"
            ),
            requirement=requirement(),
            requested_by="monitor-agent",
        )
    )

    assert not result.completed

    assert (
        result.replacement_assignment
        is None
    )

    current = (
        engine.assignments_for_role(
            team_id="team-001",
            role_name="Move Developer",
        )
    )

    assert current == (active,)


def test_policy_can_disable_automatic_activation():

    engine = make_engine()

    active = active_assignment(engine)

    engine.update_runtime_metrics(
        AgentRuntimeMetrics(
            agent_id=active.agent_id,
            availability=(
                AgentAvailabilityStatus
                .OFFLINE
            ),
            current_assignments=1,
            maximum_assignments=4,
            workload_ratio=0.2,
        )
    )

    policy_engine = (
        RoleReassignmentPolicyEngine(
            policy=ReassignmentPolicy(
                activate_replacement_automatically=False
            )
        )
    )

    failover = (
        AutomatedRoleFailoverEngine(
            assignment_engine=engine,
            policy_engine=policy_engine,
        )
    )

    result = failover.execute(
        RoleFailoverRequest(
            assignment_id=(
                active.assignment_id
            ),
            team_id="team-001",
            workspace_id=(
                "blockchain-workspace"
            ),
            requirement=requirement(),
            requested_by="monitor-agent",
        )
    )

    assert not result.completed

    assert (
        result.replacement_assignment
        is not None
    )

    assert (
        result.replacement_assignment.status
        is RoleAssignmentStatus.PROPOSED
    )

    assert not (
        result.previous_assignment_released
    )
