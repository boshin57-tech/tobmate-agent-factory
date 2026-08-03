"""Deterministic workflow trigger engine.

The engine evaluates workflow events and produces immutable target-step
activations. It does not directly mutate workflow lifecycle state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

from af_core.orchestrator.workflow_dependency_graph import (
    WorkflowDependencyGraph,
    normalize_workflow_state,
)


class WorkflowTriggerError(ValueError):
    """Raised when a workflow trigger invariant is violated."""


class WorkflowTriggerKind(str, Enum):
    """Supported workflow trigger kinds."""

    WORKFLOW_STARTED = "workflow_started"
    STEP_STATE_CHANGED = "step_state_changed"
    EVENT_RECEIVED = "event_received"
    MANUAL = "manual"
    DEPENDENCY_READY = "dependency_ready"


@dataclass(frozen=True, slots=True)
class WorkflowTriggerEvent:
    """Runtime event evaluated against trigger rules."""

    workflow_id: str
    kind: WorkflowTriggerKind
    event_id: str = ""
    source_step_id: str | None = None
    state: object | None = None
    event_name: str | None = None
    payload: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.workflow_id.strip():
            raise WorkflowTriggerError(
                "workflow_id must not be empty"
            )

        if (
            self.kind is WorkflowTriggerKind.STEP_STATE_CHANGED
            and not self.source_step_id
        ):
            raise WorkflowTriggerError(
                "STEP_STATE_CHANGED requires source_step_id"
            )

        if (
            self.kind is WorkflowTriggerKind.EVENT_RECEIVED
            and not self.event_name
        ):
            raise WorkflowTriggerError(
                "EVENT_RECEIVED requires event_name"
            )

    @property
    def identity(self) -> str:
        """Return a stable event identity for idempotency."""

        if self.event_id:
            return self.event_id

        payload = json.dumps(
            dict(self.payload),
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )

        return "|".join(
            (
                self.kind.value,
                self.source_step_id or "",
                normalize_workflow_state(self.state),
                self.event_name or "",
                payload,
            )
        )


@dataclass(frozen=True, slots=True)
class WorkflowTriggerRule:
    """Rule mapping an event condition to a target step."""

    trigger_id: str
    target_step_id: str
    kind: WorkflowTriggerKind
    source_step_id: str | None = None
    expected_state: object | None = None
    event_name: str | None = None
    once_per_workflow: bool = True
    priority: int = 100

    def __post_init__(self) -> None:
        if not self.trigger_id.strip():
            raise WorkflowTriggerError(
                "trigger_id must not be empty"
            )

        if not self.target_step_id.strip():
            raise WorkflowTriggerError(
                "target_step_id must not be empty"
            )

        if self.kind is WorkflowTriggerKind.DEPENDENCY_READY:
            raise WorkflowTriggerError(
                "DEPENDENCY_READY is generated from the graph"
            )

        if (
            self.kind is WorkflowTriggerKind.STEP_STATE_CHANGED
            and not self.source_step_id
        ):
            raise WorkflowTriggerError(
                "STEP_STATE_CHANGED rule requires source_step_id"
            )

        if (
            self.kind is WorkflowTriggerKind.EVENT_RECEIVED
            and not self.event_name
        ):
            raise WorkflowTriggerError(
                "EVENT_RECEIVED rule requires event_name"
            )

    def matches(self, event: WorkflowTriggerEvent) -> bool:
        """Return whether the rule matches an event."""

        if self.kind is not event.kind:
            return False

        if (
            self.source_step_id is not None
            and self.source_step_id != event.source_step_id
        ):
            return False

        if self.expected_state is not None:
            expected = normalize_workflow_state(
                self.expected_state
            )
            actual = normalize_workflow_state(event.state)

            if expected != actual:
                return False

        if (
            self.event_name is not None
            and self.event_name != event.event_name
        ):
            return False

        return True


@dataclass(frozen=True, slots=True)
class WorkflowTriggerActivation:
    """Immutable trigger activation result."""

    workflow_id: str
    trigger_id: str
    target_step_id: str
    kind: WorkflowTriggerKind
    event_identity: str
    priority: int
    source_step_id: str | None = None
    event_name: str | None = None


class WorkflowTriggerEngine:
    """Deterministic and idempotent trigger evaluator."""

    def __init__(self) -> None:
        self._rules: dict[str, WorkflowTriggerRule] = {}
        self._seen_events: set[tuple[str, str]] = set()
        self._fired_rules: set[tuple[str, str]] = set()
        self._dependency_fired: set[tuple[str, str]] = set()

    def register(self, rule: WorkflowTriggerRule) -> None:
        """Register a unique trigger rule."""

        if rule.trigger_id in self._rules:
            raise WorkflowTriggerError(
                f"duplicate workflow trigger: {rule.trigger_id}"
            )

        self._rules[rule.trigger_id] = rule

    def unregister(
        self,
        trigger_id: str,
    ) -> WorkflowTriggerRule:
        """Remove and return a trigger rule."""

        try:
            return self._rules.pop(trigger_id)
        except KeyError as exc:
            raise WorkflowTriggerError(
                f"unknown workflow trigger: {trigger_id}"
            ) from exc

    def get(self, trigger_id: str) -> WorkflowTriggerRule:
        """Return a registered trigger rule."""

        try:
            return self._rules[trigger_id]
        except KeyError as exc:
            raise WorkflowTriggerError(
                f"unknown workflow trigger: {trigger_id}"
            ) from exc

    def rules(self) -> tuple[WorkflowTriggerRule, ...]:
        """Return rules in deterministic priority order."""

        return tuple(
            sorted(
                self._rules.values(),
                key=lambda rule: (
                    rule.priority,
                    rule.trigger_id,
                ),
            )
        )

    def process(
        self,
        event: WorkflowTriggerEvent,
        *,
        dependency_graph: WorkflowDependencyGraph | None = None,
        states: Mapping[str, object] | None = None,
    ) -> tuple[WorkflowTriggerActivation, ...]:
        """Evaluate an event and return permitted activations."""

        event_key = (
            event.workflow_id,
            event.identity,
        )

        if event_key in self._seen_events:
            return ()

        current_states = states or {}
        activations: list[WorkflowTriggerActivation] = []

        for rule in self.rules():
            if not rule.matches(event):
                continue

            fired_key = (
                event.workflow_id,
                rule.trigger_id,
            )

            if (
                rule.once_per_workflow
                and fired_key in self._fired_rules
            ):
                continue

            if dependency_graph is not None:
                if rule.target_step_id not in dependency_graph.steps():
                    raise WorkflowTriggerError(
                        "trigger target is not registered in graph: "
                        f"{rule.target_step_id}"
                    )

                if not dependency_graph.is_ready(
                    rule.target_step_id,
                    current_states,
                ):
                    continue

            activations.append(
                WorkflowTriggerActivation(
                    workflow_id=event.workflow_id,
                    trigger_id=rule.trigger_id,
                    target_step_id=rule.target_step_id,
                    kind=event.kind,
                    event_identity=event.identity,
                    priority=rule.priority,
                    source_step_id=event.source_step_id,
                    event_name=event.event_name,
                )
            )

            if rule.once_per_workflow:
                self._fired_rules.add(fired_key)

        self._seen_events.add(event_key)

        return tuple(activations)

    def evaluate_dependencies(
        self,
        workflow_id: str,
        dependency_graph: WorkflowDependencyGraph,
        states: Mapping[str, object],
    ) -> tuple[WorkflowTriggerActivation, ...]:
        """Activate newly dependency-ready steps once."""

        if not workflow_id.strip():
            raise WorkflowTriggerError(
                "workflow_id must not be empty"
            )

        activations: list[WorkflowTriggerActivation] = []

        for target_step_id in dependency_graph.ready_steps(states):
            fired_key = (
                workflow_id,
                target_step_id,
            )

            if fired_key in self._dependency_fired:
                continue

            trigger_id = f"dependency-ready:{target_step_id}"

            activations.append(
                WorkflowTriggerActivation(
                    workflow_id=workflow_id,
                    trigger_id=trigger_id,
                    target_step_id=target_step_id,
                    kind=WorkflowTriggerKind.DEPENDENCY_READY,
                    event_identity=trigger_id,
                    priority=100,
                )
            )

            self._dependency_fired.add(fired_key)

        return tuple(activations)

    def clear_workflow(self, workflow_id: str) -> None:
        """Clear trigger history for a workflow instance."""

        self._seen_events = {
            key
            for key in self._seen_events
            if key[0] != workflow_id
        }

        self._fired_rules = {
            key
            for key in self._fired_rules
            if key[0] != workflow_id
        }

        self._dependency_fired = {
            key
            for key in self._dependency_fired
            if key[0] != workflow_id
        }

    def has_seen_event(
        self,
        workflow_id: str,
        event_identity: str,
    ) -> bool:
        """Return whether an event has already been processed."""

        return (
            workflow_id,
            event_identity,
        ) in self._seen_events
