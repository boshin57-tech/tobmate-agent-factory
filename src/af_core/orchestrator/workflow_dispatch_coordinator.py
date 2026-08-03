"""Trigger-to-scheduler-to-lifecycle dispatch coordination."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterable, Mapping, Protocol

from af_core.orchestrator.workflow_priority_scheduler import (
    WorkflowPriorityScheduler,
    WorkflowScheduleCandidate,
)
from af_core.orchestrator.workflow_trigger_engine import (
    WorkflowTriggerActivation,
)


class WorkflowDispatchError(ValueError):
    """Raised when lifecycle dispatch integration is invalid."""


class WorkflowDispatchStatus(str, Enum):
    """Lifecycle dispatch result."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class WorkflowDispatchRequest:
    """Lifecycle dispatch request generated from a schedule candidate."""

    workflow_id: str
    step_id: str
    priority: int
    trigger_id: str = ""
    event_identity: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def from_candidate(
        cls,
        candidate: WorkflowScheduleCandidate,
    ) -> "WorkflowDispatchRequest":
        return cls(
            workflow_id=candidate.workflow_id,
            step_id=candidate.step_id,
            priority=candidate.priority,
            trigger_id=candidate.trigger_id,
            event_identity=candidate.event_identity,
            metadata=dict(candidate.metadata),
        )


@dataclass(frozen=True, slots=True)
class WorkflowDispatchOutcome:
    """Immutable lifecycle dispatch outcome."""

    request: WorkflowDispatchRequest
    status: WorkflowDispatchStatus
    reason: str = ""

    @property
    def accepted(self) -> bool:
        return self.status is WorkflowDispatchStatus.ACCEPTED


@dataclass(frozen=True, slots=True)
class WorkflowDispatchCycle:
    """Result of one scheduler-to-lifecycle dispatch cycle."""

    outcomes: tuple[WorkflowDispatchOutcome, ...]
    deferred: tuple[WorkflowScheduleCandidate, ...]

    @property
    def accepted_count(self) -> int:
        return sum(outcome.accepted for outcome in self.outcomes)

    @property
    def rejected_count(self) -> int:
        return sum(
            outcome.status is WorkflowDispatchStatus.REJECTED
            for outcome in self.outcomes
        )

    @property
    def failed_count(self) -> int:
        return sum(
            outcome.status is WorkflowDispatchStatus.FAILED
            for outcome in self.outcomes
        )


class WorkflowLifecycleDispatcher(Protocol):
    """Adapter implemented by a workflow lifecycle engine."""

    def dispatch(
        self,
        request: WorkflowDispatchRequest,
    ) -> WorkflowDispatchOutcome | bool:
        ...


CapabilityResolver = Callable[
    [WorkflowTriggerActivation],
    Iterable[str],
]

MetadataResolver = Callable[
    [WorkflowTriggerActivation],
    Mapping[str, object],
]


class WorkflowDispatchCoordinator:
    """Connect triggers, priority scheduling and lifecycle dispatch."""

    def __init__(
        self,
        scheduler: WorkflowPriorityScheduler | None = None,
    ) -> None:
        self._scheduler = (
            scheduler
            if scheduler is not None
            else WorkflowPriorityScheduler()
        )

    @property
    def scheduler(self) -> WorkflowPriorityScheduler:
        return self._scheduler

    def enqueue_activations(
        self,
        activations: Iterable[WorkflowTriggerActivation],
        *,
        capability_resolver: CapabilityResolver | None = None,
        metadata_resolver: MetadataResolver | None = None,
    ) -> tuple[WorkflowScheduleCandidate, ...]:
        """Convert new trigger activations into pending candidates."""

        existing = {
            candidate.key
            for candidate in self._scheduler.pending()
        }

        queued: list[WorkflowScheduleCandidate] = []

        for activation in activations:
            key = (
                activation.workflow_id,
                activation.target_step_id,
            )

            if key in existing:
                continue

            capabilities = (
                tuple(capability_resolver(activation))
                if capability_resolver is not None
                else ()
            )

            metadata = {
                "trigger_kind": activation.kind.value,
            }

            if activation.source_step_id is not None:
                metadata["source_step_id"] = (
                    activation.source_step_id
                )

            if activation.event_name is not None:
                metadata["event_name"] = activation.event_name

            if metadata_resolver is not None:
                metadata.update(
                    dict(metadata_resolver(activation))
                )

            candidate = self._scheduler.enqueue_activation(
                activation,
                required_capabilities=capabilities,
                metadata=metadata,
            )

            queued.append(candidate)
            existing.add(key)

        return tuple(queued)

    def dispatch_ready(
        self,
        dispatcher: WorkflowLifecycleDispatcher,
        *,
        limit: int,
        states_by_workflow: Mapping[
            str,
            Mapping[str, object],
        ]
        | None = None,
        available_capabilities: Iterable[str] = (),
    ) -> WorkflowDispatchCycle:
        """Dispatch eligible candidates and acknowledge accepted work."""

        batch = self._scheduler.select(
            limit=limit,
            states_by_workflow=states_by_workflow,
            available_capabilities=available_capabilities,
        )

        outcomes: list[WorkflowDispatchOutcome] = []

        for candidate in batch.selected:
            request = WorkflowDispatchRequest.from_candidate(
                candidate
            )

            try:
                raw_outcome = dispatcher.dispatch(request)
                outcome = self._normalize_outcome(
                    request,
                    raw_outcome,
                )
            except Exception as exc:
                outcome = WorkflowDispatchOutcome(
                    request=request,
                    status=WorkflowDispatchStatus.FAILED,
                    reason=(
                        f"{type(exc).__name__}: {exc}"
                    ),
                )

            if outcome.accepted:
                self._scheduler.acknowledge(candidate)

            outcomes.append(outcome)

        return WorkflowDispatchCycle(
            outcomes=tuple(outcomes),
            deferred=batch.deferred,
        )

    @staticmethod
    def _normalize_outcome(
        request: WorkflowDispatchRequest,
        raw_outcome: WorkflowDispatchOutcome | bool,
    ) -> WorkflowDispatchOutcome:
        if isinstance(raw_outcome, bool):
            return WorkflowDispatchOutcome(
                request=request,
                status=(
                    WorkflowDispatchStatus.ACCEPTED
                    if raw_outcome
                    else WorkflowDispatchStatus.REJECTED
                ),
            )

        if not isinstance(
            raw_outcome,
            WorkflowDispatchOutcome,
        ):
            raise WorkflowDispatchError(
                "dispatcher must return bool or "
                "WorkflowDispatchOutcome"
            )

        if (
            raw_outcome.request.workflow_id
            != request.workflow_id
            or raw_outcome.request.step_id
            != request.step_id
        ):
            raise WorkflowDispatchError(
                "dispatcher outcome request does not match "
                "the dispatched workflow step"
            )

        return raw_outcome
