from __future__ import annotations

from af_core.capability.capability_models import (
    AgentCapability,
)
from af_core.communication import (
    AgentCommunicationBus,
    AgentMessage,
    CommunicationAuthorityGate,
    DeliveryStatus,
)
from af_core.organization import (
    AgentAvailabilityStatus,
    AgentRuntimeMetrics,
    AutomatedRoleFailoverEngine,
    DynamicRoleAssignmentEngine,
    DynamicRoleCoordinator,
    DynamicRoleRequirement,
    RoleAssignmentRequest,
    RoleEventPublisher,
    RoleFailoverRequest,
)


def agents() -> tuple[AgentCapability, ...]:
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

    for agent_id in (
        "move-agent-1",
        "move-agent-2",
    ):
        engine.update_runtime_metrics(
            AgentRuntimeMetrics(
                agent_id=agent_id,
                availability=(
                    AgentAvailabilityStatus.AVAILABLE
                ),
                current_assignments=0,
                maximum_assignments=4,
                workload_ratio=0.2,
                success_rate=0.98,
                quality_score=97,
                reliability_score=98,
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


def test_assignment_lifecycle_events_are_published():

    received: list[AgentMessage] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="role.**",
        agent_id="organization-monitor",
        handler=received.append,
    )

    _, coordinator = make_system(bus)

    result = coordinator.assign_role(
        request=RoleAssignmentRequest(
            team_id="team-001",
            workspace_id="blockchain-workspace",
            requirement=requirement(),
            requested_by="team-manager",
        ),
        auto_activate=True,
        approval_required=True,
    )

    assert result.selection.fulfilled
    assert len(result.active_assignments) == 1

    assert [
        message.topic
        for message in received
    ] == [
        "role.assignment.proposed",
        "role.assignment.approved",
        "role.assignment.activated",
    ]

    assert bus.verify_audit_integrity()


def test_release_event_is_published():

    received: list[AgentMessage] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="role.**",
        agent_id="organization-monitor",
        handler=received.append,
    )

    _, coordinator = make_system(bus)

    lifecycle = coordinator.assign_role(
        request=RoleAssignmentRequest(
            team_id="team-001",
            workspace_id="blockchain-workspace",
            requirement=requirement(),
            requested_by="team-manager",
        )
    )

    assignment = lifecycle.active_assignments[0]

    coordinator.release_role(
        assignment_id=assignment.assignment_id
    )

    assert (
        received[-1].topic
        == "role.assignment.released"
    )


def test_failover_completed_event_is_published():

    received: list[AgentMessage] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="role.**",
        agent_id="organization-monitor",
        handler=received.append,
    )

    engine, coordinator = make_system(bus)

    lifecycle = coordinator.assign_role(
        request=RoleAssignmentRequest(
            team_id="team-001",
            workspace_id="blockchain-workspace",
            requirement=requirement(),
            requested_by="team-manager",
        )
    )

    active = lifecycle.active_assignments[0]

    current_metrics = engine.runtime_metrics(
        active.agent_id
    )

    assert current_metrics is not None

    engine.update_runtime_metrics(
        current_metrics.model_copy(
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
            requested_by="monitor-agent",
        )
    )

    assert result.completed

    assert (
        received[-1].topic
        == "role.failover.completed"
    )

    assert bus.verify_audit_integrity()


def test_protected_role_event_is_denied_without_authority():

    received: list[AgentMessage] = []

    bus = AgentCommunicationBus(
        authority_gate=CommunicationAuthorityGate(
            checker=lambda agent_id, permission, environment, resource_scope: False
        )
    )

    bus.subscribe(
        topic="role.**",
        agent_id="organization-monitor",
        handler=received.append,
    )

    _, coordinator = make_system(bus)

    result = coordinator.assign_role(
        request=RoleAssignmentRequest(
            team_id="team-001",
            workspace_id="blockchain-workspace",
            requirement=requirement(),
            requested_by="team-manager",
        ),
        auto_activate=False,
        protected_events=True,
        environment="mainnet",
    )

    assert result.selection.fulfilled
    assert received == []

    assert (
        bus.delivery_history()[-1].status
        is DeliveryStatus.DENIED
    )

    assert bus.dead_letter_count == 1
    assert bus.verify_audit_integrity()
