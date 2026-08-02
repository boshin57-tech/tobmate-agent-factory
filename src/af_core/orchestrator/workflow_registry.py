"""Workflow registry and DAG validation."""

from __future__ import annotations

from threading import RLock

from af_core.orchestrator.workflow_models import (
    WorkflowDefinition,
    WorkflowStep,
)


class WorkflowRegistryError(RuntimeError):
    pass


class WorkflowRegistry:
    def __init__(self) -> None:
        self._definitions: dict[
            str,
            WorkflowDefinition,
        ] = {}
        self._lock = RLock()

    def register(
        self,
        workflow: WorkflowDefinition,
        *,
        replace: bool = False,
    ) -> WorkflowDefinition:
        self.validate(workflow)

        with self._lock:
            existing = self._definitions.get(
                workflow.workflow_id
            )

            if existing is not None and not replace:
                raise WorkflowRegistryError(
                    "Workflow already registered: "
                    f"{workflow.workflow_id}"
                )

            if (
                existing is not None
                and workflow.version <= existing.version
            ):
                raise WorkflowRegistryError(
                    "Replacement workflow version "
                    "must increase"
                )

            self._definitions[
                workflow.workflow_id
            ] = workflow

            return workflow

    def get(
        self,
        workflow_id: str,
    ) -> WorkflowDefinition:
        with self._lock:
            try:
                return self._definitions[workflow_id]
            except KeyError as exc:
                raise WorkflowRegistryError(
                    f"Unknown workflow: {workflow_id}"
                ) from exc

    def list_workflows(
        self,
    ) -> tuple[WorkflowDefinition, ...]:
        with self._lock:
            return tuple(
                sorted(
                    self._definitions.values(),
                    key=lambda item: item.workflow_id,
                )
            )

    def validate(
        self,
        workflow: WorkflowDefinition,
    ) -> None:
        step_ids = [
            step.step_id
            for step in workflow.steps
        ]

        if len(step_ids) != len(set(step_ids)):
            raise WorkflowRegistryError(
                "Workflow step IDs must be unique"
            )

        known = set(step_ids)

        for step in workflow.steps:
            missing = (
                set(step.dependency_ids) - known
            )

            if missing:
                raise WorkflowRegistryError(
                    "Unknown workflow dependencies: "
                    + ", ".join(sorted(missing))
                )

            if (
                step.compensation_step_id is not None
                and step.compensation_step_id not in known
            ):
                raise WorkflowRegistryError(
                    "Unknown compensation step: "
                    f"{step.compensation_step_id}"
                )

            if step.step_id in step.dependency_ids:
                raise WorkflowRegistryError(
                    "Workflow step cannot depend on itself: "
                    f"{step.step_id}"
                )

        self._validate_acyclic(workflow.steps)

    def topological_order(
        self,
        workflow_id: str,
    ) -> tuple[str, ...]:
        workflow = self.get(workflow_id)

        dependencies = {
            step.step_id: set(step.dependency_ids)
            for step in workflow.steps
        }

        order: list[str] = []

        while dependencies:
            ready = sorted(
                step_id
                for step_id, required
                in dependencies.items()
                if not required
            )

            if not ready:
                raise WorkflowRegistryError(
                    "Workflow dependency cycle detected"
                )

            order.extend(ready)

            for step_id in ready:
                dependencies.pop(step_id)

            for required in dependencies.values():
                required.difference_update(ready)

        return tuple(order)

    @staticmethod
    def _validate_acyclic(
        steps: tuple[WorkflowStep, ...],
    ) -> None:
        dependencies = {
            step.step_id: set(step.dependency_ids)
            for step in steps
        }

        while dependencies:
            ready = [
                step_id
                for step_id, required
                in dependencies.items()
                if not required
            ]

            if not ready:
                raise WorkflowRegistryError(
                    "Workflow dependency cycle detected"
                )

            for step_id in ready:
                dependencies.pop(step_id)

            for required in dependencies.values():
                required.difference_update(ready)
