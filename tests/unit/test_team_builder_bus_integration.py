from __future__ import annotations

from af_core.capability.capability_models import (
    AgentCapability,
)
from af_core.communication import (
    AgentCommunicationBus,
    AgentMessage,
)
from af_core.organization import (
    TeamBuildRequest,
    TeamBuilderEngine,
    TeamEventType,
    TeamLifecycleCoordinator,
    TeamReadinessDecision,
    TeamReadinessGovernance,
    TeamRoleRequirement,
    TeamStatus,
    TeamEventPublisher,
)


def make_agents() -> tuple[
    AgentCapability,
    ...
]:
    return (
        AgentCapability(
            agent_id="architect-agent",
            agent_name="Architect Agent",
            capabilities=[
                "architecture",
            ],
            supported_tasks=[
                "system_design",
            ],
            skill_level=5,
        ),
        AgentCapability(
            agent_id="move-agent",
            agent_name="Move Agent",
            capabilities=[
                "sui_move",
            ],
            supported_tasks=[
                "contract_implementation",
            ],
            skill_level=5,
        ),
    )


def make_request() -> TeamBuildRequest:
    return TeamBuildRequest(
        team_name="Blockchain Team",
        workspace_id=(
            "blockchain-workspace"
        ),
        objective=(
            "Build a Move protocol"
        ),
        requested_by=(
            "project-manager-agent"
        ),
        role_requirements=[
            TeamRoleRequirement(
                role_name="Architect",
                required_capabilities={
                    "architecture",
                },
                supported_tasks={
                    "system_design",
                },
            ),
            TeamRoleRequirement(
                role_name="Move Developer",
                required_capabilities={
                    "sui_move",
                },
                supported_tasks={
                    "contract_implementation",
                },
            ),
        ],
    )


def build_coordinator(
    bus: AgentCommunicationBus,
) -> TeamLifecycleCoordinator:
    builder = TeamBuilderEngine(
        agent_provider=make_agents
    )

    governance = (
        TeamReadinessGovernance()
    )

    publisher = TeamEventPublisher(
        bus
    )

    return TeamLifecycleCoordinator(
        builder=builder,
        governance=governance,
        publisher=publisher,
    )


def test_runtime_team_lifecycle_is_broadcast():

    received: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="team.**",
        agent_id=(
            "organization-monitor-agent"
        ),
        handler=received.append,
    )

    coordinator = build_coordinator(
        bus
    )

    result = coordinator.create_team(
        request=make_request(),
        environment="runtime",
    )

    assert result.validation.valid

    assert (
        result.readiness.decision
        is TeamReadinessDecision.READY
    )

    assert result.activated

    assert (
        result.activated_team
        is not None
    )

    assert (
        result.activated_team.status
        is TeamStatus.ACTIVE
    )

    topics = [
        message.topic
        for message in received
    ]

    assert topics == [
        "team.created",
        "team.validation.completed",
        "team.ready",
        "team.activated",
    ]

    assert bus.verify_audit_integrity()


def test_mainnet_team_publishes_approval_required():

    received: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="team.**",
        agent_id=(
            "governance-monitor-agent"
        ),
        handler=received.append,
    )

    coordinator = build_coordinator(
        bus
    )

    result = coordinator.create_team(
        request=make_request(),
        environment="mainnet",
    )

    assert (
        result.readiness.decision
        is TeamReadinessDecision
        .APPROVAL_REQUIRED
    )

    assert not result.activated

    topics = [
        message.topic
        for message in received
    ]

    assert topics == [
        "team.created",
        "team.validation.completed",
        "team.approval.required",
    ]

    approval_message = received[-1]

    assert (
        approval_message.payload[
            "event_type"
        ]
        == TeamEventType
        .APPROVAL_REQUIRED.value
    )


def test_approved_mainnet_team_is_activated():

    received: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="team.**",
        agent_id="audit-agent",
        handler=received.append,
    )

    coordinator = build_coordinator(
        bus
    )

    result = coordinator.create_team(
        request=make_request(),
        environment="mainnet",
        human_approved=True,
        approver_id="human-owner",
    )

    assert result.activated

    assert received[-1].topic == (
        "team.activated"
    )


def test_invalid_team_publishes_blocked_event():

    bus = AgentCommunicationBus()

    received: list[
        AgentMessage
    ] = []

    bus.subscribe(
        topic="team.**",
        agent_id="monitor-agent",
        handler=received.append,
    )

    builder = TeamBuilderEngine(
        agent_provider=lambda: ()
    )

    coordinator = TeamLifecycleCoordinator(
        builder=builder,
        governance=(
            TeamReadinessGovernance()
        ),
        publisher=TeamEventPublisher(
            bus
        ),
    )

    request = TeamBuildRequest(
        team_name="Invalid Team",
        workspace_id="workspace-001",
        objective="Unavailable capability",
        requested_by="manager-agent",
        role_requirements=[
            TeamRoleRequirement(
                role_name="Missing Agent",
                required_capabilities={
                    "missing_capability",
                },
            )
        ],
    )

    result = coordinator.create_team(
        request=request
    )

    assert not result.validation.valid

    assert (
        result.readiness.decision
        is TeamReadinessDecision.BLOCKED
    )

    assert not result.activated

    assert received[-1].topic == (
        "team.blocked"
    )


def test_team_events_are_workspace_isolated():

    workspace_messages: list[
        AgentMessage
    ] = []

    other_workspace_messages: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="team.**",
        agent_id="blockchain-monitor",
        workspace_id=(
            "blockchain-workspace"
        ),
        handler=(
            workspace_messages.append
        ),
    )

    bus.subscribe(
        topic="team.**",
        agent_id="gsos-monitor",
        workspace_id=(
            "gsos-workspace"
        ),
        handler=(
            other_workspace_messages
            .append
        ),
    )

    coordinator = build_coordinator(
        bus
    )

    coordinator.create_team(
        request=make_request()
    )

    assert len(
        workspace_messages
    ) == 4

    assert (
        other_workspace_messages
        == []
    )
