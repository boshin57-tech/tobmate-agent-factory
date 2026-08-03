from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from af_core.capability.capability_models import (
    AgentCapability,
)

from .dynamic_role_models import (
    DynamicRoleAssignment,
    RoleAssignmentRequest,
    RoleAssignmentResult,
    RoleAssignmentStatus,
    RoleCandidateEvaluation,
)
from .role_assignment_repository import (
    RoleAssignmentRepository,
)
from .agent_runtime_metrics import (
    AgentRuntimeMetrics,
)
from .agent_runtime_repository import (
    AgentRuntimeMetricsRepository,
)
from .runtime_agent_scorer import (
    RuntimeAgentScorer,
)


DynamicAgentProvider = Callable[
    [],
    tuple[AgentCapability, ...],
]


class DynamicRoleAssignmentEngine:
    """
    Assigns runtime roles to eligible Agents.

    Initial policy:
    - Agent must be active.
    - Agent must satisfy every capability requirement.
    - Agent must satisfy every task requirement.
    - Agent must meet minimum skill level.
    - Current Agent is excluded during reassignment.
    - Exclusive roles avoid Agents already holding active roles.
    - Higher capability, task, and skill scores rank first.
    """

    def __init__(
        self,
        *,
        agent_provider: DynamicAgentProvider,
        repository: (
            RoleAssignmentRepository
            | None
        ) = None,
        runtime_repository: (
            AgentRuntimeMetricsRepository
            | None
        ) = None,
        runtime_scorer: (
            RuntimeAgentScorer
            | None
        ) = None,
        require_runtime_metrics: bool = False,
    ) -> None:
        self._agent_provider = (
            agent_provider
        )

        self._repository = (
            repository
            or RoleAssignmentRepository()
        )

        self._runtime_repository = (
            runtime_repository
            or AgentRuntimeMetricsRepository()
        )

        self._runtime_scorer = (
            runtime_scorer
            or RuntimeAgentScorer()
        )

        self._require_runtime_metrics = (
            require_runtime_metrics
        )

    def assign(
        self,
        request: RoleAssignmentRequest,
    ) -> RoleAssignmentResult:
        agents = tuple(
            self._agent_provider()
        )

        evaluations = [
            self._evaluate_candidate(
                request=request,
                agent=agent,
            )
            for agent in agents
        ]

        eligible = [
            evaluation
            for evaluation in evaluations
            if evaluation.eligible
        ]

        eligible.sort(
            key=lambda evaluation: (
                evaluation.score,
                evaluation.skill_level,
                evaluation.agent_id,
            ),
            reverse=True,
        )

        limit = (
            request.requirement
            .maximum_assignments
        )

        selected = eligible[:limit]

        assignments: list[
            DynamicRoleAssignment
        ] = []

        for evaluation in selected:
            assignment = (
                DynamicRoleAssignment(
                    request_id=(
                        request.request_id
                    ),
                    team_id=request.team_id,
                    workspace_id=(
                        request.workspace_id
                    ),
                    role_name=(
                        request.requirement
                        .role_name
                    ),
                    agent_id=(
                        evaluation.agent_id
                    ),
                    agent_name=(
                        evaluation.agent_name
                    ),
                    action=request.action,
                    reason=request.reason,
                    status=(
                        RoleAssignmentStatus
                        .PROPOSED
                    ),
                    replaced_agent_id=(
                        request.current_agent_id
                    ),
                    matched_capabilities=(
                        evaluation
                        .matched_capabilities
                    ),
                    matched_tasks=(
                        evaluation
                        .matched_tasks
                    ),
                    assignment_score=(
                        evaluation.score
                    ),
                    metadata={
                        **request.metadata,
                        "requested_by":
                            request.requested_by,
                    },
                )
            )

            assignments.append(
                self._repository.save(
                    assignment
                )
            )

        completed = len(
            assignments
        )

        required = (
            request.requirement
            .minimum_assignments
        )

        fulfilled = (
            completed >= required
        )

        reasons: list[str] = []

        if fulfilled:
            reasons.append(
                "minimum role assignment "
                "requirement satisfied"
            )
        else:
            reasons.append(
                "insufficient eligible agents "
                "for role assignment"
            )

        return RoleAssignmentResult(
            request_id=request.request_id,
            team_id=request.team_id,
            assignments=assignments,
            candidates=evaluations,
            fulfilled=fulfilled,
            required_assignments=required,
            completed_assignments=(
                completed
            ),
            reasons=reasons,
        )

    def activate(
        self,
        assignment_id: str,
    ) -> DynamicRoleAssignment:
        assignment = (
            self._require_assignment(
                assignment_id
            )
        )

        if (
            assignment.status
            not in {
                RoleAssignmentStatus
                .PROPOSED,
                RoleAssignmentStatus
                .APPROVED,
            }
        ):
            raise ValueError(
                "assignment cannot be "
                "activated from current status"
            )

        active = assignment.model_copy(
            update={
                "status":
                    RoleAssignmentStatus.ACTIVE,

                "activated_at":
                    datetime.now(
                        timezone.utc
                    ),
            }
        )

        return self._repository.replace(
            active
        )

    def approve(
        self,
        assignment_id: str,
    ) -> DynamicRoleAssignment:
        assignment = (
            self._require_assignment(
                assignment_id
            )
        )

        if (
            assignment.status
            is not RoleAssignmentStatus
            .PROPOSED
        ):
            raise ValueError(
                "only proposed assignments "
                "can be approved"
            )

        approved = assignment.model_copy(
            update={
                "status":
                    RoleAssignmentStatus
                    .APPROVED,
            }
        )

        return self._repository.replace(
            approved
        )

    def release(
        self,
        assignment_id: str,
    ) -> DynamicRoleAssignment:
        assignment = (
            self._require_assignment(
                assignment_id
            )
        )

        if (
            assignment.status
            is RoleAssignmentStatus.RELEASED
        ):
            raise ValueError(
                "assignment is already released"
            )

        released = assignment.model_copy(
            update={
                "status":
                    RoleAssignmentStatus
                    .RELEASED,

                "released_at":
                    datetime.now(
                        timezone.utc
                    ),
            }
        )

        return self._repository.replace(
            released
        )

    def assignments_for_team(
        self,
        team_id: str,
    ) -> tuple[
        DynamicRoleAssignment,
        ...
    ]:
        return (
            self._repository
            .active_for_team(team_id)
        )

    def assignments_for_role(
        self,
        *,
        team_id: str,
        role_name: str,
    ) -> tuple[
        DynamicRoleAssignment,
        ...
    ]:
        return (
            self._repository
            .active_for_role(
                team_id=team_id,
                role_name=role_name,
            )
        )

    def _evaluate_candidate(
        self,
        *,
        request: RoleAssignmentRequest,
        agent: AgentCapability,
    ) -> RoleCandidateEvaluation:
        requirement = (
            request.requirement
        )

        runtime_metrics = (
            self._runtime_repository
            .get(agent.agent_id)
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
            .required_tasks
            .intersection(
                agent_tasks
            )
        )

        missing_capabilities = (
            requirement
            .required_capabilities
            - agent_capabilities
        )

        missing_tasks = (
            requirement
            .required_tasks
            - agent_tasks
        )

        rejection_reasons: list[
            str
        ] = []

        if agent.status != "active":
            rejection_reasons.append(
                "agent is not active"
            )

        if (
            agent.skill_level
            < requirement
            .minimum_skill_level
        ):
            rejection_reasons.append(
                "skill level below minimum"
            )

        if missing_capabilities:
            rejection_reasons.append(
                "missing capabilities: "
                + ", ".join(
                    sorted(
                        missing_capabilities
                    )
                )
            )

        if missing_tasks:
            rejection_reasons.append(
                "missing tasks: "
                + ", ".join(
                    sorted(missing_tasks)
                )
            )

        if (
            request.current_agent_id
            == agent.agent_id
        ):
            rejection_reasons.append(
                "current agent excluded "
                "from reassignment"
            )

        if (
            requirement.exclusive
            and self._repository
            .active_for_agent(
                agent.agent_id
            )
        ):
            rejection_reasons.append(
                "agent already holds "
                "an active exclusive role"
            )

        runtime_score = 0.0
        runtime_reasons: list[str] = []
        runtime_metrics_available = (
            runtime_metrics is not None
        )

        if runtime_metrics is None:
            if self._require_runtime_metrics:
                rejection_reasons.append(
                    "runtime metrics are required "
                    "but unavailable"
                )
        else:
            runtime_breakdown = (
                self._runtime_scorer.score(
                    runtime_metrics
                )
            )

            runtime_score = (
                runtime_breakdown.total_score
            )

            runtime_reasons = list(
                runtime_breakdown.reasons
            )

            if not runtime_breakdown.eligible:
                rejection_reasons.extend(
                    runtime_breakdown.reasons
                )

        eligible = not (
            rejection_reasons
        )

        capability_score = 0.0
        score = 0.0

        if eligible:
            capability_score = float(
                len(
                    matched_capabilities
                )
                * 10
                + len(
                    matched_tasks
                )
                * 5
                + agent.skill_level
                * 2
                + requirement.priority
            )

            score = (
                capability_score
                + runtime_score
            )

        return RoleCandidateEvaluation(
            agent_id=agent.agent_id,
            agent_name=agent.agent_name,
            eligible=eligible,
            matched_capabilities=(
                matched_capabilities
            ),
            matched_tasks=(
                matched_tasks
            ),
            missing_capabilities=(
                missing_capabilities
            ),
            missing_tasks=missing_tasks,
            skill_level=agent.skill_level,
            capability_score=(
                capability_score
            ),
            runtime_score=(
                runtime_score
            ),
            score=score,
            runtime_metrics_available=(
                runtime_metrics_available
            ),
            runtime_reasons=(
                runtime_reasons
            ),
            rejection_reasons=(
                rejection_reasons
            ),
        )

    def _require_assignment(
        self,
        assignment_id: str,
    ) -> DynamicRoleAssignment:
        assignment = (
            self._repository.get(
                assignment_id
            )
        )

        if assignment is None:
            raise ValueError(
                "role assignment not found"
            )

        return assignment

    def update_runtime_metrics(
        self,
        metrics: AgentRuntimeMetrics,
    ) -> AgentRuntimeMetrics:
        return (
            self._runtime_repository
            .upsert(metrics)
        )

    def runtime_metrics(
        self,
        agent_id: str,
    ) -> AgentRuntimeMetrics | None:
        return (
            self._runtime_repository
            .get(agent_id)
        )

    @property
    def assignment_count(
        self,
    ) -> int:
        return self._repository.count
