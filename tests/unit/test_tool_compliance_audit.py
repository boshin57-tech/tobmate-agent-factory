from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest

from af_core.runtime.tool_call_models import (
    NormalizedToolCall,
)
from af_core.runtime.tool_call_runtime import (
    ToolCallRuntime,
)
from af_core.tools.models import (
    ExternalToolCall,
    ExternalToolDescriptor,
    ExternalToolResult,
    ExternalToolRisk,
    ToolExecutionStatus,
)
from af_core.tools.registry import (
    ExternalToolRegistry,
)
from af_core.tools.tool_compliance_audit import (
    InMemoryToolAuditChain,
    ToolAuditChainError,
    ToolAuditEvent,
    ToolAuditEventType,
    ToolAuditLogger,
    ToolAuditSeverity,
    ToolAuditSource,
    ToolAuditSubject,
    ToolComplianceAuditBinding,
    ToolComplianceAuditBindingError,
    ToolComplianceAuditService,
    ToolComplianceReportBuilder,
    ToolComplianceRule,
    ToolComplianceRuleEngine,
    ToolComplianceRuleRegistry,
    ToolComplianceRuleRegistryError,
    ToolComplianceRuleType,
    ToolComplianceStatus,
    ToolComplianceViolationHistory,
    ToolComplianceViolationType,
    ToolLifecycleAuditAdapter,
    ToolTelemetryAuditAdapter,
    default_tool_compliance_rules,
    utc_now,
)
from af_core.tools.tool_telemetry import (
    InMemoryToolTelemetryStream,
    ToolTelemetryCollector,
    ToolTelemetryEvent,
    ToolTelemetryEventType,
)


def audit_event(
    event_id: str,
    *,
    event_type: ToolAuditEventType,
    tool_id: str = "tool.echo",
    project_id: str | None = "project-1",
    agent_id: str | None = "agent-1",
    request_id: str | None = None,
    severity: ToolAuditSeverity = (
        ToolAuditSeverity.INFO
    ),
    metadata: dict | None = None,
    occurred_at=None,
) -> ToolAuditEvent:
    return ToolAuditEvent(
        event_id=event_id,
        event_type=event_type,
        source=ToolAuditSource.TOOL_RUNTIME,
        severity=severity,
        subject=ToolAuditSubject(
            tool_id=tool_id,
            project_id=project_id,
            agent_id=agent_id,
            request_id=request_id,
        ),
        metadata=metadata or {},
        occurred_at=occurred_at or utc_now(),
    )


def default_engine():
    registry = ToolComplianceRuleRegistry()

    for rule in default_tool_compliance_rules():
        registry.register(rule)

    engine = ToolComplianceRuleEngine(
        rules=registry
    )

    return registry, engine


def test_audit_chain_links_records_and_verifies() -> None:
    chain = InMemoryToolAuditChain()

    first = chain.append(
        audit_event(
            "event-1",
            event_type=(
                ToolAuditEventType
                .INSTALL_REQUESTED
            ),
            request_id="request-1",
        )
    )
    second = chain.append(
        audit_event(
            "event-2",
            event_type=(
                ToolAuditEventType
                .INSTALL_APPROVED
            ),
            request_id="request-1",
        )
    )

    assert first.sequence == 1
    assert second.sequence == 2
    assert second.previous_hash == (
        first.record_hash
    )

    verification = chain.verify()

    assert verification.valid is True
    assert verification.record_count == 2


def test_audit_chain_returns_defensive_copies() -> None:
    chain = InMemoryToolAuditChain()

    chain.append(
        audit_event(
            "event-1",
            event_type=(
                ToolAuditEventType
                .TOOL_CALL_SUCCEEDED
            ),
        )
    )

    copied = chain.records()
    copied[0].event.message = "tampered"

    internal = chain.records()

    assert internal[0].event.message == ""
    assert chain.verify().valid is True


def test_audit_chain_detects_internal_tampering() -> None:
    chain = InMemoryToolAuditChain()

    chain.append(
        audit_event(
            "event-1",
            event_type=(
                ToolAuditEventType
                .TOOL_CALL_SUCCEEDED
            ),
        )
    )

    # 의도적인 내부 변조 시뮬레이션
    chain._records[0].event.message = (
        "tampered internal record"
    )

    verification = chain.verify()

    assert verification.valid is False
    assert verification.first_invalid_sequence == 1
    assert verification.error is not None


