"""Workflow dependency directed acyclic graph.

The graph is independent from workflow lifecycle persistence. Lifecycle states
may be supplied as strings or Enum values.

Core invariants:

* dependency edges form a directed acyclic graph;
* duplicate edges are rejected;
* dependency evaluation is deterministic;
* targets may use ALL or ANY dependency join semantics;
* success, failure, cancellation and completion remain distinct conditions;
* graph queries never mutate workflow lifecycle state.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class WorkflowDependencyError(ValueError):
    """Raised when a workflow dependency invariant is violated."""


class DependencyCondition(str, Enum):
    """Required lifecycle condition of an upstream step."""

    ON_SUCCESS = "on_success"
    ON_FAILURE = "on_failure"
    ON_COMPLETION = "on_completion"
    ON_CANCELLATION = "on_cancellation"


class DependencyJoinPolicy(str, Enum):
    """How multiple incoming dependencies are combined."""

    ALL = "all"
    ANY = "any"


@dataclass(frozen=True, slots=True)
class WorkflowDependency:
    """Directed dependency between two workflow steps."""

    source_step_id: str
    target_step_id: str
    condition: DependencyCondition = DependencyCondition.ON_SUCCESS

    def __post_init__(self) -> None:
        if not self.source_step_id or not self.source_step_id.strip():
            raise WorkflowDependencyError("source_step_id must not be empty")

        if not self.target_step_id or not self.target_step_id.strip():
            raise WorkflowDependencyError("target_step_id must not be empty")

        if self.source_step_id == self.target_step_id:
            raise WorkflowDependencyError(
                "a workflow step cannot depend on itself"
            )


_SUCCESS_STATES = frozenset(
    {
        "success",
        "succeeded",
        "completed",
        "complete",
    }
)

_FAILURE_STATES = frozenset(
    {
        "failure",
        "failed",
        "error",
        "errored",
    }
)

_CANCELLATION_STATES = frozenset(
    {
        "cancelled",
        "canceled",
        "aborted",
    }
)

_TERMINAL_STATES = frozenset(
    set(_SUCCESS_STATES)
    | set(_FAILURE_STATES)
    | set(_CANCELLATION_STATES)
    | {
        "skipped",
        "timed_out",
        "timeout",
        "rolled_back",
    }
)

_NON_READY_TARGET_STATES = frozenset(
    set(_TERMINAL_STATES)
    | {
        "running",
        "executing",
        "in_progress",
        "active",
        "paused",
        "suspended",
    }
)


def normalize_workflow_state(value: object | None) -> str:
    """Normalize string and Enum lifecycle states."""

    if value is None:
        return ""

    enum_value = getattr(value, "value", value)
    return str(enum_value).strip().lower()


def dependency_condition_matches(
    condition: DependencyCondition,
    state: object | None,
) -> bool:
    """Return whether an upstream state satisfies a dependency condition."""

    normalized = normalize_workflow_state(state)

    if condition is DependencyCondition.ON_SUCCESS:
        return normalized in _SUCCESS_STATES

    if condition is DependencyCondition.ON_FAILURE:
        return normalized in _FAILURE_STATES

    if condition is DependencyCondition.ON_CANCELLATION:
        return normalized in _CANCELLATION_STATES

    if condition is DependencyCondition.ON_COMPLETION:
        return normalized in _TERMINAL_STATES

    return False


class WorkflowDependencyGraph:
    """Deterministic workflow dependency DAG."""

    def __init__(self) -> None:
        self._nodes: set[str] = set()
        self._incoming: dict[str, list[WorkflowDependency]] = defaultdict(list)
        self._outgoing: dict[str, list[WorkflowDependency]] = defaultdict(list)
        self._join_policies: dict[str, DependencyJoinPolicy] = {}

    def add_step(
        self,
        step_id: str,
        *,
        join_policy: DependencyJoinPolicy = DependencyJoinPolicy.ALL,
    ) -> None:
        """Register a workflow step."""

        normalized = step_id.strip()

        if not normalized:
            raise WorkflowDependencyError("step_id must not be empty")

        self._nodes.add(normalized)
        self._join_policies.setdefault(normalized, join_policy)

    def set_join_policy(
        self,
        step_id: str,
        join_policy: DependencyJoinPolicy,
    ) -> None:
        """Set ALL or ANY dependency semantics for a target step."""

        self.add_step(step_id)
        self._join_policies[step_id] = join_policy

    def join_policy_for(self, step_id: str) -> DependencyJoinPolicy:
        """Return the configured join policy."""

        self._assert_known_step(step_id)

        return self._join_policies.get(
            step_id,
            DependencyJoinPolicy.ALL,
        )

    def add_dependency(
        self,
        dependency: WorkflowDependency,
    ) -> None:
        """Add an edge while protecting DAG invariants."""

        source = dependency.source_step_id
        target = dependency.target_step_id

        self.add_step(source)
        self.add_step(target)

        if dependency in self._outgoing[source]:
            raise WorkflowDependencyError(
                "duplicate workflow dependency: "
                f"{source} -> {target} ({dependency.condition.value})"
            )

        if self._has_path(target, source):
            raise WorkflowDependencyError(
                "workflow dependency would create a cycle: "
                f"{source} -> {target}"
            )

        self._outgoing[source].append(dependency)
        self._incoming[target].append(dependency)

        self._outgoing[source].sort(
            key=lambda item: (
                item.target_step_id,
                item.condition.value,
            )
        )
        self._incoming[target].sort(
            key=lambda item: (
                item.source_step_id,
                item.condition.value,
            )
        )

    def connect(
        self,
        source_step_id: str,
        target_step_id: str,
        *,
        condition: DependencyCondition = DependencyCondition.ON_SUCCESS,
    ) -> WorkflowDependency:
        """Create and register a dependency edge."""

        dependency = WorkflowDependency(
            source_step_id=source_step_id,
            target_step_id=target_step_id,
            condition=condition,
        )

        self.add_dependency(dependency)
        return dependency

    def steps(self) -> tuple[str, ...]:
        """Return registered step identifiers."""

        return tuple(sorted(self._nodes))

    def dependencies_for(
        self,
        step_id: str,
    ) -> tuple[WorkflowDependency, ...]:
        """Return incoming dependency edges."""

        self._assert_known_step(step_id)
        return tuple(self._incoming.get(step_id, ()))

    def dependents_of(
        self,
        step_id: str,
    ) -> tuple[WorkflowDependency, ...]:
        """Return outgoing dependency edges."""

        self._assert_known_step(step_id)
        return tuple(self._outgoing.get(step_id, ()))

    def blocked_by(
        self,
        step_id: str,
        states: Mapping[str, object],
    ) -> tuple[str, ...]:
        """Return upstream steps currently blocking a target."""

        dependencies = self.dependencies_for(step_id)

        if not dependencies:
            return ()

        matches = [
            dependency_condition_matches(
                dependency.condition,
                states.get(dependency.source_step_id),
            )
            for dependency in dependencies
        ]

        policy = self.join_policy_for(step_id)

        if policy is DependencyJoinPolicy.ANY and any(matches):
            return ()

        return tuple(
            dependency.source_step_id
            for dependency, matched in zip(
                dependencies,
                matches,
                strict=True,
            )
            if not matched
        )

    def is_ready(
        self,
        step_id: str,
        states: Mapping[str, object],
    ) -> bool:
        """Return whether a step may become executable."""

        self._assert_known_step(step_id)

        current_state = normalize_workflow_state(states.get(step_id))

        if current_state in _NON_READY_TARGET_STATES:
            return False

        dependencies = self.dependencies_for(step_id)

        if not dependencies:
            return True

        results = tuple(
            dependency_condition_matches(
                dependency.condition,
                states.get(dependency.source_step_id),
            )
            for dependency in dependencies
        )

        if self.join_policy_for(step_id) is DependencyJoinPolicy.ANY:
            return any(results)

        return all(results)

    def ready_steps(
        self,
        states: Mapping[str, object],
    ) -> tuple[str, ...]:
        """Return all currently executable steps."""

        return tuple(
            step_id
            for step_id in sorted(self._nodes)
            if self.is_ready(step_id, states)
        )

    def topological_order(self) -> tuple[str, ...]:
        """Return a stable topological workflow ordering."""

        in_degree = {
            step_id: len(
                {
                    dependency.source_step_id
                    for dependency in self._incoming.get(step_id, ())
                }
            )
            for step_id in self._nodes
        }

        ready = sorted(
            step_id
            for step_id, degree in in_degree.items()
            if degree == 0
        )

        ordered: list[str] = []

        while ready:
            current = ready.pop(0)
            ordered.append(current)

            targets = sorted(
                {
                    dependency.target_step_id
                    for dependency in self._outgoing.get(current, ())
                }
            )

            for target in targets:
                in_degree[target] -= 1

                if in_degree[target] == 0:
                    ready.append(target)
                    ready.sort()

        if len(ordered) != len(self._nodes):
            raise WorkflowDependencyError(
                "workflow dependency graph contains a cycle"
            )

        return tuple(ordered)

    def _has_path(
        self,
        source_step_id: str,
        target_step_id: str,
    ) -> bool:
        """Return whether target is reachable from source."""

        pending = [source_step_id]
        visited: set[str] = set()

        while pending:
            current = pending.pop()

            if current == target_step_id:
                return True

            if current in visited:
                continue

            visited.add(current)

            pending.extend(
                dependency.target_step_id
                for dependency in self._outgoing.get(current, ())
            )

        return False

    def _assert_known_step(self, step_id: str) -> None:
        if step_id not in self._nodes:
            raise WorkflowDependencyError(
                f"unknown workflow step: {step_id}"
            )
