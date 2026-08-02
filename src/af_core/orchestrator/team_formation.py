"""Capability-aware team formation for multi-agent coordination."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from af_core.orchestrator.coordination_models import (
    CoordinationAgent,
    CoordinationAgentStatus,
    CoordinationTask,
)
from af_core.orchestrator.coordination_registry import (
    CoordinationRegistry,
)


class TeamFormationError(RuntimeError):
    pass


class TeamMemberSelection(BaseModel):
    model_config = ConfigDict(frozen=True)

    agent_id: str
    matched_capability_ids: frozenset[str]
    current_task_count: int
    capacity_remaining: int


class TeamFormationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    task_id: str
    selected_agent_ids: tuple[str, ...]
    selections: tuple[TeamMemberSelection, ...]
    uncovered_capability_ids: frozenset[str] = frozenset()

    @property
    def complete(self) -> bool:
        return not self.uncovered_capability_ids


class TeamFormationEngine:
    def __init__(
        self,
        *,
        registry: CoordinationRegistry,
    ) -> None:
        self._registry = registry

    def form_team(
        self,
        task: CoordinationTask,
        *,
        maximum_team_size: int | None = None,
    ) -> TeamFormationResult:
        required = set(task.required_capability_ids)

        candidates = [
            agent
            for agent in self._registry.list_agents()
            if self._eligible(agent)
        ]

        selections: list[TeamMemberSelection] = []
        selected_ids: list[str] = []
        uncovered = set(required)

        while uncovered:
            candidate = self._best_candidate(
                candidates=candidates,
                uncovered=uncovered,
                selected_ids=set(selected_ids),
            )

            if candidate is None:
                break

            matched = frozenset(
                candidate.capability_ids.intersection(
                    uncovered
                )
            )

            active_count = (
                self._registry.active_task_count(
                    candidate.agent_id
                )
            )

            selections.append(
                TeamMemberSelection(
                    agent_id=candidate.agent_id,
                    matched_capability_ids=matched,
                    current_task_count=active_count,
                    capacity_remaining=(
                        candidate.maximum_parallel_tasks
                        - active_count
                    ),
                )
            )
            selected_ids.append(candidate.agent_id)
            uncovered.difference_update(matched)

            if (
                maximum_team_size is not None
                and len(selected_ids) >= maximum_team_size
            ):
                break

        return TeamFormationResult(
            task_id=task.task_id,
            selected_agent_ids=tuple(selected_ids),
            selections=tuple(selections),
            uncovered_capability_ids=frozenset(uncovered),
        )

    def require_complete_team(
        self,
        task: CoordinationTask,
        *,
        maximum_team_size: int | None = None,
    ) -> TeamFormationResult:
        result = self.form_team(
            task,
            maximum_team_size=maximum_team_size,
        )

        if not result.complete:
            missing = ", ".join(
                sorted(result.uncovered_capability_ids)
            )
            raise TeamFormationError(
                "Unable to cover required capabilities: "
                f"{missing}"
            )

        return result

    def _best_candidate(
        self,
        *,
        candidates: list[CoordinationAgent],
        uncovered: set[str],
        selected_ids: set[str],
    ) -> CoordinationAgent | None:
        ranked: list[
            tuple[int, int, str, CoordinationAgent]
        ] = []

        for agent in candidates:
            if agent.agent_id in selected_ids:
                continue

            matched_count = len(
                agent.capability_ids.intersection(uncovered)
            )

            if matched_count == 0:
                continue

            active_count = (
                self._registry.active_task_count(
                    agent.agent_id
                )
            )
            remaining = (
                agent.maximum_parallel_tasks
                - active_count
            )

            if remaining <= 0:
                continue

            ranked.append(
                (
                    matched_count,
                    remaining,
                    agent.agent_id,
                    agent,
                )
            )

        if not ranked:
            return None

        ranked.sort(
            key=lambda item: (
                -item[0],
                -item[1],
                item[2],
            )
        )

        return ranked[0][3]

    @staticmethod
    def _eligible(
        agent: CoordinationAgent,
    ) -> bool:
        return agent.status in {
            CoordinationAgentStatus.ACTIVE,
            CoordinationAgentStatus.BUSY,
        }
