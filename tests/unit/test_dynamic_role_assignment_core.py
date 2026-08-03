from __future__ import annotations

import pytest

from af_core.capability.capability_models import (
    AgentCapability,
)
from af_core.organization import (
    DynamicRoleAssignmentEngine,
    DynamicRoleRequirement,
    RoleAssignmentAction,
    RoleAssignmentReason,
    RoleAssignmentRequest,
    RoleAssignmentStatus,
)


def make_agents() -> tuple[
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
            agent_id="python-agent",
            agent_name="Python Agent",
            capabilities=[
                "python",
            ],
            supported_tasks=[
                "backend_implementation",
            ],
            skill_level=5,
        ),
        AgentCapability(
            agent_id="inactive-move-agent",
            agent_name=(
                "Inactive Move Agent"
            ),
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


def make_request(
    **overrides,
) -> RoleAssignmentRequest:
    values = {
        "team_id": "team-001",
        "workspace_id":
            "blockchain-workspace",
        "requirement":
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
            ),
        "action":
            RoleAssignmentAction.ASSIGN,
        "reason":
            RoleAssignmentReason
            .CAPABILITY_MATCH,
        "requested_by":
            "team-manager-agent",
    }

    values.update(overrides)

    return RoleAssignmentRequest(
        **values
    )


def test_best_candidate_is_proposed():

    engine = (
        DynamicRoleAssignmentEngine(
            agent_provider=make_agents
        )
    )

    result = engine.assign(
        make_request()
    )

    assert result.fulfilled

    assert (
        result.completed_assignments
        == 1
    )

    assignment = (
        result.assignments[0]
    )

    assert (
        assignment.agent_id
        == "move-agent-1"
    )

    assert (
        assignment.status
        is RoleAssignmentStatus
        .PROPOSED
    )

    assert (
        assignment.assignment_score
        > 0
    )


def test_ineligible_candidates_are_explained():

    engine = (
        DynamicRoleAssignmentEngine(
            agent_provider=make_agents
        )
    )

    result = engine.assign(
        make_request()
    )

    evaluations = {
        candidate.agent_id:
            candidate
        for candidate
        in result.candidates
    }

    assert not (
        evaluations[
            "python-agent"
        ].eligible
    )

    assert (
        "missing capabilities"
        in " ".join(
            evaluations[
                "python-agent"
            ].rejection_reasons
        )
    )

    assert not (
        evaluations[
            "inactive-move-agent"
        ].eligible
    )

    assert (
        "agent is not active"
        in evaluations[
            "inactive-move-agent"
        ].rejection_reasons
    )


def test_assignment_can_be_approved_and_activated():

    engine = (
        DynamicRoleAssignmentEngine(
            agent_provider=make_agents
        )
    )

    result = engine.assign(
        make_request()
    )

    assignment = (
        result.assignments[0]
    )

    approved = engine.approve(
        assignment.assignment_id
    )

    assert (
        approved.status
        is RoleAssignmentStatus
        .APPROVED
    )

    active = engine.activate(
        assignment.assignment_id
    )

    assert (
        active.status
        is RoleAssignmentStatus.ACTIVE
    )

    assert active.activated_at is not None

    assert (
        engine.assignments_for_team(
            "team-001"
        )
        == (active,)
    )


def test_active_assignment_can_be_released():

    engine = (
        DynamicRoleAssignmentEngine(
            agent_provider=make_agents
        )
    )

    result = engine.assign(
        make_request()
    )

    assignment = (
        result.assignments[0]
    )

    engine.activate(
        assignment.assignment_id
    )

    released = engine.release(
        assignment.assignment_id
    )

    assert (
        released.status
        is RoleAssignmentStatus
        .RELEASED
    )

    assert released.released_at is not None

    assert (
        engine.assignments_for_team(
            "team-001"
        )
        == ()
    )


def test_current_agent_is_excluded_from_reassignment():

    engine = (
        DynamicRoleAssignmentEngine(
            agent_provider=make_agents
        )
    )

    request = make_request(
        action=(
            RoleAssignmentAction
            .REASSIGN
        ),
        current_agent_id=(
            "move-agent-1"
        ),
        reason=(
            RoleAssignmentReason
            .AGENT_UNAVAILABLE
        ),
    )

    result = engine.assign(
        request
    )

    assert result.fulfilled

    assert (
        result.assignments[0]
        .agent_id
        == "move-agent-2"
    )

    assert (
        result.assignments[0]
        .replaced_agent_id
        == "move-agent-1"
    )


def test_missing_capability_leaves_role_unfulfilled():

    engine = (
        DynamicRoleAssignmentEngine(
            agent_provider=make_agents
        )
    )

    request = make_request(
        requirement=(
            DynamicRoleRequirement(
                role_name=(
                    "Robotics Engineer"
                ),
                required_capabilities={
                    "robotics",
                },
            )
        )
    )

    result = engine.assign(
        request
    )

    assert not result.fulfilled

    assert result.assignments == []

    assert (
        result.completed_assignments
        == 0
    )


def test_invalid_transition_is_rejected():

    engine = (
        DynamicRoleAssignmentEngine(
            agent_provider=make_agents
        )
    )

    result = engine.assign(
        make_request()
    )

    assignment = (
        result.assignments[0]
    )

    engine.release(
        assignment.assignment_id
    )

    with pytest.raises(
        ValueError,
        match=(
            "assignment cannot be "
            "activated"
        ),
    ):
        engine.activate(
            assignment.assignment_id
        )
