from __future__ import annotations

from af_core.capability.capability_models import (
    AgentCapability,
)
from af_core.organization import (
    AgentRankingWeights,
    CapabilityCandidateRanker,
    CapabilityTeamSelector,
    DiversityPolicy,
    TeamBuildRequest,
    TeamBuilderEngine,
    TeamRoleRequirement,
    TeamStatus,
)


def agent(
    *,
    agent_id: str,
    capabilities: list[str],
    tasks: list[str] | None = None,
    skill_level: int = 3,
    status: str = "active",
) -> AgentCapability:
    return AgentCapability(
        agent_id=agent_id,
        agent_name=agent_id,
        capabilities=capabilities,
        supported_tasks=tasks or [],
        skill_level=skill_level,
        status=status,
    )


def test_ineligible_agent_rejection_is_explained():

    selector = CapabilityTeamSelector()

    requirement = TeamRoleRequirement(
        role_name="Move Developer",
        required_capabilities={
            "sui_move",
        },
        supported_tasks={
            "contract_implementation",
        },
        minimum_skill_level=4,
    )

    agents = (
        agent(
            agent_id="python-agent",
            capabilities=["python"],
            tasks=[
                "contract_implementation"
            ],
            skill_level=5,
        ),
        agent(
            agent_id="junior-move-agent",
            capabilities=["sui_move"],
            tasks=[
                "contract_implementation"
            ],
            skill_level=2,
        ),
    )

    selected, result = selector.select(
        requirement=requirement,
        available_agents=agents,
    )

    assert selected == ()

    assert (
        "missing capabilities: sui_move"
        in result.rejection_reasons[
            "python-agent"
        ]
    )

    assert (
        "skill level below minimum"
        in result.rejection_reasons[
            "junior-move-agent"
        ]
    )


def test_higher_skill_candidate_ranks_first():

    selector = CapabilityTeamSelector()

    requirement = TeamRoleRequirement(
        role_name="Security Reviewer",
        required_capabilities={
            "security_audit",
        },
        supported_tasks={
            "security_review",
        },
    )

    agents = (
        agent(
            agent_id="security-level-3",
            capabilities=[
                "security_audit"
            ],
            tasks=["security_review"],
            skill_level=3,
        ),
        agent(
            agent_id="security-level-5",
            capabilities=[
                "security_audit"
            ],
            tasks=["security_review"],
            skill_level=5,
        ),
    )

    selected, result = selector.select(
        requirement=requirement,
        available_agents=agents,
    )

    assert (
        selected[0].agent_id
        == "security-level-5"
    )

    assert (
        result.ranked_candidates[0]
        .total_score
        >
        result.ranked_candidates[1]
        .total_score
    )


def test_exact_specialist_can_beat_broad_generalist():

    ranker = CapabilityCandidateRanker(
        weights=AgentRankingWeights(
            specialization_bonus=10.0,
            excess_capability_penalty=2.0,
        )
    )

    selector = CapabilityTeamSelector(
        ranker=ranker
    )

    requirement = TeamRoleRequirement(
        role_name="Move Specialist",
        required_capabilities={
            "sui_move",
        },
    )

    agents = (
        agent(
            agent_id="specialist",
            capabilities=["sui_move"],
            skill_level=4,
        ),
        agent(
            agent_id="generalist",
            capabilities=[
                "sui_move",
                "python",
                "frontend",
                "database",
                "devops",
            ],
            skill_level=4,
        ),
    )

    selected, result = selector.select(
        requirement=requirement,
        available_agents=agents,
    )

    assert (
        selected[0].agent_id
        == "specialist"
    )

    assert (
        result.ranked_candidates[0]
        .agent_id
        == "specialist"
    )


def test_diversity_selects_distinct_profiles():

    selector = CapabilityTeamSelector(
        diversity_policy=DiversityPolicy(
            max_same_capability_profile=1
        )
    )

    requirement = TeamRoleRequirement(
        role_name="Development Team",
        required_capabilities={
            "python",
        },
        minimum_members=2,
        maximum_members=2,
    )

    agents = (
        agent(
            agent_id="python-a",
            capabilities=[
                "python",
                "database",
            ],
            skill_level=5,
        ),
        agent(
            agent_id="python-b",
            capabilities=[
                "python",
                "database",
            ],
            skill_level=4,
        ),
        agent(
            agent_id="python-devops",
            capabilities=[
                "python",
                "devops",
            ],
            skill_level=4,
        ),
    )

    selected, result = selector.select(
        requirement=requirement,
        available_agents=agents,
    )

    selected_ids = {
        item.agent_id
        for item in selected
    }

    assert "python-a" in selected_ids

    assert (
        "python-devops"
        in selected_ids
    )

    assert (
        "python-b"
        not in selected_ids
    )

    assert not (
        result.diversity_fallback_used
    )


def test_diversity_fallback_fills_required_seats():

    selector = CapabilityTeamSelector(
        diversity_policy=DiversityPolicy(
            max_same_capability_profile=1,
            allow_profile_limit_fallback=True,
        )
    )

    requirement = TeamRoleRequirement(
        role_name="Move Team",
        required_capabilities={
            "sui_move",
        },
        minimum_members=2,
        maximum_members=2,
    )

    agents = (
        agent(
            agent_id="move-a",
            capabilities=[
                "sui_move",
                "smart_contract",
            ],
            skill_level=5,
        ),
        agent(
            agent_id="move-b",
            capabilities=[
                "sui_move",
                "smart_contract",
            ],
            skill_level=4,
        ),
    )

    selected, result = selector.select(
        requirement=requirement,
        available_agents=agents,
    )

    assert len(selected) == 2

    assert (
        result.diversity_fallback_used
    )


def test_team_builder_records_selection_metadata():

    agents = (
        agent(
            agent_id="architect-agent",
            capabilities=[
                "architecture"
            ],
            tasks=["system_design"],
            skill_level=5,
        ),
    )

    builder = TeamBuilderEngine(
        agent_provider=lambda: agents
    )

    request = TeamBuildRequest(
        team_name="Architecture Team",
        workspace_id="workspace-001",
        objective="Design GSOS component",
        requested_by="manager-agent",
        role_requirements=[
            TeamRoleRequirement(
                role_name="Architect",
                required_capabilities={
                    "architecture"
                },
                supported_tasks={
                    "system_design"
                },
            )
        ],
    )

    team = builder.build(request)

    metadata = (
        team.selection_metadata[
            "Architect"
        ]
    )

    assert (
        team.status
        is TeamStatus.READY
    )

    assert (
        metadata["selected_agent_ids"]
        == ["architect-agent"]
    )

    assert (
        metadata["eligible_count"]
        == 1
    )

    assert (
        metadata["ranked_candidates"][0][
            "total_score"
        ]
        > 0
    )


def test_already_assigned_agent_is_excluded():

    selector = CapabilityTeamSelector()

    requirement = TeamRoleRequirement(
        role_name="Planner",
        required_capabilities={
            "planning",
        },
    )

    agents = (
        agent(
            agent_id="planner-agent",
            capabilities=["planning"],
            skill_level=5,
        ),
    )

    selected, result = selector.select(
        requirement=requirement,
        available_agents=agents,
        excluded_agent_ids={
            "planner-agent"
        },
    )

    assert selected == ()

    assert (
        "agent excluded or already assigned"
        in result.rejection_reasons[
            "planner-agent"
        ]
    )
