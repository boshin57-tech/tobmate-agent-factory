"""Models and state registry for the unified workflow runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

from af_core.orchestrator.workflow_dependency_graph import (
    WorkflowDependencyGraph,
)
from af_core.orchestrator.workflow_priority_scheduler import (
    WorkflowScheduleCandidate,
)
from af_core.orchestrator.workflow_runtime_observability import (
    WorkflowRuntimeMetrics,
)
from af_core.orchestrator.workflow_trigger_engine import (
    WorkflowTriggerActivation,
)


class WorkflowRuntimeError(ValueError):
    """Raised when unified workflow runtime usage is invalid."""


CapabilityResolver = Callable[
    [WorkflowTriggerActivation],
    Iterable[str],
]

MetadataResolver = Callable[
    [WorkflowTriggerActivation],
    Mapping[str, object],
]


@dataclass(frozen=True, slots=True)
class WorkflowRuntimeProcessResult:
    """Result of trigger and dependency processing."""

    event_activations: tuple[
        WorkflowTriggerActivation,
        ...,
    ]
    dependency_activations: tuple[
        WorkflowTriggerActivation,
        ...,
    ]
    queued: tuple[
        WorkflowScheduleCandidate,
        ...,
    ]


@dataclass(frozen=True, slots=True)
class WorkflowRuntimeSnapshot:
    """Current status of one workflow runtime instance."""

    workflow_id: str
    states: Mapping[str, object]
    pending_count: int
    inflight_count: int
    retry_waiting_count: int
    metrics: WorkflowRuntimeMetrics


class WorkflowRuntimeRegistry:
    """Own registered dependency graphs and lifecycle state views."""

    def __init__(self) -> None:
        self._graphs: dict[
            str,
            WorkflowDependencyGraph,
        ] = {}

        self._states: dict[
            str,
            dict[str, object],
        ] = {}

    def register(
        self,
        workflow_id: str,
        graph: WorkflowDependencyGraph,
        *,
        initial_states: Mapping[str, object] | None = None,
    ) -> None:
        """Register a workflow graph and its initial states."""

        if not workflow_id or not workflow_id.strip():
            raise WorkflowRuntimeError(
                "workflow_id must not be empty"
            )

        if workflow_id in self._graphs:
            raise WorkflowRuntimeError(
                f"workflow already registered: {workflow_id}"
            )

        states: dict[str, object] = {
            step_id: "pending"
            for step_id in graph.steps()
        }

        supplied_states = dict(initial_states or {})
        unknown = set(supplied_states) - set(graph.steps())

        if unknown:
            raise WorkflowRuntimeError(
                "initial state contains unknown workflow steps: "
                + ", ".join(sorted(unknown))
            )

        states.update(supplied_states)

        self._graphs[workflow_id] = graph
        self._states[workflow_id] = states

    def graph(
        self,
        workflow_id: str,
    ) -> WorkflowDependencyGraph:
        """Return a registered workflow dependency graph."""

        try:
            return self._graphs[workflow_id]
        except KeyError as exc:
            raise WorkflowRuntimeError(
                f"workflow is not registered: {workflow_id}"
            ) from exc

    def states(
        self,
        workflow_id: str,
    ) -> Mapping[str, object]:
        """Return a copy of current lifecycle states."""

        self.graph(workflow_id)
        return dict(self._states[workflow_id])

    def mutable_states(
        self,
        workflow_id: str,
    ) -> dict[str, object]:
        """Return internal mutable state for runtime coordination."""

        self.graph(workflow_id)
        return self._states[workflow_id]

    def all_states(
        self,
    ) -> Mapping[str, Mapping[str, object]]:
        """Return copies of states for all workflows."""

        return {
            workflow_id: dict(states)
            for workflow_id, states in self._states.items()
        }

    def update_step(
        self,
        workflow_id: str,
        step_id: str,
        state: object,
    ) -> None:
        """Update one registered workflow step state."""

        graph = self.graph(workflow_id)

        if step_id not in graph.steps():
            raise WorkflowRuntimeError(
                f"unknown workflow step: {step_id}"
            )

        self._states[workflow_id][step_id] = state

    def contains(
        self,
        workflow_id: str,
    ) -> bool:
        return workflow_id in self._graphs

    def workflow_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._graphs))

    def remove(
        self,
        workflow_id: str,
    ) -> tuple[
        WorkflowDependencyGraph,
        Mapping[str, object],
    ]:
        """Remove and return one registered workflow."""

        graph = self.graph(workflow_id)
        states = dict(self._states[workflow_id])

        del self._graphs[workflow_id]
        del self._states[workflow_id]

        return graph, states

    def __len__(self) -> int:
        return len(self._graphs)
