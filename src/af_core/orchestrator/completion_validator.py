from __future__ import annotations

from .execution_audit_models import (
    CompletionState,
    CompletionVerificationRequest,
    ExecutionAuditRecord,
)


class CompletionValidatorError(RuntimeError):
    pass


class CompletionValidator:
    """
    Validates whether an execution can be
    considered completed.

    Validation dimensions:
    - Audit existence
    - Evidence availability
    - Completion state
    """

    def __init__(
        self,
        *,
        audit_collector=None,
    ) -> None:
        self.audit_collector = (
            audit_collector
        )

    def validate(
        self,
        request: CompletionVerificationRequest,
    ) -> CompletionState:

        records = self._records(
            request.run_id,
            request.step_id,
        )

        if not records:
            return CompletionState.FAILED

        completed = [
            record
            for record in records
            if (
                record.completion_state
                is CompletionState.VERIFIED
            )
        ]

        if not completed:
            return CompletionState.FAILED

        if request.evidence_ids:
            evidence_ids = {
                evidence.evidence_id
                for record in completed
                for evidence in record.evidence
            }

            if not set(
                request.evidence_ids
            ).issubset(
                evidence_ids
            ):
                return CompletionState.FAILED

        return CompletionState.VERIFIED

    def validate_record(
        self,
        record: ExecutionAuditRecord,
    ) -> bool:

        return (
            record.completion_state
            is CompletionState.VERIFIED
        )

    def _records(
        self,
        run_id: str,
        step_id: str,
    ) -> tuple[
        ExecutionAuditRecord,
        ...
    ]:

        if self.audit_collector is None:
            return ()

        return tuple(
            record
            for record
            in self.audit_collector.history()
            if (
                record.run_id == run_id
                and record.step_id == step_id
            )
        )
