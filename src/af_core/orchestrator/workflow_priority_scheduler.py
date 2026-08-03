"""Deterministic workflow priority scheduler."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from af_core.orchestrator.workflow_dependency_graph import (
    normalize_workflow_state,
)
from af_core.orchestrator.workflow_trigger_engine import (
    WorkflowTriggerActivation,
)


class WorkflowSchedulerError(ValueError):
    """Raised when a scheduling invariant is violated."""


@dataclass(frozen=True, slots=True)
class WorkflowScheduleCandidate:
    workflow_id: str
    step_id: str
    priority: int = 100
    sequence: int = 0
    trigger_id: str = ""
    event_identity: str = ""
    required_capabilities: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.workflow_id.strip():
            raise WorkflowSchedulerError(
                "workflow_id must not be empty"
            )

        if not self.step_id.strip():
            raise WorkflowSchedulerError(
                "step_id must not be empty"
            )

        if self.priority < 0:
            raise WorkflowSchedulerError(
                "priority must be zero or greater"
            )

        if self.sequence < 0:
            raise WorkflowSchedulerError(
                "sequence must be zero or greater"
            )

        capabilities = tuple(
            value.strip()
            for value in self.required_capabilities
        )

        if any(not value for value in capabilities):
            raise WorkflowSchedulerError(
                "required capabilities must not be empty"
            )

        if len(set(capabilities)) != len(capabilities):
            raise WorkflowSchedulerError(
                "required capabilities must be unique"
            )

    @property
    def key(self) -> tuple[str, str]:
        return self.workflow_id, self.step_id


@dataclass(frozen=True, slots=True)
class WorkflowScheduleBatch:
    selected: tuple[WorkflowScheduleCandidate, ...]
    deferred: tuple[WorkflowScheduleCandidate, ...]

    @property
    def selected_count(self) -> int:
        return len(self.selected)

    @property
    def deferred_count(self) -> int:
        return len(self.deferred)


_BLOCKED_STATES = frozenset(
    {
        "running",
        "executing",
        "in_progress",
        "active",
        "dispatching",
        "dispatched",
        "success",
        "succeeded",
        "completed",
        "complete",
        "failure",
        "failed",
        "error",
        "errored",
        "cancelled",
        "canceled",
        "aborted",
        "skipped",
        "timed_out",
        "timeout",
        "rolled_back",
    }
)


class WorkflowPriorityScheduler:
    """Priority queue for trigger-generated workflow steps."""

    def __init__(self) -> None:
        self._pending: dict[
            tuple[str, str],
            WorkflowScheduleCandidate,
        ] = {}
        self._next_sequence = 0

    def enqueue(
        self,
        candidate: WorkflowScheduleCandidate,
    ) -> WorkflowScheduleCandidate:
        if candidate.key in self._pending:
            raise WorkflowSchedulerError(
                "duplicate workflow schedule candidate: "
                f"{candidate.workflow_id}/{candidate.step_id}"
            )

        stored = candidate

        if candidate.sequence == 0:
            self._next_sequence += 1

            stored = WorkflowScheduleCandidate(
                workflow_id=candidate.workflow_id,
                step_id=candidate.step_id,
                priority=candidate.priority,
                sequence=self._next_sequence,
                trigger_id=candidate.trigger_id,
                event_identity=candidate.event_identity,
                required_capabilities=(
                    candidate.required_capabilities
                ),
                metadata=dict(candidate.metadata),
            )
        else:
            self._next_sequence = max(
                self._next_sequence,
                candidate.sequence,
            )

        self._pending[stored.key] = stored
        return stored

    def enqueue_activation(
        self,
        activation: WorkflowTriggerActivation,
        *,
        required_capabilities: Iterable[str] = (),
        metadata: Mapping[str, object] | None = None,
    ) -> WorkflowScheduleCandidate:
        return self.enqueue(
            WorkflowScheduleCandidate(
                workflow_id=activation.workflow_id,
                step_id=activation.target_step_id,
                priority=activation.priority,
                trigger_id=activation.trigger_id,
                event_identity=activation.event_identity,
                required_capabilities=tuple(
                    required_capabilities
                ),
                metadata=dict(metadata or {}),
            )
        )

    def get(
        self,
        workflow_id: str,
        step_id: str,
    ) -> WorkflowScheduleCandidate:
        try:
            return self._pending[(workflow_id, step_id)]
        except KeyError as exc:
            raise WorkflowSchedulerError(
                "unknown workflow schedule candidate: "
                f"{workflow_id}/{step_id}"
            ) from exc

    def pending(
        self,
    ) -> tuple[WorkflowScheduleCandidate, ...]:
        return tuple(
            sorted(
                self._pending.values(),
                key=lambda item: (
                    item.priority,
                    item.sequence,
                    item.workflow_id,
                    item.step_id,
                ),
            )
        )

    def select(
        self,
        *,
        limit: int,
        states_by_workflow: Mapping[
            str,
            Mapping[str, object],
        ]
        | None = None,
        available_capabilities: Iterable[str] = (),
    ) -> WorkflowScheduleBatch:
        if limit < 0:
            raise WorkflowSchedulerError(
                "limit must be zero or greater"
            )

        states = states_by_workflow or {}
        capabilities = frozenset(available_capabilities)

        selected: list[WorkflowScheduleCandidate] = []
        deferred: list[WorkflowScheduleCandidate] = []

        for candidate in self.pending():
            workflow_states = states.get(
                candidate.workflow_id,
                {},
            )

            state = normalize_workflow_state(
                workflow_states.get(candidate.step_id)
            )

            lifecycle_blocked = state in _BLOCKED_STATES

            capability_blocked = not frozenset(
                candidate.required_capabilities
            ).issubset(capabilities)

            if (
                not lifecycle_blocked
                and not capability_blocked
                and len(selected) < limit
            ):
                selected.append(candidate)
            else:
                deferred.append(candidate)

        return WorkflowScheduleBatch(
            selected=tuple(selected),
            deferred=tuple(deferred),
        )

    def acknowledge(
        self,
        candidate: WorkflowScheduleCandidate,
    ) -> WorkflowScheduleCandidate:
        stored = self.get(
            candidate.workflow_id,
            candidate.step_id,
        )

        if stored != candidate:
            raise WorkflowSchedulerError(
                "schedule candidate does not match pending record"
            )

        del self._pending[candidate.key]
        return stored

    def remove(
        self,
        workflow_id: str,
        step_id: str,
    ) -> WorkflowScheduleCandidate:
        candidate = self.get(workflow_id, step_id)
        del self._pending[candidate.key]
        return candidate

    def clear_workflow(
        self,
        workflow_id: str,
    ) -> tuple[WorkflowScheduleCandidate, ...]:
        removed = tuple(
            item
            for item in self.pending()
            if item.workflow_id == workflow_id
        )

        for item in removed:
            del self._pending[item.key]

        return removed

    def __len__(self) -> int:
        return len(self._pending)
