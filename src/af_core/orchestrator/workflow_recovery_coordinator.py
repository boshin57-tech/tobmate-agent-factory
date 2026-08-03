"""Recovery-aware workflow lifecycle dispatch coordination."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Mapping

from af_core.orchestrator.workflow_dispatch_coordinator import (
    WorkflowDispatchCoordinator,
    WorkflowDispatchCycle,
    WorkflowDispatchOutcome,
    WorkflowDispatchRequest,
    WorkflowDispatchStatus,
    WorkflowLifecycleDispatcher,
)
from af_core.orchestrator.workflow_priority_scheduler import (
    WorkflowScheduleCandidate,
)
from af_core.orchestrator.workflow_recovery_engine import (
    WorkflowFailureKind,
    WorkflowFailureRecoveryEngine,
    WorkflowRecoveryAction,
    WorkflowRecoveryDecision,
)


class WorkflowRecoveryCoordinatorError(ValueError):
    """Raised when dispatch recovery coordination is invalid."""


class _RecoveryDispatcher:
    """Wrap a lifecycle dispatcher with attempt recovery tracking."""

    def __init__(
        self,
        dispatcher: WorkflowLifecycleDispatcher,
        recovery: WorkflowFailureRecoveryEngine,
        *,
        now: float,
    ) -> None:
        self._dispatcher = dispatcher
        self._recovery = recovery
        self._now = now

    def dispatch(
        self,
        request: WorkflowDispatchRequest,
    ) -> WorkflowDispatchOutcome | bool:
        self._recovery.begin_attempt(
            request.workflow_id,
            request.step_id,
            now=self._now,
        )

        try:
            outcome = self._dispatcher.dispatch(request)
        except Exception as exc:
            self._recovery.record_failure(
                request.workflow_id,
                request.step_id,
                kind=WorkflowFailureKind.DISPATCH_ERROR,
                now=self._now,
                reason=f"{type(exc).__name__}: {exc}",
            )
            raise

        if isinstance(outcome, bool):
            if not outcome:
                self._recovery.record_failure(
                    request.workflow_id,
                    request.step_id,
                    kind=WorkflowFailureKind.REJECTED,
                    now=self._now,
                    reason="lifecycle dispatcher rejected request",
                )

            return outcome

        if isinstance(outcome, WorkflowDispatchOutcome):
            if outcome.status is WorkflowDispatchStatus.REJECTED:
                self._recovery.record_failure(
                    request.workflow_id,
                    request.step_id,
                    kind=WorkflowFailureKind.REJECTED,
                    now=self._now,
                    reason=outcome.reason,
                )

            elif outcome.status is WorkflowDispatchStatus.FAILED:
                self._recovery.record_failure(
                    request.workflow_id,
                    request.step_id,
                    kind=WorkflowFailureKind.DISPATCH_ERROR,
                    now=self._now,
                    reason=outcome.reason,
                )

            return outcome

        self._recovery.record_failure(
            request.workflow_id,
            request.step_id,
            kind=WorkflowFailureKind.DISPATCH_ERROR,
            now=self._now,
            reason="unsupported lifecycle dispatcher result",
        )

        return outcome


class WorkflowRecoveryCoordinator:
    """Coordinate dispatch attempts, retries, timeouts and completion."""

    def __init__(
        self,
        dispatch_coordinator: WorkflowDispatchCoordinator,
        recovery_engine: WorkflowFailureRecoveryEngine,
    ) -> None:
        self._dispatch = dispatch_coordinator
        self._recovery = recovery_engine
        self._inflight: dict[
            tuple[str, str],
            WorkflowScheduleCandidate,
        ] = {}
        self._retry_waiting: dict[
            tuple[str, str],
            WorkflowScheduleCandidate,
        ] = {}

    @property
    def dispatch_coordinator(
        self,
    ) -> WorkflowDispatchCoordinator:
        return self._dispatch

    @property
    def recovery_engine(
        self,
    ) -> WorkflowFailureRecoveryEngine:
        return self._recovery

    def dispatch_ready(
        self,
        dispatcher: WorkflowLifecycleDispatcher,
        *,
        now: float,
        limit: int,
        states_by_workflow: Mapping[
            str,
            Mapping[str, object],
        ]
        | None = None,
        available_capabilities: Iterable[str] = (),
    ) -> WorkflowDispatchCycle:
        """Dispatch eligible work with retry and backoff protection."""

        effective_states = self._effective_states(
            states_by_workflow or {},
            now=now,
        )

        preview = self._dispatch.scheduler.select(
            limit=limit,
            states_by_workflow=effective_states,
            available_capabilities=available_capabilities,
        )

        selected_by_key = {
            candidate.key: candidate
            for candidate in preview.selected
        }

        cycle = self._dispatch.dispatch_ready(
            _RecoveryDispatcher(
                dispatcher,
                self._recovery,
                now=now,
            ),
            limit=limit,
            states_by_workflow=effective_states,
            available_capabilities=available_capabilities,
        )

        for outcome in cycle.outcomes:
            key = (
                outcome.request.workflow_id,
                outcome.request.step_id,
            )

            if outcome.accepted:
                candidate = selected_by_key[key]
                self._inflight[key] = candidate
                continue

            state = self._recovery.get(*key)

            if state.terminal:
                self._remove_pending_if_present(*key)

        return cycle

    def record_execution_success(
        self,
        workflow_id: str,
        step_id: str,
        *,
        now: float,
    ) -> WorkflowRecoveryDecision:
        """Complete an accepted lifecycle execution successfully."""

        key = workflow_id, step_id
        self._require_inflight(key)

        decision = self._recovery.record_success(
            workflow_id,
            step_id,
            now=now,
        )

        del self._inflight[key]
        return decision

    def record_execution_failure(
        self,
        workflow_id: str,
        step_id: str,
        *,
        now: float,
        reason: str = "",
    ) -> WorkflowRecoveryDecision:
        """Record execution failure and retain a retry template."""

        key = workflow_id, step_id
        candidate = self._require_inflight(key)

        decision = self._recovery.record_failure(
            workflow_id,
            step_id,
            kind=WorkflowFailureKind.EXECUTION_FAILURE,
            now=now,
            reason=reason,
        )

        del self._inflight[key]

        if decision.action is WorkflowRecoveryAction.RETRY:
            self._retry_waiting[key] = candidate

        return decision

    def check_timeouts(
        self,
        *,
        now: float,
    ) -> tuple[WorkflowRecoveryDecision, ...]:
        """Evaluate all active executions for timeout recovery."""

        decisions: list[WorkflowRecoveryDecision] = []

        for key, candidate in tuple(self._inflight.items()):
            decision = self._recovery.check_timeout(
                key[0],
                key[1],
                now=now,
            )

            if decision is None:
                continue

            decisions.append(decision)
            del self._inflight[key]

            if decision.action is WorkflowRecoveryAction.RETRY:
                self._retry_waiting[key] = candidate

        return tuple(decisions)

    def release_ready_retries(
        self,
        *,
        now: float,
    ) -> tuple[WorkflowScheduleCandidate, ...]:
        """Return backoff-complete retries to the priority scheduler."""

        released: list[WorkflowScheduleCandidate] = []

        for key, candidate in tuple(
            self._retry_waiting.items()
        ):
            if not self._recovery.is_retry_ready(
                key[0],
                key[1],
                now=now,
            ):
                continue

            metadata = dict(candidate.metadata)
            metadata["retry_attempt"] = (
                self._recovery.get(*key).attempts_started + 1
            )

            retry_candidate = replace(
                candidate,
                sequence=0,
                metadata=metadata,
            )

            stored = self._dispatch.scheduler.enqueue(
                retry_candidate
            )

            released.append(stored)
            del self._retry_waiting[key]

        return tuple(released)

    def inflight(
        self,
    ) -> tuple[WorkflowScheduleCandidate, ...]:
        return tuple(
            sorted(
                self._inflight.values(),
                key=lambda item: (
                    item.workflow_id,
                    item.step_id,
                ),
            )
        )

    def waiting_retries(
        self,
    ) -> tuple[WorkflowScheduleCandidate, ...]:
        return tuple(
            sorted(
                self._retry_waiting.values(),
                key=lambda item: (
                    item.workflow_id,
                    item.step_id,
                ),
            )
        )

    def _effective_states(
        self,
        states: Mapping[str, Mapping[str, object]],
        *,
        now: float,
    ) -> dict[str, dict[str, object]]:
        effective = {
            workflow_id: dict(step_states)
            for workflow_id, step_states in states.items()
        }

        for candidate in self._dispatch.scheduler.pending():
            recovery = self._recovery.get(
                candidate.workflow_id,
                candidate.step_id,
            )

            backoff_active = (
                recovery.next_eligible_at is not None
                and now < recovery.next_eligible_at
            )

            if (
                recovery.terminal
                or recovery.active
                or backoff_active
            ):
                effective.setdefault(
                    candidate.workflow_id,
                    {},
                )[candidate.step_id] = "running"

        return effective

    def _require_inflight(
        self,
        key: tuple[str, str],
    ) -> WorkflowScheduleCandidate:
        try:
            return self._inflight[key]
        except KeyError as exc:
            raise WorkflowRecoveryCoordinatorError(
                "workflow step is not currently in flight: "
                f"{key[0]}/{key[1]}"
            ) from exc

    def _remove_pending_if_present(
        self,
        workflow_id: str,
        step_id: str,
    ) -> None:
        keys = {
            candidate.key
            for candidate in self._dispatch.scheduler.pending()
        }

        if (workflow_id, step_id) in keys:
            self._dispatch.scheduler.remove(
                workflow_id,
                step_id,
            )
