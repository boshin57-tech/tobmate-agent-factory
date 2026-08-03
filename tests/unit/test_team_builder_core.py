from __future__ import annotations

from af_core.capability.capability_models import (
    AgentCapability,
)
from af_core.organization import (
    RoleCriticality,
    TeamBuildRequest,
    TeamBuilderEngine,
    TeamRoleRequirement,
    TeamStatus,
)


def make_agents() -> tuple[
    AgentCapability,
    ...
]:
    return (
        AgentCapability(
            agent_id="architect-agent",
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
            agent_name="Move Agent",
            capabilities=[
                "sui_move",
                "smart_contract",
            ],
            supported_tasks=[
                "contract_implementation",
                "unit_test",
            ],
            skill_level=4,
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
    )


def test_builder_creates_ready_team():

    builder = TeamBuilderEngine(
        agent_provider=make_agents
    )

    request = TeamBuildRequest(
        team_name="Blockchain Core Team",
        workspace_id=(
            "blockchain-workspace"
        ),
        objective=(
            "Implement and validate "
            "a Sui Move protocol"
        ),
        requested_by="project-manager",
        role_requirements=[
            TeamRoleRequirement(
                role_name="Architect",
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
                },
                supported_tasks={
                    "contract_implementation",
                },
                minimum_skill_level=3,
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
        ],
    )

    team = builder.build(request)

    assert (
        team.status
        is TeamStatus.READY
    )

    assert team.is_ready

    assert team.member_count == 3

    assert (
        builder.team_count
        == 1
    )


def test_missing_required_role_keeps_team_forming():

    builder = TeamBuilderEngine(
        agent_provider=make_agents
    )

    request = TeamBuildRequest(
        team_name="Incomplete Team",
        workspace_id="workspace-001",
        objective="Build a 3D world",
        requested_by="project-manager",
        role_requirements=[
            TeamRoleRequirement(
                role_name="Unreal Developer",
                required_capabilities={
                    "unreal_engine",
                },
            )
        ],
    )

    team = builder.build(request)

    assert (
        team.status
        is TeamStatus.FORMING
    )

    assert not team.is_ready

    assert len(team.unfilled_roles) == 1

    assert (
        team.unfilled_roles[0].role_name
        == "Unreal Developer"
    )


def test_optional_role_does_not_block_team_readiness():

    builder = TeamBuilderEngine(
        agent_provider=make_agents
    )

    request = TeamBuildRequest(
        team_name="Optional Specialist Team",
        workspace_id="workspace-001",
        objective="Design a protocol",
        requested_by="project-manager",
        role_requirements=[
            TeamRoleRequirement(
                role_name="Architect",
                required_capabilities={
                    "architecture",
                },
            ),
            TeamRoleRequirement(
                role_name="Optional Economist",
                required_capabilities={
                    "token_economics",
                },
                criticality=(
                    RoleCriticality.OPTIONAL
                ),
            ),
        ],
    )

    team = builder.build(request)

    assert (
        team.status
        is TeamStatus.READY
    )

    assert team.member_count == 1

    assert team.unfilled_roles == []


def test_agent_is_not_reused_by_default():

    agents = (
        AgentCapability(
            agent_id="multi-agent",
            agent_name="Multi Specialist",
            capabilities=[
                "architecture",
                "planning",
            ],
            supported_tasks=[],
            skill_level=5,
        ),
    )

    builder = TeamBuilderEngine(
        agent_provider=lambda: agents
    )

    request = TeamBuildRequest(
        team_name="No Reuse Team",
        workspace_id="workspace-001",
        objective="Test role isolation",
        requested_by="project-manager",
        role_requirements=[
            TeamRoleRequirement(
                role_name="Architect",
                required_capabilities={
                    "architecture",
                },
            ),
            TeamRoleRequirement(
                role_name="Planner",
                required_capabilities={
                    "planning",
                },
            ),
        ],
    )

    team = builder.build(request)

    assert team.member_count == 1

    assert len(team.unfilled_roles) == 1


def test_team_is_stored_by_workspace():

    builder = TeamBuilderEngine(
        agent_provider=make_agents
    )

    request = TeamBuildRequest(
        team_name="Stored Team",
        workspace_id="workspace-001",
        objective="Test repository",
        requested_by="project-manager",
        role_requirements=[],
    )

    team = builder.build(request)

    stored = builder.get_team(
        team.team_id
    )

    workspace_teams = (
        builder.teams_for_workspace(
            "workspace-001"
        )
    )

    assert stored == team

    assert workspace_teams == (
        team,
    )
