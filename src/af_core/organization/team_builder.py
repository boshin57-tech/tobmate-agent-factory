from __future__ import annotations

from collections.abc import Callable

from af_core.capability.capability_models import (
    AgentCapability,
)

from .capability_team_selector import (
    CapabilityTeamSelector,
)
from .selection_models import (
    SelectionResult,
)
from .team_models import (
    AgentTeam,
    RoleCriticality,
    TeamBuildRequest,
    TeamMember,
    TeamRoleRequirement,
    TeamStatus,
    UnfilledRole,
)
from .team_repository import (
    TeamRepository,
)
from .team_validator import (
    TeamValidator,
)


AgentProvider = Callable[
    [],
    tuple[AgentCapability, ...],
]


class TeamBuilderEngine:
    """
    Builds capability-ranked and diversity-aware Agent teams.
    """

    def __init__(
        self,
        *,
        agent_provider: AgentProvider,
        repository: TeamRepository | None = None,
        selector: CapabilityTeamSelector | None = None,
        validator: TeamValidator | None = None,
    ) -> None:
        self._agent_provider = agent_provider

        self._repository = (
            repository
            or TeamRepository()
        )

        self._selector = (
            selector
            or CapabilityTeamSelector()
        )

        self._validator = (
            validator
            or TeamValidator()
        )

        self._validation_reports = {}

    def build(
        self,
        request: TeamBuildRequest,
    ) -> AgentTeam:
        available_agents = tuple(
            self._agent_provider()
        )

        selected_agent_ids: set[str] = set()

        selected_profiles: set[
            tuple[str, ...]
        ] = set()

        members: list[
            TeamMember
        ] = []

        unfilled_roles: list[
            UnfilledRole
        ] = []

        selection_metadata: dict[
            str,
            dict[str, object],
        ] = {}

        for requirement in (
            request.role_requirements
        ):
            excluded_agent_ids = (
                set()
                if request.allow_agent_role_reuse
                else selected_agent_ids
            )

            selected, selection = (
                self._selector.select(
                    requirement=requirement,
                    available_agents=(
                        available_agents
                    ),
                    excluded_agent_ids=(
                        excluded_agent_ids
                    ),
                    existing_profiles=(
                        selected_profiles
                    ),
                )
            )

            for agent in selected:
                candidate = (
                    self._candidate_for_agent(
                        selection=selection,
                        agent_id=agent.agent_id,
                    )
                )

                member = self._create_member(
                    requirement=requirement,
                    agent=agent,
                    assignment_score=(
                        candidate.total_score
                        if candidate is not None
                        else 0.0
                    ),
                )

                members.append(member)

                selected_profiles.add(
                    tuple(
                        sorted(
                            agent.capabilities
                        )
                    )
                )

                if not (
                    request
                    .allow_agent_role_reuse
                ):
                    selected_agent_ids.add(
                        agent.agent_id
                    )

            assigned_count = len(
                selected
            )

            selection_metadata[
                requirement.role_name
            ] = self._serialize_selection(
                selection
            )

            if (
                assigned_count
                < requirement.minimum_members
                and requirement.criticality
                is RoleCriticality.REQUIRED
            ):
                unfilled_roles.append(
                    UnfilledRole(
                        role_name=(
                            requirement.role_name
                        ),
                        required_members=(
                            requirement
                            .minimum_members
                        ),
                        assigned_members=(
                            assigned_count
                        ),
                        missing_capabilities=(
                            requirement
                            .required_capabilities
                        ),
                        reason=(
                            "insufficient eligible "
                            "or diverse agents"
                        ),
                    )
                )

        status = (
            TeamStatus.READY
            if not unfilled_roles
            else TeamStatus.FORMING
        )

        team = AgentTeam(
            request_id=request.request_id,
            team_name=request.team_name,
            workspace_id=request.workspace_id,
            objective=request.objective,
            status=status,
            members=members,
            unfilled_roles=unfilled_roles,
            selection_metadata=(
                selection_metadata
            ),
            metadata={
                **request.metadata,
                "requested_by":
                    request.requested_by,
            },
        )

        saved_team = (
            self._repository.save(
                team
            )
        )

        validation = (
            self._validator.validate(
                request=request,
                team=saved_team,
            )
        )

        self._validation_reports[
            saved_team.team_id
        ] = validation

        return saved_team

    @staticmethod
    def _candidate_for_agent(
        *,
        selection: SelectionResult,
        agent_id: str,
    ):
        for candidate in (
            selection.ranked_candidates
        ):
            if candidate.agent_id == agent_id:
                return candidate

        return None

    @staticmethod
    def _create_member(
        *,
        requirement: TeamRoleRequirement,
        agent: AgentCapability,
        assignment_score: float,
    ) -> TeamMember:
        matched_capabilities = (
            requirement.required_capabilities
            .intersection(
                set(agent.capabilities)
            )
        )

        matched_tasks = (
            requirement.supported_tasks
            .intersection(
                set(agent.supported_tasks)
            )
        )

        return TeamMember(
            agent_id=agent.agent_id,
            agent_name=agent.agent_name,
            role_name=requirement.role_name,
            matched_capabilities=(
                matched_capabilities
            ),
            matched_tasks=(
                matched_tasks
            ),
            skill_level=agent.skill_level,
            assignment_score=(
                assignment_score
            ),
            metadata={
                "selection_method":
                    "capability_ranked",
            },
        )

    @staticmethod
    def _serialize_selection(
        selection: SelectionResult,
    ) -> dict[str, object]:
        return {
            "eligible_count":
                selection.eligible_count,

            "selected_count":
                selection.selected_count,

            "selected_agent_ids":
                list(
                    selection
                    .selected_agent_ids
                ),

            "diversity_fallback_used":
                selection
                .diversity_fallback_used,

            "ranked_candidates": [
                {
                    "agent_id":
                        candidate.agent_id,

                    "agent_name":
                        candidate.agent_name,

                    "total_score":
                        candidate.total_score,

                    "capability_profile":
                        list(
                            candidate
                            .capability_profile
                        ),

                    "reasons":
                        list(
                            candidate.reasons
                        ),
                }
                for candidate
                in selection.ranked_candidates
            ],

            "rejection_reasons":
                selection.rejection_reasons,
        }

    def get_team(
        self,
        team_id: str,
    ) -> AgentTeam | None:
        return self._repository.get(
            team_id
        )

    def teams_for_workspace(
        self,
        workspace_id: str,
    ) -> tuple[AgentTeam, ...]:
        return self._repository.by_workspace(
            workspace_id
        )

    def validation_report(
        self,
        team_id: str,
    ):
        return (
            self._validation_reports
            .get(team_id)
        )

    @property
    def team_count(
        self,
    ) -> int:
        return self._repository.count
