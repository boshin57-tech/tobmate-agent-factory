from __future__ import annotations

from af_core.capability.capability_models import (
    AgentCapability,
)

from .candidate_ranker import (
    CapabilityCandidateRanker,
)
from .selection_models import (
    DiversityPolicy,
    SelectionResult,
)
from .team_models import (
    TeamRoleRequirement,
)


class CapabilityTeamSelector:
    """
    Selects the best Agents for one team role.

    Mandatory eligibility:
    - Agent status must be active.
    - Skill level must meet the role minimum.
    - Every required capability must be present.
    - Every supported task requirement must be present.
    - Excluded Agent IDs are never selected.

    Diversity:
    - Avoids repeated capability profiles when possible.
    - Can fall back to repeated profiles if otherwise the role cannot
      reach its requested member count.
    """

    def __init__(
        self,
        *,
        ranker: CapabilityCandidateRanker | None = None,
        diversity_policy: DiversityPolicy | None = None,
    ) -> None:
        self._ranker = (
            ranker
            or CapabilityCandidateRanker()
        )

        self._diversity_policy = (
            diversity_policy
            or DiversityPolicy()
        )

    def select(
        self,
        *,
        requirement: TeamRoleRequirement,
        available_agents: tuple[
            AgentCapability,
            ...
        ],
        excluded_agent_ids: set[str] | None = None,
        existing_profiles: set[
            tuple[str, ...]
        ] | None = None,
    ) -> tuple[
        tuple[AgentCapability, ...],
        SelectionResult,
    ]:
        excluded_agent_ids = (
            excluded_agent_ids
            or set()
        )

        existing_profiles = (
            existing_profiles
            or set()
        )

        eligible: list[
            AgentCapability
        ] = []

        rejection_reasons: dict[
            str,
            list[str],
        ] = {}

        for agent in available_agents:
            reasons = self._rejection_reasons(
                requirement=requirement,
                agent=agent,
                excluded_agent_ids=(
                    excluded_agent_ids
                ),
            )

            if reasons:
                rejection_reasons[
                    agent.agent_id
                ] = reasons
                continue

            eligible.append(agent)

        ranked = self._ranker.rank(
            requirement=requirement,
            agents=tuple(eligible),
            existing_profiles=(
                existing_profiles
            ),
        )

        agents_by_id = {
            agent.agent_id: agent
            for agent in eligible
        }

        selected_ids: list[str] = []
        profile_counts: dict[
            tuple[str, ...],
            int,
        ] = {}

        deferred_ids: list[str] = []

        for candidate in ranked:
            if (
                len(selected_ids)
                >= requirement.maximum_members
            ):
                break

            if not self._diversity_policy.enabled:
                selected_ids.append(
                    candidate.agent_id
                )
                continue

            profile = (
                candidate.capability_profile
            )

            profile_count = (
                profile_counts.get(
                    profile,
                    0,
                )
            )

            if (
                self._diversity_policy
                .prefer_distinct_capability_profiles
                and profile_count
                >= self._diversity_policy
                .max_same_capability_profile
            ):
                deferred_ids.append(
                    candidate.agent_id
                )
                continue

            selected_ids.append(
                candidate.agent_id
            )

            profile_counts[profile] = (
                profile_count + 1
            )

        diversity_fallback_used = False

        if (
            len(selected_ids)
            < requirement.minimum_members
            and self._diversity_policy
            .allow_profile_limit_fallback
        ):
            diversity_fallback_used = True

            for agent_id in deferred_ids:
                if (
                    len(selected_ids)
                    >= requirement.maximum_members
                ):
                    break

                selected_ids.append(
                    agent_id
                )

                if (
                    len(selected_ids)
                    >= requirement.minimum_members
                ):
                    break

        selected_agents = tuple(
            agents_by_id[agent_id]
            for agent_id in selected_ids
        )

        result = SelectionResult(
            role_name=requirement.role_name,
            selected_agent_ids=(
                selected_ids
            ),
            ranked_candidates=ranked,
            eligible_count=len(eligible),
            selected_count=(
                len(selected_agents)
            ),
            diversity_fallback_used=(
                diversity_fallback_used
            ),
            rejection_reasons=(
                rejection_reasons
            ),
        )

        return (
            selected_agents,
            result,
        )

    @staticmethod
    def _rejection_reasons(
        *,
        requirement: TeamRoleRequirement,
        agent: AgentCapability,
        excluded_agent_ids: set[str],
    ) -> list[str]:
        reasons: list[str] = []

        if agent.agent_id in excluded_agent_ids:
            reasons.append(
                "agent excluded or already assigned"
            )

        if agent.status != "active":
            reasons.append(
                "agent is not active"
            )

        if (
            agent.skill_level
            < requirement.minimum_skill_level
        ):
            reasons.append(
                "skill level below minimum"
            )

        missing_capabilities = (
            requirement.required_capabilities
            - set(agent.capabilities)
        )

        if missing_capabilities:
            reasons.append(
                "missing capabilities: "
                + ", ".join(
                    sorted(
                        missing_capabilities
                    )
                )
            )

        missing_tasks = (
            requirement.supported_tasks
            - set(agent.supported_tasks)
        )

        if missing_tasks:
            reasons.append(
                "missing tasks: "
                + ", ".join(
                    sorted(missing_tasks)
                )
            )

        return reasons
