from __future__ import annotations

from af_core.capability.capability_models import (
    AgentCapability,
)
from af_core.communication import (
    AgentCommunicationBus,
    AgentMessage,
)
from af_core.organization import (
    AgentAvailabilityStatus,
    AgentRuntimeMetrics,
    AutomatedRoleFailoverEngine,
    DynamicRoleAssignmentEngine,
    DynamicRoleCoordinator,
    DynamicRoleRequirement,
    RoleAssignmentRequest,
    RoleAssignmentStatus,
    RoleEventPublisher,
    RoleFailoverRequest,
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
                "unit_test",
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
        AgentCapability(
            agent_id="move-agent-3",
            agent_name="Move Agent 3",
            capabilities=[
                "sui_move",
                "smart_contract",
                "security_review",
            ],
            supported_tasks=[
                "contract_implementation",
                "unit_test",
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
        priority=8,
    )


def make_system(
    bus: AgentCommunicationBus,
) -> tuple[
    DynamicRoleAssignmentEngine,
    DynamicRoleCoordinator,
]:
    engine = DynamicRoleAssignmentEngine(
        agent_provider=agents,
        require_runtime_metrics=True,
    )

    engine.update_runtime_metrics(
        AgentRuntimeMetrics(
            agent_id="move-agent-1",
            availability=(
                AgentAvailabilityStatus.AVAILABLE
            ),
            current_assignments=0,
            maximum_assignments=4,
            workload_ratio=0.20,
            success_rate=0.99,
            quality_score=98,
            reliability_score=99,
            average_response_ms=300,
        )
    )

    engine.update_runtime_metrics(
        AgentRuntimeMetrics(
            agent_id="move-agent-2",
            availability=(
                AgentAvailabilityStatus.AVAILABLE
            ),
            current_assignments=0,
            maximum_assignments=4,
            workload_ratio=0.30,
            success_rate=0.97,
            quality_score=95,
            reliability_score=97,
            average_response_ms=500,
        )
    )

    engine.update_runtime_metrics(
        AgentRuntimeMetrics(
            agent_id="move-agent-3",
            availability=(
                AgentAvailabilityStatus.AVAILABLE
            ),
            current_assignments=1,
            maximum_assignments=4,
            workload_ratio=0.45,
            success_rate=0.96,
            quality_score=94,
            reliability_score=96,
            average_response_ms=650,
        )
    )

    failover = AutomatedRoleFailoverEngine(
        assignment_engine=engine
    )

    coordinator = DynamicRoleCoordinator(
        assignment_engine=engine,
        failover_engine=failover,
        publisher=RoleEventPublisher(bus),
    )

    return engine, coordinator


def test_complete_dynamic_role_lifecycle():

    events: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="role.**",
        agent_id="organization-intelligence-agent",
        workspace_id="blockchain-workspace",
        handler=events.append,
    )

    engine, coordinator = make_system(
        bus
    )

    lifecycle = coordinator.assign_role(
        request=RoleAssignmentRequest(
            team_id="team-001",
            workspace_id="blockchain-workspace",
            requirement=requirement(),
            requested_by="team-manager-agent",
        ),
        auto_activate=True,
        approval_required=True,
    )

    assert lifecycle.selection.fulfilled
    assert len(
        lifecycle.active_assignments
    ) == 1

    active = (
        lifecycle.active_assignments[0]
    )

    assert (
        active.status
        is RoleAssignmentStatus.ACTIVE
    )

    assert [
        message.topic
        for message in events
    ] == [
        "role.assignment.proposed",
        "role.assignment.approved",
        "role.assignment.activated",
    ]

    assert (
        engine.assignments_for_team(
            "team-001"
        )
        == (active,)
    )

    assert bus.verify_audit_integrity()


def test_runtime_degradation_triggers_reassignment():

    events: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="role.**",
        agent_id="organization-monitor",
        handler=events.append,
    )

    engine, coordinator = make_system(
        bus
    )

    lifecycle = coordinator.assign_role(
        request=RoleAssignmentRequest(
            team_id="team-001",
            workspace_id="blockchain-workspace",
            requirement=requirement(),
            requested_by="team-manager-agent",
        )
    )

    active = (
        lifecycle.active_assignments[0]
    )

    current_metrics = (
        engine.runtime_metrics(
            active.agent_id
        )
    )

    assert current_metrics is not None

    engine.update_runtime_metrics(
        current_metrics.model_copy(
            update={
                "workload_ratio": 0.97,
                "success_rate": 0.60,
                "quality_score": 55,
                "reliability_score": 60,
                "consecutive_failures": 4,
            }
        )
    )

    result = coordinator.execute_failover(
        request=RoleFailoverRequest(
            assignment_id=(
                active.assignment_id
            ),
            team_id="team-001",
            workspace_id="blockchain-workspace",
            requirement=requirement(),
            requested_by="monitor-agent",
        )
    )

    assert result.completed

    assert (
        result.replacement_assignment
        is not None
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

    assert (
        events[-1].topic
        == "role.failover.completed"
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
        == result.replacement_assignment.agent_id
    )

    assert bus.verify_audit_integrity()


def test_offline_assignment_fails_over_without_role_gap():

    bus = AgentCommunicationBus()

    engine, coordinator = make_system(
        bus
    )

    lifecycle = coordinator.assign_role(
        request=RoleAssignmentRequest(
            team_id="team-001",
            workspace_id="blockchain-workspace",
            requirement=requirement(),
            requested_by="team-manager-agent",
        )
    )

    active = (
        lifecycle.active_assignments[0]
    )

    metrics = engine.runtime_metrics(
        active.agent_id
    )

    assert metrics is not None

    engine.update_runtime_metrics(
        metrics.model_copy(
            update={
                "availability":
                    AgentAvailabilityStatus.OFFLINE,
            }
        )
    )

    result = coordinator.execute_failover(
        request=RoleFailoverRequest(
            assignment_id=active.assignment_id,
            team_id="team-001",
            workspace_id="blockchain-workspace",
            requirement=requirement(),
            requested_by="health-monitor-agent",
        )
    )

    assert result.completed

    assert (
        result.replacement_assignment
        is not None
    )

    assert (
        result.replacement_assignment.status
        is RoleAssignmentStatus.ACTIVE
    )

    active_assignments = (
        engine.assignments_for_team(
            "team-001"
        )
    )

    assert len(active_assignments) == 1

    assert (
        active_assignments[0].agent_id
        != active.agent_id
    )


def test_release_closes_dynamic_role_lifecycle():

    events: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="role.**",
        agent_id="audit-agent",
        handler=events.append,
    )

    engine, coordinator = make_system(
        bus
    )

    lifecycle = coordinator.assign_role(
        request=RoleAssignmentRequest(
            team_id="team-001",
            workspace_id="blockchain-workspace",
            requirement=requirement(),
            requested_by="team-manager-agent",
        )
    )

    active = (
        lifecycle.active_assignments[0]
    )

    released = coordinator.release_role(
        assignment_id=(
            active.assignment_id
        )
    )

    assert (
        released.status
        is RoleAssignmentStatus.RELEASED
    )

    assert (
        engine.assignments_for_team(
            "team-001"
        )
        == ()
    )

    assert (
        events[-1].topic
        == "role.assignment.released"
    )

    assert bus.verify_audit_integrity()