def test_audit_chain_capacity_is_enforced() -> None:
    chain = InMemoryToolAuditChain(
        maximum_records=1
    )

    chain.append(
        audit_event(
            "event-1",
            event_type=(
                ToolAuditEventType
                .TOOL_CALL_SUCCEEDED
            ),
        )
    )

    with pytest.raises(
        ToolAuditChainError,
        match="capacity",
    ):
        chain.append(
            audit_event(
                "event-2",
                event_type=(
                    ToolAuditEventType
                    .TOOL_CALL_FAILED
                ),
            )
        )


def test_install_completion_requires_approval() -> None:
    chain = InMemoryToolAuditChain()
    registry, engine = default_engine()

    del registry

    completed = chain.append(
        audit_event(
            "completed",
            event_type=(
                ToolAuditEventType
                .INSTALL_COMPLETED
            ),
            request_id="request-1",
        )
    )

    evaluations = engine.evaluate_record(
        record=completed,
        chain_records=chain.records(),
    )

    violations = [
        item.violation
        for item in evaluations
        if item.violation is not None
    ]

    assert len(violations) == 1
    assert violations[0].violation_type is (
        ToolComplianceViolationType
        .UNAPPROVED_INSTALLATION
    )
    assert violations[0].severity is (
        ToolAuditSeverity.CRITICAL
    )


def test_approved_installation_is_compliant() -> None:
    chain = InMemoryToolAuditChain()
    registry, engine = default_engine()

    del registry

    chain.append(
        audit_event(
            "approved",
            event_type=(
                ToolAuditEventType
                .INSTALL_APPROVED
            ),
            request_id="request-1",
        )
    )

    completed = chain.append(
        audit_event(
            "completed",
            event_type=(
                ToolAuditEventType
                .INSTALL_COMPLETED
            ),
            request_id="request-1",
        )
    )

    evaluations = engine.evaluate_record(
        record=completed,
        chain_records=chain.records(),
    )

    assert evaluations
    assert all(
        item.compliant
        for item in evaluations
    )
    assert engine.violations.count() == 0


def test_quarantined_tool_execution_is_detected() -> None:
    chain = InMemoryToolAuditChain()
    registry, engine = default_engine()

    del registry

    chain.append(
        audit_event(
            "quarantined",
            event_type=(
                ToolAuditEventType.QUARANTINED
            ),
        )
    )

    executed = chain.append(
        audit_event(
            "executed",
            event_type=(
                ToolAuditEventType
                .TOOL_CALL_SUCCEEDED
            ),
        )
    )

    evaluations = engine.evaluate_record(
        record=executed,
        chain_records=chain.records(),
    )

    violations = [
        item.violation
        for item in evaluations
        if item.violation is not None
    ]

    assert any(
        violation.violation_type is (
            ToolComplianceViolationType
            .QUARANTINED_TOOL_EXECUTION
        )
        for violation in violations
    )


def test_metadata_requirement_detects_missing_fields() -> None:
    chain = InMemoryToolAuditChain()
    registry, engine = default_engine()

    del registry

    record = chain.append(
        audit_event(
            "auto-quarantine",
            event_type=(
                ToolAuditEventType
                .AUTO_QUARANTINE_TRIGGERED
            ),
            metadata={
                "successful": True,
            },
        )
    )

    evaluations = engine.evaluate_record(
        record=record,
        chain_records=chain.records(),
    )

    violation = next(
        item.violation
        for item in evaluations
        if item.violation is not None
    )

    assert violation.violation_type is (
        ToolComplianceViolationType
        .POLICY_BYPASS
    )
    assert "lifecycle_state" in (
        violation.message
    )


def test_violation_history_suppresses_duplicate() -> None:
    chain = InMemoryToolAuditChain()
    registry, engine = default_engine()

    del registry

    record = chain.append(
        audit_event(
            "completed",
            event_type=(
                ToolAuditEventType
                .INSTALL_COMPLETED
            ),
            request_id="request-duplicate",
        )
    )

    for _ in range(2):
        engine.evaluate_record(
            record=record,
            chain_records=chain.records(),
        )

    assert engine.violations.count() == 1


