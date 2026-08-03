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
    TeamEventPublisher,
    TeamLifecycleCoordinator,
    TeamReadinessDecision,
    TeamReadinessGovernance,
    TeamRoleRequirement,
    TeamStatus,
)


def available_agents() -> tuple[
    AgentCapability,
    ...
]:
    return (
        AgentCapability(
            agent_id="architecture-agent",
            agent_name="Architecture Agent",
            capabilities=[
                "architecture",
                "adr",
                "planning",
            ],
            supported_tasks=[
                "system_design",
                "architecture_review",
            ],
            skill_level=5,
        ),
        AgentCapability(
            agent_id="move-agent",
            agent_name="Move Development Agent",
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
            agent_id="security-agent",
            agent_name="Security Agent",
            capabilities=[
                "security_audit",
                "smart_contract",
            ],
            supported_tasks=[
                "security_review",
                "threat_analysis",
            ],
            skill_level=5,
        ),
        AgentCapability(
            agent_id="qa-agent",
            agent_name="Quality Assurance Agent",
            capabilities=[
                "quality_assurance",
                "test_automation",
            ],
            supported_tasks=[
                "integration_test",
                "regression_test",
            ],
            skill_level=4,
        ),
        AgentCapability(
            agent_id="inactive-move-agent",
            agent_name="Inactive Move Agent",
            capabilities=[
                "sui_move",
                "smart_contract",
            ],
            supported_tasks=[
                "contract_implementation",
            ],
            skill_level=5,
            status="inactive",
        ),
    )


def blockchain_team_request() -> TeamBuildRequest:
    return TeamBuildRequest(
        team_name=(
            "TOBMATE Blockchain "
            "Engineering Team"
        ),
        workspace_id=(
            "blockchain-workspace"
        ),
        objective=(
            "Design, implement, secure, "
            "and validate a Sui Move module"
        ),
        requested_by=(
            "project-manager-agent"
        ),
        role_requirements=[
            TeamRoleRequirement(
                role_name="System Architect",
                required_capabilities={
                    "architecture",
                },
                supported_tasks={
                    "system_design",
                },
                minimum_skill_level=4,
            ),
            TeamRoleRequirement(
                role_name="Move Developer",
                required_capabilities={
                    "sui_move",
                    "smart_contract",
                },
                supported_tasks={
                    "contract_implementation",
                },
                minimum_skill_level=4,
            ),
            TeamRoleRequirement(
                role_name="Security Reviewer",
                required_capabilities={
                    "security_audit",
                },
                supported_tasks={
                    "security_review",
                },
                minimum_skill_level=4,
            ),
            TeamRoleRequirement(
                role_name="QA Engineer",
                required_capabilities={
                    "quality_assurance",
                },
                supported_tasks={
                    "integration_test",
                    "regression_test",
                },
                minimum_skill_level=3,
            ),
        ],
        metadata={
            "project":
                "tobmate-blockchain",

            "checkpoint":
                "16-B",
        },
    )


def make_coordinator(
    bus: AgentCommunicationBus,
) -> tuple[
    TeamBuilderEngine,
    TeamLifecycleCoordinator,
]:
    builder = TeamBuilderEngine(
        agent_provider=available_agents
    )

    coordinator = (
        TeamLifecycleCoordinator(
            builder=builder,
            governance=(
                TeamReadinessGovernance()
            ),
            publisher=(
                TeamEventPublisher(bus)
            ),
        )
    )

    return builder, coordinator


def test_complete_runtime_team_intelligence_flow():

    lifecycle_events: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="team.**",
        agent_id=(
            "organization-intelligence-agent"
        ),
        workspace_id=(
            "blockchain-workspace"
        ),
        handler=lifecycle_events.append,
    )

    builder, coordinator = (
        make_coordinator(bus)
    )

    result = coordinator.create_team(
        request=blockchain_team_request(),
        environment="runtime",
    )

    assert result.validation.valid

    assert (
        result.readiness.decision
        is TeamReadinessDecision.READY
    )

    assert result.readiness.approved
    assert result.activated

    assert (
        result.activated_team
        is not None
    )

    assert (
        result.activated_team.status
        is TeamStatus.ACTIVE
    )

    assert (
        result.team.member_count
        == 4
    )

    role_assignments = {
        member.role_name:
            member.agent_id
        for member in result.team.members
    }

    assert role_assignments == {
        "System Architect":
            "architecture-agent",

        "Move Developer":
            "move-agent",

        "Security Reviewer":
            "security-agent",

        "QA Engineer":
            "qa-agent",
    }

    report = builder.validation_report(
        result.team.team_id
    )

    assert report is not None
    assert report.valid
    assert report.error_count == 0

    assert all(
        coverage.covered
        for coverage
        in report.role_coverage
    )

    topics = [
        message.topic
        for message in lifecycle_events
    ]

    assert topics == [
        "team.created",
        "team.validation.completed",
        "team.ready",
        "team.activated",
    ]

    assert bus.verify_audit_integrity()

    # Four lifecycle messages are published and delivered.
    assert len(
        bus.message_history()
    ) == 4

    assert len(
        bus.delivery_history()
    ) == 4


