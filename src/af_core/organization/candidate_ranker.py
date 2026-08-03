from __future__ import annotations

from af_core.capability.capability_models import (
    AgentCapability,
)

from .selection_models import (
    AgentRankingWeights,
    CandidateScore,
)
from .team_models import (
    TeamRoleRequirement,
)


class CapabilityCandidateRanker:
    """
    Produces explainable Agent ranking scores.

    Eligibility is evaluated separately by the selector. This class only
    ranks Agents that already satisfy the mandatory role requirements.
    """

    def __init__(
        self,
        weights: AgentRankingWeights | None = None,
    ) -> None:
        self._weights = (
            weights
            or AgentRankingWeights()
        )

    def rank(
        self,
        *,
        requirement: TeamRoleRequirement,
        agents: tuple[
            AgentCapability,
            ...
        ],
        existing_profiles: set[
            tuple[str, ...]
        ] | None = None,
    ) -> list[CandidateScore]:
        profiles = (
            existing_profiles
            or set()
        )

        scored = [
            self.score(
                requirement=requirement,
                agent=agent,
                existing_profiles=profiles,
            )
            for agent in agents
        ]

        return sorted(
            scored,
            key=lambda candidate: (
                candidate.total_score,
                candidate.skill_level,
                candidate.agent_id,
            ),
            reverse=True,
        )

    def score(
        self,
        *,
        requirement: TeamRoleRequirement,
        agent: AgentCapability,
        existing_profiles: set[
            tuple[str, ...]
        ] | None = None,
    ) -> CandidateScore:
        existing_profiles = (
            existing_profiles
            or set()
        )

        agent_capabilities = set(
            agent.capabilities
        )

        agent_tasks = set(
            agent.supported_tasks
        )

        matched_capabilities = (
            requirement
            .required_capabilities
            .intersection(
                agent_capabilities
            )
        )

        matched_tasks = (
            requirement
            .supported_tasks
            .intersection(
                agent_tasks
            )
        )

        capability_profile = tuple(
            sorted(agent_capabilities)
        )

        capability_score = (
            len(matched_capabilities)
            * self._weights.capability_match
        )

        task_score = (
            len(matched_tasks)
            * self._weights.task_match
        )

        skill_score = (
            agent.skill_level
            * self._weights.skill_level
        )

        exact_fit_score = 0.0

        if (
            agent_capabilities
            == requirement.required_capabilities
            and requirement.required_capabilities
        ):
            exact_fit_score += (
                self._weights
                .exact_capability_fit
            )

        if (
            agent_tasks
            == requirement.supported_tasks
            and requirement.supported_tasks
        ):
            exact_fit_score += (
                self._weights
                .exact_task_fit
            )

        excess_capabilities = (
            agent_capabilities
            - requirement.required_capabilities
        )

        penalty_score = (
            len(excess_capabilities)
            * self._weights
            .excess_capability_penalty
        )

        specialization_score = 0.0

        if requirement.required_capabilities:
            required_count = len(
                requirement.required_capabilities
            )

            total_count = len(
                agent_capabilities
            )

            if total_count > 0:
                specialization_ratio = (
                    required_count
                    / total_count
                )

                specialization_score = (
                    specialization_ratio
                    * self._weights
                    .specialization_bonus
                )

        diversity_score = 0.0

        if (
            capability_profile
            not in existing_profiles
        ):
            diversity_score = (
                self._weights.diversity_bonus
            )

        total_score = (
            capability_score
            + task_score
            + skill_score
            + exact_fit_score
            + specialization_score
            + diversity_score
            - penalty_score
        )

        reasons = [
            (
                f"matched {len(matched_capabilities)} "
                "required capabilities"
            ),
            (
                f"matched {len(matched_tasks)} "
                "required tasks"
            ),
            (
                f"skill level {agent.skill_level}"
            ),
        ]

        if exact_fit_score:
            reasons.append(
                "exact requirement fit bonus"
            )

        if specialization_score:
            reasons.append(
                "specialization bonus"
            )

        if diversity_score:
            reasons.append(
                "distinct capability profile bonus"
            )

        if penalty_score:
            reasons.append(
                "excess capability penalty"
            )

        return CandidateScore(
            agent_id=agent.agent_id,
            agent_name=agent.agent_name,
            matched_capabilities=(
                matched_capabilities
            ),
            matched_tasks=matched_tasks,
            capability_profile=(
                capability_profile
            ),
            skill_level=agent.skill_level,
            capability_score=(
                capability_score
            ),
            task_score=task_score,
            skill_score=skill_score,
            exact_fit_score=(
                exact_fit_score
            ),
            specialization_score=(
                specialization_score
            ),
            diversity_score=(
                diversity_score
            ),
            penalty_score=(
                penalty_score
            ),
            total_score=round(
                total_score,
                4,
            ),
            reasons=reasons,
        )
