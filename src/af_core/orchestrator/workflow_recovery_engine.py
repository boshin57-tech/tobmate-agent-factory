"""Workflow retry, timeout, backoff and recovery models."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class WorkflowRecoveryError(ValueError):
    """Raised when a workflow recovery invariant is violated."""


class WorkflowFailureKind(str, Enum):
    """Failure categories understood by recovery processing."""

    REJECTED = "rejected"
    DISPATCH_ERROR = "dispatch_error"
    TIMEOUT = "timeout"
    EXECUTION_FAILURE = "execution_failure"
    CANCELLED = "cancelled"


class WorkflowRecoveryAction(str, Enum):
    """Recovery action selected after an attempt."""

    RETRY = "retry"
    EXHAUSTED = "exhausted"
    TERMINAL = "terminal"
    SUCCEEDED = "succeeded"


@dataclass(frozen=True, slots=True)
class WorkflowRetryPolicy:
    """Exponential retry and backoff policy."""

    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    multiplier: float = 2.0
    max_delay_seconds: float = 60.0
    retryable_failures: frozenset[WorkflowFailureKind] = frozenset(
        {
            WorkflowFailureKind.REJECTED,
            WorkflowFailureKind.DISPATCH_ERROR,
            WorkflowFailureKind.TIMEOUT,
            WorkflowFailureKind.EXECUTION_FAILURE,
        }
    )

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise WorkflowRecoveryError(
                "max_attempts must be at least one"
            )

        if self.initial_delay_seconds < 0:
            raise WorkflowRecoveryError(
                "initial_delay_seconds must not be negative"
            )

        if self.multiplier < 1:
            raise WorkflowRecoveryError(
                "multiplier must be at least one"
            )

        if self.max_delay_seconds < 0:
            raise WorkflowRecoveryError(
                "max_delay_seconds must not be negative"
            )

        if (
            self.max_delay_seconds
            < self.initial_delay_seconds
        ):
            raise WorkflowRecoveryError(
                "max_delay_seconds must be greater than or equal "
                "to initial_delay_seconds"
            )

    def delay_after_attempt(
        self,
        attempt_number: int,
    ) -> float:
        """Calculate the backoff delay after an attempt."""

        if attempt_number < 1:
            raise WorkflowRecoveryError(
                "attempt_number must be at least one"
            )

        delay = self.initial_delay_seconds * (
            self.multiplier ** (attempt_number - 1)
        )

        return min(delay, self.max_delay_seconds)


@dataclass(frozen=True, slots=True)
class WorkflowTimeoutPolicy:
    """Maximum execution duration for one active attempt."""

    timeout_seconds: float = 300.0

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise WorkflowRecoveryError(
                "timeout_seconds must be greater than zero"
            )


@dataclass(frozen=True, slots=True)
class WorkflowRecoveryState:
    """Recovery state belonging to one workflow step."""

    workflow_id: str
    step_id: str
    attempts_started: int = 0
    active: bool = False
    started_at: float | None = None
    deadline_at: float | None = None
    next_eligible_at: float | None = None
    terminal: bool = False
    succeeded: bool = False
    last_failure_kind: WorkflowFailureKind | None = None
    last_failure_reason: str = ""

    def __post_init__(self) -> None:
        if not self.workflow_id.strip():
            raise WorkflowRecoveryError(
                "workflow_id must not be empty"
            )

        if not self.step_id.strip():
            raise WorkflowRecoveryError(
                "step_id must not be empty"
            )

        if self.attempts_started < 0:
            raise WorkflowRecoveryError(
                "attempts_started must not be negative"
            )

    @property
    def key(self) -> tuple[str, str]:
        return self.workflow_id, self.step_id


@dataclass(frozen=True, slots=True)
class WorkflowRecoveryDecision:
    """Immutable recovery evaluation result."""

    workflow_id: str
    step_id: str
    action: WorkflowRecoveryAction
    attempts_started: int
    next_eligible_at: float | None = None
    failure_kind: WorkflowFailureKind | None = None
    reason: str = ""


class WorkflowFailureRecoveryEngine:
    """Deterministic retry, timeout and failure recovery engine."""

    def __init__(
        self,
        *,
        retry_policy: WorkflowRetryPolicy | None = None,
        timeout_policy: WorkflowTimeoutPolicy | None = None,
    ) -> None:
        self._retry_policy = retry_policy or WorkflowRetryPolicy()
        self._timeout_policy = (
            timeout_policy or WorkflowTimeoutPolicy()
        )
        self._states: dict[
            tuple[str, str],
            WorkflowRecoveryState,
        ] = {}

    @property
    def retry_policy(self) -> WorkflowRetryPolicy:
        return self._retry_policy

    @property
    def timeout_policy(self) -> WorkflowTimeoutPolicy:
        return self._timeout_policy

    def get(
        self,
        workflow_id: str,
        step_id: str,
    ) -> WorkflowRecoveryState:
        """Return existing state or create a new idle state."""

        key = workflow_id, step_id

        if key not in self._states:
            self._states[key] = WorkflowRecoveryState(
                workflow_id=workflow_id,
                step_id=step_id,
            )

        return self._states[key]

    def begin_attempt(
        self,
        workflow_id: str,
        step_id: str,
        *,
        now: float,
    ) -> WorkflowRecoveryState:
        """Start one eligible execution attempt."""

        state = self.get(workflow_id, step_id)

        if state.terminal:
            raise WorkflowRecoveryError(
                "cannot start an attempt for a terminal workflow step"
            )

        if state.active:
            raise WorkflowRecoveryError(
                "workflow step already has an active attempt"
            )

        if (
            state.next_eligible_at is not None
            and now < state.next_eligible_at
        ):
            raise WorkflowRecoveryError(
                "workflow step is still inside retry backoff"
            )

        if (
            state.attempts_started
            >= self._retry_policy.max_attempts
        ):
            raise WorkflowRecoveryError(
                "maximum workflow attempts already exhausted"
            )

        updated = replace(
            state,
            attempts_started=state.attempts_started + 1,
            active=True,
            started_at=now,
            deadline_at=(
                now + self._timeout_policy.timeout_seconds
            ),
            next_eligible_at=None,
        )

        self._states[state.key] = updated
        return updated

    def record_success(
        self,
        workflow_id: str,
        step_id: str,
        *,
        now: float,
    ) -> WorkflowRecoveryDecision:
        """Mark an active attempt as successfully completed."""

        state = self._require_active(
            workflow_id,
            step_id,
        )

        updated = replace(
            state,
            active=False,
            started_at=None,
            deadline_at=None,
            next_eligible_at=None,
            terminal=True,
            succeeded=True,
            last_failure_kind=None,
            last_failure_reason="",
        )

        self._states[state.key] = updated

        return WorkflowRecoveryDecision(
            workflow_id=workflow_id,
            step_id=step_id,
            action=WorkflowRecoveryAction.SUCCEEDED,
            attempts_started=updated.attempts_started,
            reason=f"completed at {now}",
        )

    def record_failure(
        self,
        workflow_id: str,
        step_id: str,
        *,
        kind: WorkflowFailureKind,
        now: float,
        reason: str = "",
    ) -> WorkflowRecoveryDecision:
        """Record failure and choose retry or terminal recovery."""

        state = self._require_active(
            workflow_id,
            step_id,
        )

        retryable = (
            kind in self._retry_policy.retryable_failures
        )
        exhausted = (
            state.attempts_started
            >= self._retry_policy.max_attempts
        )

        if retryable and not exhausted:
            delay = self._retry_policy.delay_after_attempt(
                state.attempts_started
            )
            next_eligible_at = now + delay

            updated = replace(
                state,
                active=False,
                started_at=None,
                deadline_at=None,
                next_eligible_at=next_eligible_at,
                last_failure_kind=kind,
                last_failure_reason=reason,
            )

            action = WorkflowRecoveryAction.RETRY
        else:
            next_eligible_at = None

            updated = replace(
                state,
                active=False,
                started_at=None,
                deadline_at=None,
                next_eligible_at=None,
                terminal=True,
                last_failure_kind=kind,
                last_failure_reason=reason,
            )

            action = (
                WorkflowRecoveryAction.EXHAUSTED
                if exhausted
                else WorkflowRecoveryAction.TERMINAL
            )

        self._states[state.key] = updated

        return WorkflowRecoveryDecision(
            workflow_id=workflow_id,
            step_id=step_id,
            action=action,
            attempts_started=updated.attempts_started,
            next_eligible_at=next_eligible_at,
            failure_kind=kind,
            reason=reason,
        )

    def check_timeout(
        self,
        workflow_id: str,
        step_id: str,
        *,
        now: float,
    ) -> WorkflowRecoveryDecision | None:
        """Convert an expired active attempt into a timeout failure."""

        state = self.get(workflow_id, step_id)

        if not state.active:
            return None

        if state.deadline_at is None:
            return None

        if now < state.deadline_at:
            return None

        return self.record_failure(
            workflow_id,
            step_id,
            kind=WorkflowFailureKind.TIMEOUT,
            now=now,
            reason=(
                f"attempt exceeded deadline "
                f"{state.deadline_at}"
            ),
        )

    def is_retry_ready(
        self,
        workflow_id: str,
        step_id: str,
        *,
        now: float,
    ) -> bool:
        """Return whether another attempt may begin."""

        state = self.get(workflow_id, step_id)

        return (
            not state.terminal
            and not state.active
            and state.next_eligible_at is not None
            and now >= state.next_eligible_at
            and state.attempts_started
            < self._retry_policy.max_attempts
        )

    def clear_workflow(
        self,
        workflow_id: str,
    ) -> tuple[WorkflowRecoveryState, ...]:
        """Remove all recovery state for one workflow."""

        removed = tuple(
            sorted(
                (
                    state
                    for state in self._states.values()
                    if state.workflow_id == workflow_id
                ),
                key=lambda state: state.step_id,
            )
        )

        for state in removed:
            del self._states[state.key]

        return removed

    def _require_active(
        self,
        workflow_id: str,
        step_id: str,
    ) -> WorkflowRecoveryState:
        state = self.get(workflow_id, step_id)

        if not state.active:
            raise WorkflowRecoveryError(
                "workflow step has no active attempt"
            )

        return state