def test_selection_intelligence_records_explanations():

    bus = AgentCommunicationBus()

    builder, coordinator = (
        make_coordinator(bus)
    )

    result = coordinator.create_team(
        request=blockchain_team_request(),
        environment="runtime",
        activate_when_ready=False,
    )

    metadata = (
        result.team.selection_metadata
    )

    assert set(metadata) == {
        "System Architect",
        "Move Developer",
        "Security Reviewer",
        "QA Engineer",
    }

    move_selection = metadata[
        "Move Developer"
    ]

    assert (
        move_selection[
            "selected_agent_ids"
        ]
        == ["move-agent"]
    )

    assert (
        move_selection[
            "eligible_count"
        ]
        == 1
    )

    ranked = move_selection[
        "ranked_candidates"
    ]

    assert len(ranked) == 1

    assert (
        ranked[0]["agent_id"]
        == "move-agent"
    )

    assert (
        ranked[0]["total_score"]
        > 0
    )

    assert ranked[0]["reasons"]

    rejected = move_selection[
        "rejection_reasons"
    ]

    assert (
        "inactive-move-agent"
        in rejected
    )

    assert (
        "agent is not active"
        in rejected[
            "inactive-move-agent"
        ]
    )

    assert not result.activated


def test_mainnet_requires_approval_then_activates():

    lifecycle_events: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="team.**",
        agent_id="governance-agent",
        handler=lifecycle_events.append,
    )

    _, coordinator = make_coordinator(
        bus
    )

    pending = coordinator.create_team(
        request=blockchain_team_request(),
        environment="mainnet",
    )

    assert (
        pending.readiness.decision
        is TeamReadinessDecision
        .APPROVAL_REQUIRED
    )

    assert not pending.activated

    assert (
        lifecycle_events[-1].topic
        == "team.approval.required"
    )

    lifecycle_events.clear()

    approved = coordinator.create_team(
        request=blockchain_team_request(),
        environment="mainnet",
        human_approved=True,
        approver_id="tobmate-owner",
    )

    assert (
        approved.readiness.decision
        is TeamReadinessDecision.READY
    )

    assert approved.activated

    assert (
        approved.activated_team
        is not None
    )

    assert (
        approved.activated_team.status
        is TeamStatus.ACTIVE
    )

    assert [
        message.topic
        for message in lifecycle_events
    ] == [
        "team.created",
        "team.validation.completed",
        "team.ready",
        "team.activated",
    ]

    assert bus.verify_audit_integrity()


def test_unavailable_required_role_is_blocked():

    received: list[
        AgentMessage
    ] = []

    bus = AgentCommunicationBus()

    bus.subscribe(
        topic="team.**",
        agent_id="team-monitor-agent",
        handler=received.append,
    )

    builder = TeamBuilderEngine(
        agent_provider=available_agents
    )

    coordinator = (
        TeamLifecycleCoordinator(
            builder=builder,
            governance=(
                TeamReadinessGovernance()
            ),
            publisher=(
                TeamEventPublisher(bus)
            ),
        )
    )

    request = TeamBuildRequest(
        team_name="Robotics Team",
        workspace_id=(
            "robotics-workspace"
        ),
        objective=(
            "Build an embodied robotics "
            "control system"
        ),
        requested_by="manager-agent",
        role_requirements=[
            TeamRoleRequirement(
                role_name=(
                    "Robotics Engineer"
                ),
                required_capabilities={
                    "robotics",
                },
                supported_tasks={
                    "robot_control",
                },
            )
        ],
    )

    result = coordinator.create_team(
        request=request,
        environment="runtime",
    )

    assert not result.validation.valid

    assert (
        result.readiness.decision
        is TeamReadinessDecision.BLOCKED
    )

    assert not result.activated

    assert result.team.unfilled_roles

    assert (
        result.team.unfilled_roles[0]
        .role_name
        == "Robotics Engineer"
    )

    assert [
        message.topic
        for message in received
    ] == [
        "team.created",
        "team.validation.completed",
        "team.blocked",
    ]

    assert bus.verify_audit_integrity()
