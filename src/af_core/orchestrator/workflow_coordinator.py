"""Workflow coordination adapter.

Connects workflow scheduling with multi-agent coordination.
"""

from __future__ import annotations

from af_core.orchestrator.coordination_models import (
    CoordinationDecision,
    CoordinationTask,
)
from af_core.orchestrator.coordination_registry import (
    CoordinationRegistry,
)
from af_core.orchestrator.team_formation import (
    TeamFormationEngine,
)
from af_core.orchestrator.authority_coordination import (
    AuthorityAwareCoordinationEngine,
)
from af_core.orchestrator.workflow_engine import (
    WorkflowEngine,
)
from af_core.orchestrator.workflow_models import (
    WorkflowScheduleDecision,
    WorkflowStepStatus,
)


class WorkflowCoordinatorError(RuntimeError):
    pass


class WorkflowCoordinator:
    def __init__(
        self,
        *,
        workflow_engine: WorkflowEngine,
        coordination_registry: CoordinationRegistry,
        team_builder: TeamFormationEngine,
        authority_coordination: (
            AuthorityAwareCoordinationEngine
        ),
    ) -> None:
        self._workflow = workflow_engine
        self._registry = coordination_registry
        self._team_builder = team_builder
        self._authority = authority_coordination

    def schedule_and_assign(
        self,
        *,
        run_id: str,
    ) -> tuple[
        WorkflowScheduleDecision,
        ...,
    ]:
        decisions = (
            self._workflow.schedule_ready(
                run_id
            )
        )

        results: list[
            WorkflowScheduleDecision
        ] = []

        for decision in decisions:
            if decision.step_id is None:
                results.append(decision)
                continue

            step = self._find_step(
                run_id,
                decision.step_id,
            )

            coordination_task = CoordinationTask(
                task_id=step.step_id,
                name=step.name,
                required_capability_ids=(
                    step.required_capability_ids
                ),
            )

            team = (
                self._team_builder.require_complete_team(
                    coordination_task
                )
            )

            assigned = False

            for agent_id in (
                team.selected_agent_ids
            ):
                assignment = (
                    self._authority.assign(
                        task_id=step.step_id,
                        agent_id=agent_id,
                    )
                )

                if assignment.decision in {
                    CoordinationDecision.ASSIGN,
                    CoordinationDecision.REASSIGN,
                }:
                    assigned = True

                    updated = (
                        self._replace_step_assignment(
                            run_id,
                            step.step_id,
                            agent_id,
                        )
                    )

                    break

            if not assigned:
                raise WorkflowCoordinatorError(
                    "No authorized agent available "
                    f"for step {step.step_id}"
                )

            results.append(decision)

        return tuple(results)

    def _find_step(
        self,
        run_id: str,
        step_id: str,
    ):
        run = self._workflow.get_run(run_id)

        for step in run.steps:
            if step.step_id == step_id:
                return step

        raise WorkflowCoordinatorError(
            f"Unknown workflow step: {step_id}"
        )

    def _replace_step_assignment(
        self,
        run_id: str,
        step_id: str,
        agent_id: str,
    ):
        run = self._workflow.get_run(run_id)

        updated_steps = tuple(
            step.model_copy(
                update={
                    "status": (
                        WorkflowStepStatus.READY
                    ),
                    "assigned_agent_id": agent_id,
                }
            )
            if step.step_id == step_id
            else step
            for step in run.steps
        )

        updated = run.model_copy(
            update={
                "steps": updated_steps,
            }
        )

        return self._workflow._save(
            updated
        )
