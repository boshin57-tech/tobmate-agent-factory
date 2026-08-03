"""Unified workflow runtime integration engine."""

from __future__ import annotations

from typing import Iterable

from af_core.orchestrator.workflow_dependency_graph import (
    WorkflowDependencyGraph,
)
from af_core.orchestrator.workflow_dispatch_coordinator import (
    WorkflowDispatchCoordinator,
    WorkflowDispatchCycle,
    WorkflowDispatchStatus,
    WorkflowLifecycleDispatcher,
)
from af_core.orchestrator.workflow_recovery_coordinator import (
    WorkflowRecoveryCoordinator,
)
from af_core.orchestrator.workflow_recovery_engine import (
    WorkflowFailureRecoveryEngine,
    WorkflowRecoveryAction,
    WorkflowRecoveryDecision,
)
from af_core.orchestrator.workflow_runtime_models import (
    CapabilityResolver,
    MetadataResolver,
    WorkflowRuntimeProcessResult,
    WorkflowRuntimeRegistry,
    WorkflowRuntimeSnapshot,
)
from af_core.orchestrator.workflow_runtime_observability import (
    WorkflowRuntimeEventKind,
    WorkflowRuntimeObserver,
)
from af_core.orchestrator.workflow_trigger_engine import (
    WorkflowTriggerEngine,
    WorkflowTriggerEvent,
)