def test_rule_registry_supports_lifecycle() -> None:
    registry = ToolComplianceRuleRegistry()

    rule = ToolComplianceRule(
        rule_id="forbidden-test",
        name="Forbidden test event",
        rule_type=(
            ToolComplianceRuleType
            .FORBIDDEN_EVENT
        ),
        event_types={
            ToolAuditEventType.REVOKED
        },
        violation_type=(
            ToolComplianceViolationType
            .POLICY_BYPASS
        ),
    )

    registry.register(rule)

    with pytest.raises(
        ToolComplianceRuleRegistryError,
        match="already registered",
    ):
        registry.register(rule)

    registry.disable("forbidden-test")

    assert registry.list_rules(
        enabled_only=True
    ) == []

    registry.enable("forbidden-test")

    assert len(
        registry.list_rules(
            enabled_only=True
        )
    ) == 1

    registry.unregister("forbidden-test")

    assert registry.list_rules() == []


def test_lifecycle_adapter_records_case_state() -> None:
    chain = InMemoryToolAuditChain()
    logger = ToolAuditLogger(chain=chain)

    adapter = ToolLifecycleAuditAdapter(
        logger=logger
    )

    case = SimpleNamespace(
        request=SimpleNamespace(
            request_id="request-1",
            ecosystem_id="tool.echo",
        ),
        state="QUARANTINED",
        installed_version="1.0.0",
        previous_version=None,
        quarantined_reason="Critical anomaly",
        revoked_reason=None,
        error=None,
    )

    record = adapter.record_case(
        case,
        actor="anomaly-monitor",
        message="Automatic quarantine",
    )

    assert record.event.event_type is (
        ToolAuditEventType.QUARANTINED
    )
    assert record.event.subject.tool_id == (
        "tool.echo"
    )
    assert record.event.subject.request_id == (
        "request-1"
    )
    assert record.event.severity is (
        ToolAuditSeverity.HIGH
    )
    assert record.event.metadata[
        "quarantined_reason"
    ] == "Critical anomaly"


def test_lifecycle_history_preserves_action_order() -> None:
    chain = InMemoryToolAuditChain()
    logger = ToolAuditLogger(chain=chain)

    adapter = ToolLifecycleAuditAdapter(
        logger=logger
    )

    case = SimpleNamespace(
        request=SimpleNamespace(
            request_id="request-1",
            ecosystem_id="tool.echo",
        ),
        history=[
            SimpleNamespace(
                action="REQUEST",
                state="REQUESTED",
                actor="requester",
                message="Requested",
                installation_state=(
                    "NOT_INSTALLED"
                ),
                occurred_at=utc_now(),
            ),
            SimpleNamespace(
                action="APPROVE",
                state="APPROVED",
                actor="reviewer",
                message="Approved",
                installation_state=(
                    "NOT_INSTALLED"
                ),
                occurred_at=utc_now(),
            ),
            SimpleNamespace(
                action="COMPLETE_INSTALL",
                state="INSTALLED",
                actor="installer",
                message="Installed",
                installation_state="INSTALLED",
                occurred_at=utc_now(),
            ),
        ],
    )

    records = adapter.record_history(case)

    assert [
        item.event.event_type
        for item in records
    ] == [
        ToolAuditEventType.INSTALL_REQUESTED,
        ToolAuditEventType.INSTALL_APPROVED,
        ToolAuditEventType.INSTALL_COMPLETED,
    ]

    assert chain.verify().valid is True


def test_report_builder_filters_tool_project_and_window() -> None:
    chain = InMemoryToolAuditChain()
    history = ToolComplianceViolationHistory()
    now = utc_now()

    chain.append(
        audit_event(
            "alpha-old",
            event_type=(
                ToolAuditEventType
                .TOOL_CALL_SUCCEEDED
            ),
            tool_id="tool.alpha",
            project_id="project-1",
            occurred_at=(
                now - timedelta(hours=2)
            ),
        )
    )

    chain.append(
        audit_event(
            "alpha-current",
            event_type=(
                ToolAuditEventType
                .TOOL_CALL_SUCCEEDED
            ),
            tool_id="tool.alpha",
            project_id="project-1",
            occurred_at=now,
        )
    )

    chain.append(
        audit_event(
            "beta-current",
            event_type=(
                ToolAuditEventType
                .TOOL_CALL_FAILED
            ),
            tool_id="tool.beta",
            project_id="project-2",
            occurred_at=now,
        )
    )

    report = ToolComplianceReportBuilder(
        chain=chain,
        violations=history,
    ).build(
        tool_id="tool.alpha",
        project_id="project-1",
        window_start=(
            now - timedelta(minutes=10)
        ),
        window_end=(
            now + timedelta(minutes=10)
        ),
    )

    assert report.summary.total_events == 1
    assert report.summary.total_violations == 0
    assert report.summary.chain_valid is True
    assert report.summary.status is (
        ToolComplianceStatus.COMPLIANT
    )
    assert report.records[
        0
    ].event.event_id == "alpha-current"


