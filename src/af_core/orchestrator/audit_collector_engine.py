from __future__ import annotations

from uuid import uuid4

from .execution_audit_models import (
    AuditEventType,
    CompletionState,
    ExecutionAuditRecord,
    ExecutionEvidence,
)


class AuditCollectorError(RuntimeError):
    pass


class AuditCollectorEngine:
    """
    Collects execution lifecycle events and
    maintains immutable audit history.
    """

    def __init__(self) -> None:
        self._records: list[
            ExecutionAuditRecord
        ] = []

    def record(
        self,
        *,
        run_id: str,
        step_id: str,
        event_type: AuditEventType,
        message: str,
        evidence: tuple[
            ExecutionEvidence,
            ...
        ] = (),
        completion_state: (
            CompletionState
        ) = CompletionState.PENDING,
        metadata: dict[str, str] | None = None,
    ) -> ExecutionAuditRecord:

        record = ExecutionAuditRecord(
            audit_id=str(uuid4()),
            run_id=run_id,
            step_id=step_id,
            event_type=event_type,
            completion_state=completion_state,
            message=message,
            evidence=evidence,
            metadata=(
                metadata or {}
            ),
        )

        self._records.append(
            record
        )

        return record

    def record_start(
        self,
        *,
        run_id: str,
        step_id: str,
        agent_id: str | None = None,
    ) -> ExecutionAuditRecord:

        return self.record(
            run_id=run_id,
            step_id=step_id,
            event_type=(
                AuditEventType
                .EXECUTION_STARTED
            ),
            message=(
                "Execution started"
            ),
            metadata={
                "agent_id": (
                    agent_id or ""
                )
            },
        )

    def record_completion(
        self,
        *,
        run_id: str,
        step_id: str,
        evidence: tuple[
            ExecutionEvidence,
            ...
        ] = (),
    ) -> ExecutionAuditRecord:

        return self.record(
            run_id=run_id,
            step_id=step_id,
            event_type=(
                AuditEventType
                .EXECUTION_COMPLETED
            ),
            completion_state=(
                CompletionState
                .VERIFIED
            ),
            message=(
                "Execution completed"
            ),
            evidence=evidence,
        )

    def record_failure(
        self,
        *,
        run_id: str,
        step_id: str,
        reason: str,
    ) -> ExecutionAuditRecord:

        return self.record(
            run_id=run_id,
            step_id=step_id,
            event_type=(
                AuditEventType
                .EXECUTION_FAILED
            ),
            completion_state=(
                CompletionState.FAILED
            ),
            message=reason,
        )

    def history(
        self,
    ) -> tuple[
        ExecutionAuditRecord,
        ...
    ]:
        return tuple(
            self._records
        )

    def find_by_run(
        self,
        run_id: str,
    ) -> tuple[
        ExecutionAuditRecord,
        ...
    ]:

        return tuple(
            record
            for record in self._records
            if record.run_id == run_id
        )
