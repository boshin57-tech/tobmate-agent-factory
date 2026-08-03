"""Workflow runtime observability and immutable event history."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class WorkflowObservabilityError(ValueError):
    """Raised when a runtime observability invariant is violated."""


class WorkflowRuntimeEventKind(str, Enum):
    """Observable workflow runtime event kinds."""

    TRIGGER_PROCESSED = "trigger_processed"
    ACTIVATION_QUEUED = "activation_queued"
    DISPATCH_ACCEPTED = "dispatch_accepted"
    DISPATCH_REJECTED = "dispatch_rejected"
    DISPATCH_FAILED = "dispatch_failed"
    EXECUTION_SUCCEEDED = "execution_succeeded"
    EXECUTION_FAILED = "execution_failed"
    RETRY_SCHEDULED = "retry_scheduled"
    RETRY_RELEASED = "retry_released"
    TIMEOUT_DETECTED = "timeout_detected"
    WORKFLOW_CLEARED = "workflow_cleared"


@dataclass(frozen=True, slots=True)
class WorkflowRuntimeEvent:
    """Immutable runtime event."""

    sequence: int
    workflow_id: str
    kind: WorkflowRuntimeEventKind
    occurred_at: float
    step_id: str | None = None
    detail: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise WorkflowObservabilityError(
                "sequence must be at least one"
            )

        if not self.workflow_id.strip():
            raise WorkflowObservabilityError(
                "workflow_id must not be empty"
            )

        if self.step_id is not None and not self.step_id.strip():
            raise WorkflowObservabilityError(
                "step_id must not be empty when provided"
            )


@dataclass(frozen=True, slots=True)
class WorkflowRuntimeMetrics:
    """Aggregate runtime metrics snapshot."""

    event_count: int
    workflow_count: int
    trigger_count: int
    activation_count: int
    dispatch_accepted_count: int
    dispatch_rejected_count: int
    dispatch_failed_count: int
    execution_succeeded_count: int
    execution_failed_count: int
    retry_scheduled_count: int
    retry_released_count: int
    timeout_count: int


class WorkflowRuntimeObserver:
    """In-memory immutable workflow runtime event collector."""

    def __init__(self) -> None:
        self._events: list[WorkflowRuntimeEvent] = []
        self._next_sequence = 0

    def record(
        self,
        *,
        workflow_id: str,
        kind: WorkflowRuntimeEventKind,
        occurred_at: float,
        step_id: str | None = None,
        detail: Mapping[str, object] | None = None,
    ) -> WorkflowRuntimeEvent:
        """Append one runtime event."""

        self._next_sequence += 1

        event = WorkflowRuntimeEvent(
            sequence=self._next_sequence,
            workflow_id=workflow_id,
            kind=kind,
            occurred_at=occurred_at,
            step_id=step_id,
            detail=dict(detail or {}),
        )

        self._events.append(event)
        return event

    def events(
        self,
        *,
        workflow_id: str | None = None,
        step_id: str | None = None,
        kind: WorkflowRuntimeEventKind | None = None,
    ) -> tuple[WorkflowRuntimeEvent, ...]:
        """Return events matching optional filters."""

        return tuple(
            event
            for event in self._events
            if (
                workflow_id is None
                or event.workflow_id == workflow_id
            )
            and (
                step_id is None
                or event.step_id == step_id
            )
            and (
                kind is None
                or event.kind is kind
            )
        )

    def latest(
        self,
        *,
        workflow_id: str | None = None,
    ) -> WorkflowRuntimeEvent | None:
        """Return the latest global or workflow-specific event."""

        matching = self.events(workflow_id=workflow_id)

        if not matching:
            return None

        return matching[-1]

    def metrics(
        self,
        *,
        workflow_id: str | None = None,
    ) -> WorkflowRuntimeMetrics:
        """Build an aggregate metrics snapshot."""

        events = self.events(workflow_id=workflow_id)
        workflows = {
            event.workflow_id
            for event in events
        }

        def count(kind: WorkflowRuntimeEventKind) -> int:
            return sum(
                event.kind is kind
                for event in events
            )

        return WorkflowRuntimeMetrics(
            event_count=len(events),
            workflow_count=len(workflows),
            trigger_count=count(
                WorkflowRuntimeEventKind.TRIGGER_PROCESSED
            ),
            activation_count=count(
                WorkflowRuntimeEventKind.ACTIVATION_QUEUED
            ),
            dispatch_accepted_count=count(
                WorkflowRuntimeEventKind.DISPATCH_ACCEPTED
            ),
            dispatch_rejected_count=count(
                WorkflowRuntimeEventKind.DISPATCH_REJECTED
            ),
            dispatch_failed_count=count(
                WorkflowRuntimeEventKind.DISPATCH_FAILED
            ),
            execution_succeeded_count=count(
                WorkflowRuntimeEventKind.EXECUTION_SUCCEEDED
            ),
            execution_failed_count=count(
                WorkflowRuntimeEventKind.EXECUTION_FAILED
            ),
            retry_scheduled_count=count(
                WorkflowRuntimeEventKind.RETRY_SCHEDULED
            ),
            retry_released_count=count(
                WorkflowRuntimeEventKind.RETRY_RELEASED
            ),
            timeout_count=count(
                WorkflowRuntimeEventKind.TIMEOUT_DETECTED
            ),
        )

    def clear_workflow(
        self,
        workflow_id: str,
        *,
        occurred_at: float,
    ) -> tuple[WorkflowRuntimeEvent, ...]:
        """Remove workflow history and retain a clear audit event."""

        removed = self.events(workflow_id=workflow_id)

        self._events = [
            event
            for event in self._events
            if event.workflow_id != workflow_id
        ]

        self.record(
            workflow_id=workflow_id,
            kind=WorkflowRuntimeEventKind.WORKFLOW_CLEARED,
            occurred_at=occurred_at,
            detail={
                "removed_event_count": len(removed),
            },
        )

        return removed

    def __len__(self) -> int:
        return len(self._events)