def test_report_marks_missing_data() -> None:
    report = ToolComplianceReportBuilder(
        chain=InMemoryToolAuditChain(),
        violations=(
            ToolComplianceViolationHistory()
        ),
    ).build(
        tool_id="tool.missing"
    )

    assert report.summary.status is (
        ToolComplianceStatus
        .INSUFFICIENT_DATA
    )
    assert report.summary.total_events == 0


def test_realtime_binding_audits_terminal_telemetry() -> None:
    stream = InMemoryToolTelemetryStream()
    chain = InMemoryToolAuditChain()
    logger = ToolAuditLogger(chain=chain)

    registry, engine = default_engine()

    del registry

    binding = ToolComplianceAuditBinding(
        stream=stream,
        chain=chain,
        telemetry_adapter=(
            ToolTelemetryAuditAdapter(
                logger=logger
            )
        ),
        rule_engine=engine,
        subscriber_id="04-compliance",
    )

    binding.attach()

    async def publish() -> None:
        await stream.publish(
            ToolTelemetryEvent(
                event_id="requested",
                event_type=(
                    ToolTelemetryEventType
                    .CALL_REQUESTED
                ),
                tool_id="tool.echo",
            )
        )

        await stream.publish(
            ToolTelemetryEvent(
                event_id="succeeded",
                event_type=(
                    ToolTelemetryEventType
                    .CALL_SUCCEEDED
                ),
                tool_id="tool.echo",
                project_id="project-1",
                agent_id="agent-1",
                successful=True,
                duration_ms=10,
            )
        )

    asyncio.run(publish())

    assert chain.count() == 1
    assert chain.verify().valid is True

    assert binding.counters() == {
        "received_events": 2,
        "audited_events": 1,
        "ignored_events": 1,
        "rule_evaluations": 2,
    }

    binding.detach()


def test_realtime_binding_rejects_duplicate_lifecycle() -> None:
    stream = InMemoryToolTelemetryStream()
    chain = InMemoryToolAuditChain()
    logger = ToolAuditLogger(chain=chain)

    binding = ToolComplianceAuditBinding(
        stream=stream,
        chain=chain,
        telemetry_adapter=(
            ToolTelemetryAuditAdapter(
                logger=logger
            )
        ),
    )

    binding.attach()

    with pytest.raises(
        ToolComplianceAuditBindingError,
        match="already attached",
    ):
        binding.attach()

    binding.detach()

    with pytest.raises(
        ToolComplianceAuditBindingError,
        match="not attached",
    ):
        binding.detach()