class WorkflowRuntimeEngine:
    """Run workflow dependencies, triggers, dispatch and recovery."""

    def __init__(
        self,
        *,
        registry: WorkflowRuntimeRegistry | None = None,
        trigger_engine: WorkflowTriggerEngine | None = None,
        observer: WorkflowRuntimeObserver | None = None,
        recovery_engine: WorkflowFailureRecoveryEngine | None = None,
    ) -> None:
        self._registry = registry or WorkflowRuntimeRegistry()
        self._trigger = trigger_engine or WorkflowTriggerEngine()
        self._observer = observer or WorkflowRuntimeObserver()

        dispatch = WorkflowDispatchCoordinator()
        recovery = recovery_engine or WorkflowFailureRecoveryEngine()

        self._recovery = WorkflowRecoveryCoordinator(
            dispatch,
            recovery,
        )

    @property
    def registry(self) -> WorkflowRuntimeRegistry:
        return self._registry

    @property
    def trigger_engine(self) -> WorkflowTriggerEngine:
        return self._trigger

    @property
    def observer(self) -> WorkflowRuntimeObserver:
        return self._observer

    @property
    def recovery_coordinator(
        self,
    ) -> WorkflowRecoveryCoordinator:
        return self._recovery

    @property
    def dispatch_coordinator(
        self,
    ) -> WorkflowDispatchCoordinator:
        return self._recovery.dispatch_coordinator

    def register_workflow(
        self,
        workflow_id: str,
        graph: WorkflowDependencyGraph,
        *,
        initial_states: dict[str, object] | None = None,
    ) -> None:
        """Register a dependency graph and lifecycle states."""

        self._registry.register(
            workflow_id,
            graph,
            initial_states=initial_states,
        )

    def update_step_state(
        self,
        workflow_id: str,
        step_id: str,
        state: object,
    ) -> None:
        """Update one runtime lifecycle state."""

        self._registry.update_step(
            workflow_id,
            step_id,
            state,
        )

    def process_event(
        self,
        event: WorkflowTriggerEvent,
        *,
        now: float,
        capability_resolver: CapabilityResolver | None = None,
        metadata_resolver: MetadataResolver | None = None,
    ) -> WorkflowRuntimeProcessResult:
        """Process an event and queue permitted activations."""

        graph = self._registry.graph(event.workflow_id)
        states = self._registry.states(event.workflow_id)

        self._observer.record(
            workflow_id=event.workflow_id,
            step_id=event.source_step_id,
            kind=WorkflowRuntimeEventKind.TRIGGER_PROCESSED,
            occurred_at=now,
            detail={
                "trigger_kind": event.kind.value,
                "event_identity": event.identity,
            },
        )

        event_activations = self._trigger.process(
            event,
            dependency_graph=graph,
            states=states,
        )

        dependency_activations = (
            self._trigger.evaluate_dependencies(
                event.workflow_id,
                graph,
                states,
            )
        )

        queued = self.dispatch_coordinator.enqueue_activations(
            event_activations + dependency_activations,
            capability_resolver=capability_resolver,
            metadata_resolver=metadata_resolver,
        )

        self._record_queued(
            queued,
            now=now,
        )

        return WorkflowRuntimeProcessResult(
            event_activations=event_activations,
            dependency_activations=dependency_activations,
            queued=queued,
        )

    def evaluate_dependencies(
        self,
        workflow_id: str,
        *,
        now: float,
        capability_resolver: CapabilityResolver | None = None,
        metadata_resolver: MetadataResolver | None = None,
    ) -> tuple:
        """Queue steps enabled by current dependency states."""

        graph = self._registry.graph(workflow_id)
        states = self._registry.states(workflow_id)

        activations = self._trigger.evaluate_dependencies(
            workflow_id,
            graph,
            states,
        )

        queued = self.dispatch_coordinator.enqueue_activations(
            activations,
            capability_resolver=capability_resolver,
            metadata_resolver=metadata_resolver,
        )

        self._record_queued(
            queued,
            now=now,
        )

        return queued

    def dispatch_ready(
        self,
        dispatcher: WorkflowLifecycleDispatcher,
        *,
        now: float,
        limit: int,
        available_capabilities: Iterable[str] = (),
    ) -> WorkflowDispatchCycle:
        """Dispatch scheduled candidates with recovery protection."""

        cycle = self._recovery.dispatch_ready(
            dispatcher,
            now=now,
            limit=limit,
            states_by_workflow=self._registry.all_states(),
            available_capabilities=available_capabilities,
        )

        for outcome in cycle.outcomes:
            workflow_id = outcome.request.workflow_id
            step_id = outcome.request.step_id

            if outcome.status is WorkflowDispatchStatus.ACCEPTED:
                kind = WorkflowRuntimeEventKind.DISPATCH_ACCEPTED

                self._registry.update_step(
                    workflow_id,
                    step_id,
                    "running",
                )

            elif outcome.status is WorkflowDispatchStatus.REJECTED:
                kind = WorkflowRuntimeEventKind.DISPATCH_REJECTED

            else:
                kind = WorkflowRuntimeEventKind.DISPATCH_FAILED

            self._observer.record(
                workflow_id=workflow_id,
                step_id=step_id,
                kind=kind,
                occurred_at=now,
                detail={
                    "reason": outcome.reason,
                    "priority": outcome.request.priority,
                    "trigger_id": outcome.request.trigger_id,
                },
            )

        return cycle

    def record_execution_success(
        self,
        workflow_id: str,
        step_id: str,
        *,
        now: float,
    ) -> WorkflowRecoveryDecision:
        """Complete execution and queue downstream steps."""

        self._registry.graph(workflow_id)

        decision = self._recovery.record_execution_success(
            workflow_id,
            step_id,
            now=now,
        )

        self._registry.update_step(
            workflow_id,
            step_id,
            "succeeded",
        )

        self._observer.record(
            workflow_id=workflow_id,
            step_id=step_id,
            kind=WorkflowRuntimeEventKind.EXECUTION_SUCCEEDED,
            occurred_at=now,
            detail={
                "attempts_started": decision.attempts_started,
            },
        )

        self.evaluate_dependencies(
            workflow_id,
            now=now,
        )

        return decision

    def record_execution_failure(
        self,
        workflow_id: str,
        step_id: str,
        *,
        now: float,
        reason: str = "",
    ) -> WorkflowRecoveryDecision:
        """Record execution failure and schedule recovery."""

        self._registry.graph(workflow_id)

        decision = self._recovery.record_execution_failure(
            workflow_id,
            step_id,
            now=now,
            reason=reason,
        )

        self._observer.record(
            workflow_id=workflow_id,
            step_id=step_id,
            kind=WorkflowRuntimeEventKind.EXECUTION_FAILED,
            occurred_at=now,
            detail={
                "reason": reason,
                "action": decision.action.value,
                "attempts_started": decision.attempts_started,
            },
        )

        if decision.action is WorkflowRecoveryAction.RETRY:
            self._registry.update_step(
                workflow_id,
                step_id,
                "retry_waiting",
            )

            self._observer.record(
                workflow_id=workflow_id,
                step_id=step_id,
                kind=WorkflowRuntimeEventKind.RETRY_SCHEDULED,
                occurred_at=now,
                detail={
                    "next_eligible_at": decision.next_eligible_at,
                },
            )
        else:
            self._registry.update_step(
                workflow_id,
                step_id,
                "failed",
            )

            self.evaluate_dependencies(
                workflow_id,
                now=now,
            )

        return decision

    def check_timeouts(
        self,
        *,
        now: float,
    ) -> tuple[WorkflowRecoveryDecision, ...]:
        """Detect expired active executions."""

        decisions = self._recovery.check_timeouts(
            now=now,
        )

        for decision in decisions:
            workflow_id = decision.workflow_id
            step_id = decision.step_id

            self._observer.record(
                workflow_id=workflow_id,
                step_id=step_id,
                kind=WorkflowRuntimeEventKind.TIMEOUT_DETECTED,
                occurred_at=now,
                detail={
                    "action": decision.action.value,
                    "attempts_started": decision.attempts_started,
                },
            )

            if decision.action is WorkflowRecoveryAction.RETRY:
                self._registry.update_step(
                    workflow_id,
                    step_id,
                    "retry_waiting",
                )

                self._observer.record(
                    workflow_id=workflow_id,
                    step_id=step_id,
                    kind=WorkflowRuntimeEventKind.RETRY_SCHEDULED,
                    occurred_at=now,
                    detail={
                        "next_eligible_at": (
                            decision.next_eligible_at
                        ),
                    },
                )
            else:
                self._registry.update_step(
                    workflow_id,
                    step_id,
                    "failed",
                )

                self.evaluate_dependencies(
                    workflow_id,
                    now=now,
                )

        return decisions

    def release_ready_retries(
        self,
        *,
        now: float,
    ) -> tuple:
        """Release backoff-complete retries to the scheduler."""

        released = self._recovery.release_ready_retries(
            now=now,
        )

        for candidate in released:
            self._registry.update_step(
                candidate.workflow_id,
                candidate.step_id,
                "pending",
            )

            self._observer.record(
                workflow_id=candidate.workflow_id,
                step_id=candidate.step_id,
                kind=WorkflowRuntimeEventKind.RETRY_RELEASED,
                occurred_at=now,
                detail={
                    "priority": candidate.priority,
                    "retry_attempt": candidate.metadata.get(
                        "retry_attempt"
                    ),
                },
            )

        return released

    def snapshot(
        self,
        workflow_id: str,
    ) -> WorkflowRuntimeSnapshot:
        """Return runtime states and observability metrics."""

        self._registry.graph(workflow_id)

        pending = tuple(
            candidate
            for candidate
            in self.dispatch_coordinator.scheduler.pending()
            if candidate.workflow_id == workflow_id
        )

        inflight = tuple(
            candidate
            for candidate in self._recovery.inflight()
            if candidate.workflow_id == workflow_id
        )

        retry_waiting = tuple(
            candidate
            for candidate in self._recovery.waiting_retries()
            if candidate.workflow_id == workflow_id
        )

        return WorkflowRuntimeSnapshot(
            workflow_id=workflow_id,
            states=self._registry.states(workflow_id),
            pending_count=len(pending),
            inflight_count=len(inflight),
            retry_waiting_count=len(retry_waiting),
            metrics=self._observer.metrics(
                workflow_id=workflow_id
            ),
        )

    def _record_queued(
        self,
        queued: Iterable,
        *,
        now: float,
    ) -> None:
        """Record scheduler admission events."""

        for candidate in queued:
            self._observer.record(
                workflow_id=candidate.workflow_id,
                step_id=candidate.step_id,
                kind=WorkflowRuntimeEventKind.ACTIVATION_QUEUED,
                occurred_at=now,
                detail={
                    "priority": candidate.priority,
                    "trigger_id": candidate.trigger_id,
                },
            )
