from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .tool_call_models import (
    NormalizedToolCall,
    ToolCallExecutionRecord,
)


class ToolBatchCallStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    POST_BUDGET_VIOLATION = (
        "POST_BUDGET_VIOLATION"
    )


class ToolBatchStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    PARTIALLY_SUCCEEDED = "PARTIALLY_SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class ToolBatchGovernancePolicy(BaseModel):
    maximum_calls_per_batch: int = Field(
        default=32,
        ge=1,
        le=1024,
    )
    maximum_calls_per_run: int | None = Field(
        default=None,
        ge=1,
        le=100000,
    )
    cancel_pending_on_failure: bool = False
    isolate_failures: bool = True
    mark_post_budget_violation: bool = True


class ToolBatchCallAudit(BaseModel):
    call_id: str
    tool_name: str
    status: ToolBatchCallStatus = (
        ToolBatchCallStatus.PENDING
    )
    started: bool = False
    completed: bool = False
    cancelled: bool = False
    error: str | None = None
    record: ToolCallExecutionRecord | None = None


class ToolBatchAudit(BaseModel):
    batch_id: str
    requested_count: int
    accepted_count: int = 0
    status: ToolBatchStatus = ToolBatchStatus.FAILED
    calls: list[ToolBatchCallAudit] = Field(
        default_factory=list
    )
    cancellation_requested: bool = False
    failure_isolated: bool = False
    reasons: list[str] = Field(default_factory=list)

    @property
    def succeeded_count(self) -> int:
        return sum(
            item.status
            is ToolBatchCallStatus.SUCCEEDED
            for item in self.calls
        )

    @property
    def failed_count(self) -> int:
        failed_statuses = {
            ToolBatchCallStatus.FAILED,
            ToolBatchCallStatus.BLOCKED,
            ToolBatchCallStatus.TIMED_OUT,
            ToolBatchCallStatus.POST_BUDGET_VIOLATION,
        }

        return sum(
            item.status in failed_statuses
            for item in self.calls
        )

    @property
    def cancelled_count(self) -> int:
        return sum(
            item.status
            is ToolBatchCallStatus.CANCELLED
            for item in self.calls
        )


class ToolBatchLimitError(RuntimeError):
    """Raised when a Tool batch exceeds governance limits."""


class ToolBatchGovernor:
    def __init__(
        self,
        policy: ToolBatchGovernancePolicy | None = None,
    ) -> None:
        self.policy = (
            policy or ToolBatchGovernancePolicy()
        )
        self._run_call_counts: dict[str, int] = {}
        self._audits: list[ToolBatchAudit] = []

    def begin(
        self,
        *,
        batch_id: str,
        calls: list[NormalizedToolCall],
        run_id: str | None = None,
    ) -> ToolBatchAudit:
        requested_count = len(calls)

        if (
            requested_count
            > self.policy.maximum_calls_per_batch
        ):
            raise ToolBatchLimitError(
                "Tool batch call count "
                f"{requested_count} exceeds maximum "
                f"{self.policy.maximum_calls_per_batch}."
            )

        if (
            run_id is not None
            and self.policy.maximum_calls_per_run
            is not None
        ):
            current = self._run_call_counts.get(
                run_id,
                0,
            )
            projected = current + requested_count

            if (
                projected
                > self.policy.maximum_calls_per_run
            ):
                raise ToolBatchLimitError(
                    "Tool run call count "
                    f"{projected} exceeds maximum "
                    f"{self.policy.maximum_calls_per_run} "
                    f"for run {run_id}."
                )

            self._run_call_counts[run_id] = projected

        audit = ToolBatchAudit(
            batch_id=batch_id,
            requested_count=requested_count,
            accepted_count=requested_count,
            calls=[
                ToolBatchCallAudit(
                    call_id=call.call_id,
                    tool_name=call.tool_name,
                )
                for call in calls
            ],
        )

        self._audits.append(audit)
        return audit

    def mark_running(
        self,
        audit: ToolBatchAudit,
        call_id: str,
    ) -> None:
        item = self._find_call(
            audit,
            call_id,
        )
        item.status = ToolBatchCallStatus.RUNNING
        item.started = True

    def mark_completed(
        self,
        audit: ToolBatchAudit,
        record: ToolCallExecutionRecord,
        *,
        post_budget_violation: bool = False,
    ) -> None:
        item = self._find_call(
            audit,
            record.call.call_id,
        )

        item.record = record
        item.completed = True
        item.error = record.result.error

        if (
            post_budget_violation
            and self.policy.mark_post_budget_violation
        ):
            item.status = (
                ToolBatchCallStatus
                .POST_BUDGET_VIOLATION
            )
            return

        status = record.result.status.value

        item.status = {
            "SUCCEEDED": ToolBatchCallStatus.SUCCEEDED,
            "FAILED": ToolBatchCallStatus.FAILED,
            "BLOCKED": ToolBatchCallStatus.BLOCKED,
            "TIMED_OUT": ToolBatchCallStatus.TIMED_OUT,
        }.get(
            status,
            ToolBatchCallStatus.FAILED,
        )

    def mark_cancelled(
        self,
        audit: ToolBatchAudit,
        call_id: str,
        *,
        reason: str = (
            "Cancelled by batch governance."
        ),
    ) -> None:
        item = self._find_call(
            audit,
            call_id,
        )

        item.status = ToolBatchCallStatus.CANCELLED
        item.cancelled = True
        item.completed = True
        item.error = reason

    def finalize(
        self,
        audit: ToolBatchAudit,
    ) -> ToolBatchAudit:
        succeeded = audit.succeeded_count
        failed = audit.failed_count
        cancelled = audit.cancelled_count

        if (
            succeeded == audit.accepted_count
            and failed == 0
            and cancelled == 0
        ):
            audit.status = ToolBatchStatus.SUCCEEDED

        elif succeeded > 0:
            audit.status = (
                ToolBatchStatus.PARTIALLY_SUCCEEDED
            )

        elif cancelled == audit.accepted_count:
            audit.status = ToolBatchStatus.CANCELLED

        elif any(
            item.status
            is ToolBatchCallStatus.BLOCKED
            for item in audit.calls
        ):
            audit.status = ToolBatchStatus.BLOCKED

        else:
            audit.status = ToolBatchStatus.FAILED

        audit.failure_isolated = (
            self.policy.isolate_failures
            and failed > 0
            and succeeded > 0
        )

        return audit

    def audits(self) -> list[ToolBatchAudit]:
        return [
            item.model_copy(deep=True)
            for item in self._audits
        ]

    def latest(
        self,
    ) -> ToolBatchAudit | None:
        if not self._audits:
            return None

        return self._audits[-1].model_copy(
            deep=True
        )

    def run_call_count(
        self,
        run_id: str,
    ) -> int:
        return self._run_call_counts.get(
            run_id,
            0,
        )

    def _find_call(
        self,
        audit: ToolBatchAudit,
        call_id: str,
    ) -> ToolBatchCallAudit:
        for item in audit.calls:
            if item.call_id == call_id:
                return item

        raise KeyError(
            f"Tool call is not part of batch "
            f"{audit.batch_id}: {call_id}"
        )