def test_tool_runtime_to_compliance_audit_e2e() -> None:
    registry = ExternalToolRegistry()

    async def handler(
        call: ExternalToolCall,
    ) -> ExternalToolResult:
        return ExternalToolResult(
            call_id=call.call_id,
            tool_id=call.tool_id,
            status=ToolExecutionStatus.SUCCEEDED,
        )

    registry.register(
        descriptor=ExternalToolDescriptor(
            tool_id="tool.audit-e2e",
            name="audit_e2e",
            description="Compliance Audit E2E Tool",
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            risk=ExternalToolRisk.READ_ONLY,
        ),
        handler=handler,
    )

    stream = InMemoryToolTelemetryStream()
    collector = ToolTelemetryCollector(
        stream=stream
    )

    chain = InMemoryToolAuditChain()
    logger = ToolAuditLogger(chain=chain)

    rule_registry, rule_engine = (
        default_engine()
    )

    del rule_registry

    binding = ToolComplianceAuditBinding(
        stream=stream,
        chain=chain,
        telemetry_adapter=(
            ToolTelemetryAuditAdapter(
                logger=logger
            )
        ),
        rule_engine=rule_engine,
        subscriber_id="04-compliance",
    )
    binding.attach()

    runtime = ToolCallRuntime(
        registry=registry,
        telemetry_collector=collector,
    )

    record = asyncio.run(
        runtime.execute_one(
            NormalizedToolCall(
                call_id="audit-call-1",
                tool_name="audit_e2e",
                arguments={},
            ),
            project_id="project-audit",
            run_id="run-audit",
            task_id="task-audit",
            agent_name="agent-audit",
        )
    )

    assert record.successful is True
    assert chain.count() == 1
    assert chain.verify().valid is True

    audit_record = chain.latest()

    assert audit_record is not None
    assert audit_record.event.event_type is (
        ToolAuditEventType
        .TOOL_CALL_SUCCEEDED
    )
    assert audit_record.event.subject.tool_id == (
        "tool.audit-e2e"
    )
    assert audit_record.event.subject.project_id == (
        "project-audit"
    )
    assert audit_record.event.subject.agent_id == (
        "agent-audit"
    )
    assert audit_record.event.subject.run_id == (
        "run-audit"
    )
    assert audit_record.event.subject.task_id == (
        "task-audit"
    )

    report = ToolComplianceReportBuilder(
        chain=chain,
        violations=rule_engine.violations,
    ).build(
        tool_id="tool.audit-e2e",
        project_id="project-audit",
        agent_id="agent-audit",
    )

    assert report.summary.total_events == 1
    assert report.summary.chain_valid is True
    assert report.summary.status is (
        ToolComplianceStatus.COMPLIANT
    )

    binding.detach()


def test_actual_lifecycle_history_compliance_e2e() -> None:
    import inspect
    import runpy

    namespace = runpy.run_path(
        "tests/unit/"
        "test_tool_installation_lifecycle.py"
    )

    setup_orchestrator = namespace[
        "setup_orchestrator"
    ]
    request_install = namespace[
        "request_install"
    ]

    (
        ecosystem,
        lifecycle,
        backend,
        evaluator,
        orchestrator,
    ) = setup_orchestrator()

    del ecosystem, backend, evaluator, orchestrator

    request_id = "request-compliance-e2e"

    signature = inspect.signature(
        request_install
    )

    candidates = {
        "lifecycle": lifecycle,
        "request_id": request_id,
        "require_approval": True,
    }

    kwargs = {
        name: value
        for name, value in candidates.items()
        if name in signature.parameters
    }

    request_install(**kwargs)

    approve = lifecycle.approve
    approve_signature = inspect.signature(
        approve
    )

    approve_candidates = {
        "request_id": request_id,
        "actor": "reviewer",
        "approver": "reviewer",
        "approved_by": "reviewer",
        "decided_by": "reviewer",
        "reason": "Approved for audit E2E.",
        "message": "Approved for audit E2E.",
    }

    approve_kwargs = {
        name: value
        for name, value
        in approve_candidates.items()
        if name in approve_signature.parameters
    }

    approve(**approve_kwargs)

    case = lifecycle.get(request_id)

    chain = InMemoryToolAuditChain()
    logger = ToolAuditLogger(chain=chain)
    adapter = ToolLifecycleAuditAdapter(
        logger=logger
    )

    records = adapter.record_history(case)

    rule_registry, rule_engine = (
        default_engine()
    )

    del rule_registry

    service = ToolComplianceAuditService(
        chain=chain,
        rule_engine=rule_engine,
    )

    evaluations = service.evaluate_records(
        records
    )

    assert records
    assert chain.verify().valid is True

    event_types = [
        record.event.event_type
        for record in records
    ]

    assert (
        ToolAuditEventType.INSTALL_REQUESTED
        in event_types
    )
    assert (
        ToolAuditEventType.INSTALL_APPROVED
        in event_types
    )

    # 설치 완료 전 상태이므로 승인 없는 설치 위반이 없어야 합니다.
    assert all(
        (
            evaluation.violation is None
            or evaluation.violation
            .violation_type
            is not (
                ToolComplianceViolationType
                .UNAPPROVED_INSTALLATION
            )
        )
        for evaluation in evaluations
    )

    report = ToolComplianceReportBuilder(
        chain=chain,
        violations=rule_engine.violations,
    ).build(
        tool_id=case.request.ecosystem_id
    )

    assert report.summary.chain_valid is True
    assert report.summary.total_events >= 2
