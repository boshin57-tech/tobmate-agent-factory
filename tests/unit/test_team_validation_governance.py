from __future__ import annotations

import pytest

from af_core.capability.capability_models import (
    AgentCapability,
)
from af_core.organization import (
    TeamBuildRequest,
    TeamBuilderEngine,
    TeamReadinessDecision,
    TeamReadinessGovernance,
    TeamReadinessPolicy,
    TeamRoleRequirement,
    TeamStatus,
    TeamValidationCode,
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
                "planning",
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
                "smart_contract",
            ],
            supported_tasks=[
                "contract_implementation",
            ],
            skill_level=4,
        ),
        AgentCapability(
            agent_id="security-agent",
            agent_name="Security Agent",
            capabilities=[
                "security_audit",
            ],
            supported_tasks=[
                "security_review",
            ],
            skill_level=5,
        ),
    )


def build_valid_team():

    builder = TeamBuilderEngine(
        agent_provider=make_agents
    )

    request = TeamBuildRequest(
        team_name="Blockchain Team",
        workspace_id=(
            "blockchain-workspace"
        ),
        objective=(
            "Implement and validate "
            "a Move protocol"
        ),
        requested_by="manager-agent",
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

    report = builder.validation_report(
        team.team_id
    )

    return (
        builder,
        request,
        team,
        report,
    )


def test_valid_team_has_complete_role_coverage():

    _, _, team, report = (
        build_valid_team()
    )

    assert report is not None
    assert report.valid

    assert (
        team.status
        is TeamStatus.READY
    )

    assert all(
        coverage.covered
        for coverage
        in report.role_coverage
    )

    assert any(
        issue.code
        is TeamValidationCode
        .ROLE_COVERAGE_COMPLETE
        for issue in report.issues
    )


def test_missing_required_role_is_invalid():

    builder = TeamBuilderEngine(
        agent_provider=make_agents
    )

    request = TeamBuildRequest(
        team_name="Incomplete Team",
        workspace_id="workspace-001",
        objective="Build robotics system",
        requested_by="manager-agent",
        role_requirements=[
            TeamRoleRequirement(
                role_name="Robotics Engineer",
                required_capabilities={
                    "robotics",
                },
            )
        ],
    )

    team = builder.build(request)

    report = builder.validation_report(
        team.team_id
    )

    assert report is not None
    assert not report.valid

    codes = {
        issue.code
        for issue in report.issues
    }

    assert (
        TeamValidationCode
        .REQUIRED_ROLE_UNFILLED
        in codes
    )

    assert (
        TeamValidationCode
        .MINIMUM_MEMBERS_NOT_MET
        in codes
    )


def test_runtime_team_is_ready_without_approval():

    _, _, team, report = (
        build_valid_team()
    )

    assert report is not None

    governance = (
        TeamReadinessGovernance()
    )

    result = governance.evaluate(
        team=team,
        validation=report,
        environment="runtime",
    )

    assert (
        result.decision
        is TeamReadinessDecision.READY
    )

    assert result.approved


def test_mainnet_team_requires_human_approval():

    _, _, team, report = (
        build_valid_team()
    )

    assert report is not None

    governance = (
        TeamReadinessGovernance()
    )

    result = governance.evaluate(
        team=team,
        validation=report,
        environment="mainnet",
    )

    assert (
        result.decision
        is TeamReadinessDecision
        .APPROVAL_REQUIRED
    )

    assert not result.approved


def test_mainnet_team_can_be_approved():

    _, _, team, report = (
        build_valid_team()
    )

    assert report is not None

    governance = (
        TeamReadinessGovernance()
    )

    result = governance.evaluate(
        team=team,
        validation=report,
        environment="mainnet",
        human_approved=True,
        approver_id="human-owner",
    )

    assert (
        result.decision
        is TeamReadinessDecision.READY
    )

    assert result.approved

    active_team = governance.activate(
        team=team,
        readiness=result,
    )

    assert (
        active_team.status
        is TeamStatus.ACTIVE
    )

    assert (
        active_team.activated_at
        is not None
    )


def test_invalid_team_is_blocked():

    builder = TeamBuilderEngine(
        agent_provider=lambda: ()
    )

    request = TeamBuildRequest(
        team_name="Invalid Team",
        workspace_id="workspace-001",
        objective="No eligible agents",
        requested_by="manager-agent",
        role_requirements=[
            TeamRoleRequirement(
                role_name="Required Agent",
                required_capabilities={
                    "required_capability",
                },
            )
        ],
    )

    team = builder.build(request)

    report = builder.validation_report(
        team.team_id
    )

    assert report is not None

    governance = (
        TeamReadinessGovernance()
    )

    result = governance.evaluate(
        team=team,
        validation=report,
    )

    assert (
        result.decision
        is TeamReadinessDecision.BLOCKED
    )

    assert not result.approved


def test_blocked_capability_rejects_team():

    _, _, team, report = (
        build_valid_team()
    )

    assert report is not None

    governance = TeamReadinessGovernance(
        policy=TeamReadinessPolicy(
            blocked_capabilities={
                "sui_move",
            }
        )
    )

    result = governance.evaluate(
        team=team,
        validation=report,
    )

    assert (
        result.decision
        is TeamReadinessDecision.REJECTED
    )

    assert not result.approved


def test_non_ready_team_cannot_activate():

    _, _, team, report = (
        build_valid_team()
    )

    assert report is not None

    governance = (
        TeamReadinessGovernance()
    )

    readiness = governance.evaluate(
        team=team,
        validation=report,
        environment="mainnet",
    )

    with pytest.raises(
        ValueError,
        match=(
            "team is not approved "
            "for activation"
        ),
    ):
        governance.activate(
            team=team,
            readiness=readiness,
        )
