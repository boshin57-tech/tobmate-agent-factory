from __future__ import annotations

from af_core.orchestrator.audit_collector_engine import (
    AuditCollectorEngine,
)

from af_core.orchestrator.completion_validator import (
    CompletionValidator,
)

from af_core.orchestrator.execution_audit_models import (
    AuditEventType,
    CompletionState,
    CompletionVerificationRequest,
    ExecutionEvidence,
)

from af_core.orchestrator.governance_history_store import (
    GovernanceHistoryStore,
)


def test_audit_completion_validation_success():

    collector = AuditCollectorEngine()

    collector.record_completion(
        run_id="run-1",
        step_id="step-1",
    )

    validator = CompletionValidator(
        audit_collector=collector
    )

    result = validator.validate(
        CompletionVerificationRequest(
            run_id="run-1",
            step_id="step-1",
        )
    )

    assert result is CompletionState.VERIFIED


def test_completion_fails_without_audit():

    collector = AuditCollectorEngine()

    validator = CompletionValidator(
        audit_collector=collector
    )

    result = validator.validate(
        CompletionVerificationRequest(
            run_id="run-2",
            step_id="step-2",
        )
    )

    assert result is CompletionState.FAILED


def test_completion_evidence_validation():

    collector = AuditCollectorEngine()

    evidence = ExecutionEvidence(
        evidence_id="ev-1",
        run_id="run-3",
        step_id="step-3",
        output_hash="hash",
    )

    collector.record_completion(
        run_id="run-3",
        step_id="step-3",
        evidence=(evidence,),
    )

    validator = CompletionValidator(
        audit_collector=collector
    )

    result = validator.validate(
        CompletionVerificationRequest(
            run_id="run-3",
            step_id="step-3",
            evidence_ids=(
                "ev-1",
            ),
        )
    )

    assert result is CompletionState.VERIFIED


def test_missing_evidence_is_rejected():

    collector = AuditCollectorEngine()

    collector.record_completion(
        run_id="run-4",
        step_id="step-4",
    )

    validator = CompletionValidator(
        audit_collector=collector
    )

    result = validator.validate(
        CompletionVerificationRequest(
            run_id="run-4",
            step_id="step-4",
            evidence_ids=(
                "missing",
            ),
        )
    )

    assert result is CompletionState.FAILED


def test_governance_history_append():

    store = GovernanceHistoryStore()

    event = store.append(
        run_id="run-5",
        step_id="step-5",
        event_type=(
            AuditEventType
            .COMPLETION_VERIFIED
        ),
        message=(
            "Completion verified"
        ),
    )

    assert event.run_id == "run-5"
    assert store.count == 1


def test_governance_history_query():

    store = GovernanceHistoryStore()

    store.append(
        run_id="run-6",
        step_id="step-a",
        event_type=(
            AuditEventType
            .EXECUTION_STARTED
        ),
        message="started",
    )

    store.append(
        run_id="run-6",
        step_id="step-b",
        event_type=(
            AuditEventType
            .EXECUTION_COMPLETED
        ),
        message="completed",
    )

    history = store.timeline(
        run_id="run-6"
    )

    assert len(history) == 2


def test_step_history_filter():

    store = GovernanceHistoryStore()

    store.append(
        run_id="run-7",
        step_id="step-target",
        event_type=(
            AuditEventType
            .EXECUTION_COMPLETED
        ),
        message="done",
    )

    result = store.find_step_history(
        run_id="run-7",
        step_id="step-target",
    )

    assert len(result) == 1
