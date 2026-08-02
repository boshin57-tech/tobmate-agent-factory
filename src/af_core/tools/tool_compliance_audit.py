from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
import json
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ToolAuditEventType(StrEnum):
    TOOL_REGISTERED = "TOOL_REGISTERED"
    TOOL_UPDATED = "TOOL_UPDATED"
    TOOL_REMOVED = "TOOL_REMOVED"

    INSTALL_REQUESTED = "INSTALL_REQUESTED"
    INSTALL_APPROVED = "INSTALL_APPROVED"
    INSTALL_REJECTED = "INSTALL_REJECTED"
    INSTALL_STARTED = "INSTALL_STARTED"
    INSTALL_COMPLETED = "INSTALL_COMPLETED"
    INSTALL_FAILED = "INSTALL_FAILED"

    ROLLBACK_STARTED = "ROLLBACK_STARTED"
    ROLLBACK_COMPLETED = "ROLLBACK_COMPLETED"
    ROLLBACK_FAILED = "ROLLBACK_FAILED"

    QUARANTINED = "QUARANTINED"
    QUARANTINE_RELEASED = "QUARANTINE_RELEASED"
    REVOKED = "REVOKED"

    TOOL_CALL_SUCCEEDED = "TOOL_CALL_SUCCEEDED"
    TOOL_CALL_FAILED = "TOOL_CALL_FAILED"
    TOOL_CALL_BLOCKED = "TOOL_CALL_BLOCKED"
    TOOL_CALL_TIMED_OUT = "TOOL_CALL_TIMED_OUT"

    SLA_WARNING = "SLA_WARNING"
    SLA_BREACHED = "SLA_BREACHED"

    ANOMALY_DETECTED = "ANOMALY_DETECTED"
    AUTO_QUARANTINE_TRIGGERED = (
        "AUTO_QUARANTINE_TRIGGERED"
    )

    POLICY_VIOLATION = "POLICY_VIOLATION"
    AUDIT_VERIFIED = "AUDIT_VERIFIED"


class ToolAuditSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ToolComplianceStatus(StrEnum):
    COMPLIANT = "COMPLIANT"
    WARNING = "WARNING"
    NON_COMPLIANT = "NON_COMPLIANT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ToolAuditSource(StrEnum):
    ECOSYSTEM = "ECOSYSTEM"
    INSTALLATION_LIFECYCLE = (
        "INSTALLATION_LIFECYCLE"
    )
    TOOL_RUNTIME = "TOOL_RUNTIME"
    TELEMETRY = "TELEMETRY"
    SLA_MONITOR = "SLA_MONITOR"
    ANOMALY_MONITOR = "ANOMALY_MONITOR"
    COMPLIANCE_ENGINE = "COMPLIANCE_ENGINE"


class ToolAuditSubject(BaseModel):
    tool_id: str | None = None
    project_id: str | None = None
    agent_id: str | None = None
    request_id: str | None = None
    run_id: str | None = None
    task_id: str | None = None


class ToolAuditEvent(BaseModel):
    event_id: str
    event_type: ToolAuditEventType
    source: ToolAuditSource
    severity: ToolAuditSeverity

    subject: ToolAuditSubject = Field(
        default_factory=ToolAuditSubject
    )

    actor: str | None = None
    message: str = ""

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )

    occurred_at: datetime = Field(
        default_factory=utc_now
    )


class ToolAuditRecord(BaseModel):
    sequence: int = Field(ge=1)
    event: ToolAuditEvent

    previous_hash: str
    record_hash: str

    recorded_at: datetime = Field(
        default_factory=utc_now
    )


class ToolAuditChainVerification(BaseModel):
    valid: bool
    record_count: int = Field(ge=0)

    first_invalid_sequence: int | None = None
    expected_hash: str | None = None
    actual_hash: str | None = None
    error: str | None = None

    verified_at: datetime = Field(
        default_factory=utc_now
    )


class ToolComplianceViolationType(StrEnum):
    UNAPPROVED_INSTALLATION = (
        "UNAPPROVED_INSTALLATION"
    )
    INVALID_MANIFEST_INTEGRITY = (
        "INVALID_MANIFEST_INTEGRITY"
    )
    TRUST_LEVEL_VIOLATION = (
        "TRUST_LEVEL_VIOLATION"
    )
    POLICY_BYPASS = "POLICY_BYPASS"
    QUARANTINED_TOOL_EXECUTION = (
        "QUARANTINED_TOOL_EXECUTION"
    )
    REVOKED_TOOL_EXECUTION = (
        "REVOKED_TOOL_EXECUTION"
    )
    SLA_BREACH = "SLA_BREACH"
    CRITICAL_ANOMALY = "CRITICAL_ANOMALY"
    MISSING_AUDIT_TRAIL = "MISSING_AUDIT_TRAIL"
    CHAIN_INTEGRITY_FAILURE = (
        "CHAIN_INTEGRITY_FAILURE"
    )


class ToolComplianceViolation(BaseModel):
    violation_id: str
    violation_type: ToolComplianceViolationType

    severity: ToolAuditSeverity
    status: ToolComplianceStatus

    subject: ToolAuditSubject = Field(
        default_factory=ToolAuditSubject
    )

    rule_id: str
    message: str

    evidence_event_ids: list[str] = Field(
        default_factory=list
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict
    )

    detected_at: datetime = Field(
        default_factory=utc_now
    )


class ToolComplianceSummary(BaseModel):
    status: ToolComplianceStatus

    total_events: int = Field(ge=0)
    total_violations: int = Field(ge=0)

    warning_count: int = Field(ge=0)
    high_count: int = Field(ge=0)
    critical_count: int = Field(ge=0)

    chain_valid: bool


class ToolComplianceAuditReport(BaseModel):
    summary: ToolComplianceSummary

    records: list[ToolAuditRecord] = Field(
        default_factory=list
    )
    violations: list[
        ToolComplianceViolation
    ] = Field(default_factory=list)

    generated_at: datetime = Field(
        default_factory=utc_now
    )
    window_start: datetime | None = None
    window_end: datetime | None = None


class ToolAuditChainError(RuntimeError):
    """Raised for invalid audit-chain operations."""


class InMemoryToolAuditChain:
    GENESIS_HASH = "0" * 64

    def __init__(
        self,
        *,
        maximum_records: int | None = None,
    ) -> None:
        if (
            maximum_records is not None
            and maximum_records <= 0
        ):
            raise ValueError(
                "maximum_records must be positive."
            )

        self.maximum_records = maximum_records
        self._records: list[
            ToolAuditRecord
        ] = []

    def append(
        self,
        event: ToolAuditEvent,
    ) -> ToolAuditRecord:
        sequence = len(self._records) + 1

        previous_hash = (
            self._records[-1].record_hash
            if self._records
            else self.GENESIS_HASH
        )

        record_hash = self._record_hash(
            sequence=sequence,
            event=event,
            previous_hash=previous_hash,
        )

        record = ToolAuditRecord(
            sequence=sequence,
            event=event.model_copy(deep=True),
            previous_hash=previous_hash,
            record_hash=record_hash,
        )

        self._records.append(record)

        if (
            self.maximum_records is not None
            and len(self._records)
            > self.maximum_records
        ):
            raise ToolAuditChainError(
                "Immutable Audit Chain capacity "
                "was exceeded."
            )

        return record.model_copy(deep=True)

    def records(
        self,
    ) -> list[ToolAuditRecord]:
        return [
            record.model_copy(deep=True)
            for record in self._records
        ]

    def latest(
        self,
    ) -> ToolAuditRecord | None:
        if not self._records:
            return None

        return self._records[
            -1
        ].model_copy(deep=True)

    def count(self) -> int:
        return len(self._records)

    def verify(
        self,
    ) -> ToolAuditChainVerification:
        previous_hash = self.GENESIS_HASH

        for expected_sequence, record in enumerate(
            self._records,
            start=1,
        ):
            if record.sequence != expected_sequence:
                return ToolAuditChainVerification(
                    valid=False,
                    record_count=len(
                        self._records
                    ),
                    first_invalid_sequence=(
                        expected_sequence
                    ),
                    error=(
                        "Audit record sequence "
                        "is not contiguous."
                    ),
                )

            if record.previous_hash != previous_hash:
                return ToolAuditChainVerification(
                    valid=False,
                    record_count=len(
                        self._records
                    ),
                    first_invalid_sequence=(
                        expected_sequence
                    ),
                    expected_hash=previous_hash,
                    actual_hash=(
                        record.previous_hash
                    ),
                    error=(
                        "Audit previous hash "
                        "does not match."
                    ),
                )

            expected_hash = self._record_hash(
                sequence=record.sequence,
                event=record.event,
                previous_hash=(
                    record.previous_hash
                ),
            )

            if record.record_hash != expected_hash:
                return ToolAuditChainVerification(
                    valid=False,
                    record_count=len(
                        self._records
                    ),
                    first_invalid_sequence=(
                        expected_sequence
                    ),
                    expected_hash=expected_hash,
                    actual_hash=record.record_hash,
                    error=(
                        "Audit record hash "
                        "does not match."
                    ),
                )

            previous_hash = record.record_hash

        return ToolAuditChainVerification(
            valid=True,
            record_count=len(self._records),
        )

    def _record_hash(
        self,
        *,
        sequence: int,
        event: ToolAuditEvent,
        previous_hash: str,
    ) -> str:
        payload = {
            "sequence": sequence,
            "previous_hash": previous_hash,
            "event": self._canonicalize(
                event.model_dump(
                    mode="python"
                )
            ),
        }

        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        return sha256(encoded).hexdigest()

    def _canonicalize(
        self,
        value: Any,
    ) -> Any:
        if isinstance(value, dict):
            return {
                str(key): self._canonicalize(
                    item
                )
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple)):
            return [
                self._canonicalize(item)
                for item in value
            ]

        if isinstance(value, (set, frozenset)):
            values = [
                self._canonicalize(item)
                for item in value
            ]

            return sorted(
                values,
                key=lambda item: json.dumps(
                    item,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )

        if isinstance(value, StrEnum):
            return value.value

        if isinstance(value, datetime):
            return value.isoformat()

        return value


class ToolAuditLogger:
    def __init__(
        self,
        *,
        chain: InMemoryToolAuditChain,
        event_prefix: str = "audit-event",
    ) -> None:
        self.chain = chain
        self.event_prefix = event_prefix
        self._counter = 0

    def record(
        self,
        *,
        event_type: ToolAuditEventType,
        source: ToolAuditSource,
        severity: ToolAuditSeverity,
        subject: ToolAuditSubject | None = None,
        actor: str | None = None,
        message: str = "",
        metadata: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> ToolAuditRecord:
        self._counter += 1

        event = ToolAuditEvent(
            event_id=(
                f"{self.event_prefix}-"
                f"{self._counter}"
            ),
            event_type=event_type,
            source=source,
            severity=severity,
            subject=(
                subject
                or ToolAuditSubject()
            ),
            actor=actor,
            message=message,
            metadata=metadata or {},
            occurred_at=(
                occurred_at
                or utc_now()
            ),
        )

        return self.chain.append(event)


from .tool_telemetry import (
    ToolTelemetryEvent,
    ToolTelemetryEventType,
)


class ToolTelemetryAuditAdapter:
    def __init__(
        self,
        *,
        logger: ToolAuditLogger,
    ) -> None:
        self.logger = logger

    def record(
        self,
        event: ToolTelemetryEvent,
    ) -> ToolAuditRecord | None:
        mapping = {
            ToolTelemetryEventType.CALL_SUCCEEDED: (
                ToolAuditEventType
                .TOOL_CALL_SUCCEEDED
            ),
            ToolTelemetryEventType.CALL_FAILED: (
                ToolAuditEventType
                .TOOL_CALL_FAILED
            ),
            ToolTelemetryEventType.CALL_BLOCKED: (
                ToolAuditEventType
                .TOOL_CALL_BLOCKED
            ),
            ToolTelemetryEventType.CALL_TIMED_OUT: (
                ToolAuditEventType
                .TOOL_CALL_TIMED_OUT
            ),
        }

        audit_type = mapping.get(
            event.event_type
        )

        if audit_type is None:
            return None

        severity = {
            ToolTelemetryEventType.CALL_SUCCEEDED: (
                ToolAuditSeverity.INFO
            ),
            ToolTelemetryEventType.CALL_FAILED: (
                ToolAuditSeverity.HIGH
            ),
            ToolTelemetryEventType.CALL_BLOCKED: (
                ToolAuditSeverity.WARNING
            ),
            ToolTelemetryEventType.CALL_TIMED_OUT: (
                ToolAuditSeverity.HIGH
            ),
        }[event.event_type]

        return self.logger.record(
            event_type=audit_type,
            source=ToolAuditSource.TELEMETRY,
            severity=severity,
            subject=ToolAuditSubject(
                tool_id=event.tool_id,
                project_id=event.project_id,
                agent_id=event.agent_id,
                run_id=event.run_id,
                task_id=event.task_id,
            ),
            message=event.error_message or "",
            metadata={
                "telemetry_event_id": (
                    event.event_id
                ),
                "duration_ms": (
                    event.duration_ms
                ),
                "retry_count": (
                    event.retry_count
                ),
                "input_tokens": (
                    event.input_tokens
                ),
                "output_tokens": (
                    event.output_tokens
                ),
                "cost_usd": (
                    str(event.cost_usd)
                ),
                "successful": (
                    event.successful
                ),
            },
            occurred_at=event.occurred_at,
        )


from .tool_sla_monitor import (
    ToolSLAAlert,
    ToolSLAStatus,
)
from .tool_anomaly_detection import (
    ToolAnomalyAlert,
    ToolAnomalySeverity,
)


class ToolSLAAuditAdapter:
    def __init__(
        self,
        *,
        logger: ToolAuditLogger,
    ) -> None:
        self.logger = logger

    def record(
        self,
        alert: ToolSLAAlert,
    ) -> ToolAuditRecord:
        breached = (
            alert.current_status
            is ToolSLAStatus.BREACHED
        )

        return self.logger.record(
            event_type=(
                ToolAuditEventType.SLA_BREACHED
                if breached
                else ToolAuditEventType
                .SLA_WARNING
            ),
            source=ToolAuditSource.SLA_MONITOR,
            severity=(
                ToolAuditSeverity.HIGH
                if breached
                else ToolAuditSeverity.WARNING
            ),
            subject=ToolAuditSubject(
                tool_id=(
                    alert.evaluation.key.tool_id
                ),
                project_id=(
                    alert.evaluation
                    .key.project_id
                ),
                agent_id=(
                    alert.evaluation.key.agent_id
                ),
            ),
            message=(
                f"SLA status changed to "
                f"{alert.current_status.value}."
            ),
            metadata={
                "alert_id": alert.alert_id,
                "policy_id": (
                    alert.evaluation.policy_id
                ),
                "change_type": (
                    alert.change_type.value
                ),
                "breach_types": [
                    breach.breach_type.value
                    for breach in (
                        alert.evaluation.breaches
                    )
                ],
            },
        )


class ToolAnomalyAuditAdapter:
    def __init__(
        self,
        *,
        logger: ToolAuditLogger,
    ) -> None:
        self.logger = logger

    def record(
        self,
        alert: ToolAnomalyAlert,
    ) -> list[ToolAuditRecord]:
        evaluation = alert.evaluation

        severity_map = {
            ToolAnomalySeverity.INFO: (
                ToolAuditSeverity.INFO
            ),
            ToolAnomalySeverity.WARNING: (
                ToolAuditSeverity.WARNING
            ),
            ToolAnomalySeverity.HIGH: (
                ToolAuditSeverity.HIGH
            ),
            ToolAnomalySeverity.CRITICAL: (
                ToolAuditSeverity.CRITICAL
            ),
        }

        records = [
            self.logger.record(
                event_type=(
                    ToolAuditEventType
                    .ANOMALY_DETECTED
                ),
                source=(
                    ToolAuditSource
                    .ANOMALY_MONITOR
                ),
                severity=severity_map[
                    evaluation.severity
                ],
                subject=ToolAuditSubject(
                    tool_id=(
                        evaluation.key.tool_id
                    ),
                    project_id=(
                        evaluation.key.project_id
                    ),
                    agent_id=(
                        evaluation.key.agent_id
                    ),
                ),
                message=(
                    "Tool anomaly detected."
                ),
                metadata={
                    "alert_id": alert.alert_id,
                    "policy_id": (
                        evaluation.policy_id
                    ),
                    "severity": (
                        evaluation.severity.value
                    ),
                    "recommended_action": (
                        evaluation
                        .recommended_action.value
                    ),
                    "metrics": [
                        signal.metric.value
                        for signal in (
                            evaluation.signals
                        )
                    ],
                },
            )
        ]

        if (
            alert.quarantine_result is not None
            and alert.quarantine_result.requested
        ):
            records.append(
                self.logger.record(
                    event_type=(
                        ToolAuditEventType
                        .AUTO_QUARANTINE_TRIGGERED
                    ),
                    source=(
                        ToolAuditSource
                        .ANOMALY_MONITOR
                    ),
                    severity=(
                        ToolAuditSeverity.CRITICAL
                    ),
                    subject=ToolAuditSubject(
                        tool_id=(
                            evaluation.key.tool_id
                        ),
                        project_id=(
                            evaluation
                            .key.project_id
                        ),
                        agent_id=(
                            evaluation
                            .key.agent_id
                        ),
                        request_id=(
                            alert
                            .quarantine_result
                            .request_id
                        ),
                    ),
                    message=(
                        "Automatic Tool quarantine "
                        "was triggered."
                    ),
                    metadata={
                        "successful": (
                            alert
                            .quarantine_result
                            .successful
                        ),
                        "lifecycle_state": (
                            alert
                            .quarantine_result
                            .lifecycle_state
                        ),
                        "error": (
                            alert
                            .quarantine_result.error
                        ),
                    },
                )
            )

        return records


class ToolComplianceRuleType(StrEnum):
    EVENT_SEQUENCE = "EVENT_SEQUENCE"
    FORBIDDEN_EVENT = "FORBIDDEN_EVENT"
    REQUIRED_PREDECESSOR = "REQUIRED_PREDECESSOR"
    METADATA_REQUIREMENT = "METADATA_REQUIREMENT"
    SUBJECT_STATE = "SUBJECT_STATE"
    CHAIN_INTEGRITY = "CHAIN_INTEGRITY"


class ToolComplianceRule(BaseModel):
    rule_id: str
    name: str
    description: str = ""

    rule_type: ToolComplianceRuleType
    enabled: bool = True

    event_types: set[
        ToolAuditEventType
    ] = Field(default_factory=set)

    required_predecessors: set[
        ToolAuditEventType
    ] = Field(default_factory=set)

    forbidden_after: set[
        ToolAuditEventType
    ] = Field(default_factory=set)

    required_metadata_keys: set[str] = Field(
        default_factory=set
    )

    violation_type: ToolComplianceViolationType
    severity: ToolAuditSeverity = (
        ToolAuditSeverity.HIGH
    )

    lookback_records: int | None = Field(
        default=None,
        ge=1,
    )


class ToolComplianceRuleEvaluation(BaseModel):
    rule_id: str
    compliant: bool

    record_sequence: int | None = None
    event_id: str | None = None

    message: str = ""
    violation: ToolComplianceViolation | None = None

    evaluated_at: datetime = Field(
        default_factory=utc_now
    )


class ToolComplianceRuleRegistryError(RuntimeError):
    """Raised for invalid compliance rule operations."""


class ToolComplianceRuleRegistry:
    def __init__(self) -> None:
        self._rules: dict[
            str,
            ToolComplianceRule,
        ] = {}

    def register(
        self,
        rule: ToolComplianceRule,
    ) -> None:
        rule_id = rule.rule_id.strip()

        if not rule_id:
            raise ToolComplianceRuleRegistryError(
                "Compliance rule ID is required."
            )

        if rule_id in self._rules:
            raise ToolComplianceRuleRegistryError(
                "Compliance rule already registered: "
                f"{rule_id}"
            )

        self._rules[rule_id] = (
            rule.model_copy(deep=True)
        )

    def upsert(
        self,
        rule: ToolComplianceRule,
    ) -> None:
        rule_id = rule.rule_id.strip()

        if not rule_id:
            raise ToolComplianceRuleRegistryError(
                "Compliance rule ID is required."
            )

        self._rules[rule_id] = (
            rule.model_copy(deep=True)
        )

    def get(
        self,
        rule_id: str,
    ) -> ToolComplianceRule:
        try:
            return self._rules[
                rule_id
            ].model_copy(deep=True)
        except KeyError as exc:
            raise ToolComplianceRuleRegistryError(
                "Unknown compliance rule: "
                f"{rule_id}"
            ) from exc

    def enable(
        self,
        rule_id: str,
    ) -> None:
        rule = self._require(rule_id)
        rule.enabled = True

    def disable(
        self,
        rule_id: str,
    ) -> None:
        rule = self._require(rule_id)
        rule.enabled = False

    def unregister(
        self,
        rule_id: str,
    ) -> None:
        if rule_id not in self._rules:
            raise ToolComplianceRuleRegistryError(
                "Unknown compliance rule: "
                f"{rule_id}"
            )

        del self._rules[rule_id]

    def list_rules(
        self,
        *,
        enabled_only: bool = False,
    ) -> list[ToolComplianceRule]:
        values = []

        for rule_id in sorted(self._rules):
            rule = self._rules[rule_id]

            if enabled_only and not rule.enabled:
                continue

            values.append(
                rule.model_copy(deep=True)
            )

        return values

    def _require(
        self,
        rule_id: str,
    ) -> ToolComplianceRule:
        try:
            return self._rules[rule_id]
        except KeyError as exc:
            raise ToolComplianceRuleRegistryError(
                "Unknown compliance rule: "
                f"{rule_id}"
            ) from exc


class ToolComplianceViolationHistory:
    def __init__(
        self,
        *,
        maximum_records: int = 10000,
    ) -> None:
        if maximum_records <= 0:
            raise ValueError(
                "maximum_records must be positive."
            )

        self.maximum_records = maximum_records
        self._records: list[
            ToolComplianceViolation
        ] = []
        self._fingerprints: set[str] = set()

    def append(
        self,
        violation: ToolComplianceViolation,
        *,
        suppress_duplicate: bool = True,
    ) -> bool:
        fingerprint = self._fingerprint(
            violation
        )

        if (
            suppress_duplicate
            and fingerprint in self._fingerprints
        ):
            return False

        self._records.append(
            violation.model_copy(deep=True)
        )
        self._fingerprints.add(fingerprint)

        overflow = (
            len(self._records)
            - self.maximum_records
        )

        if overflow > 0:
            removed = self._records[:overflow]
            del self._records[:overflow]

            self._fingerprints = {
                self._fingerprint(item)
                for item in self._records
            }

            del removed

        return True

    def history(
        self,
        *,
        tool_id: str | None = None,
        project_id: str | None = None,
        agent_id: str | None = None,
        violation_type: (
            ToolComplianceViolationType
            | None
        ) = None,
        minimum_severity: (
            ToolAuditSeverity | None
        ) = None,
    ) -> list[ToolComplianceViolation]:
        severity_order = {
            ToolAuditSeverity.INFO: 0,
            ToolAuditSeverity.WARNING: 1,
            ToolAuditSeverity.HIGH: 2,
            ToolAuditSeverity.CRITICAL: 3,
        }

        results = []

        for violation in self._records:
            subject = violation.subject

            if (
                tool_id is not None
                and subject.tool_id != tool_id
            ):
                continue

            if (
                project_id is not None
                and subject.project_id
                != project_id
            ):
                continue

            if (
                agent_id is not None
                and subject.agent_id
                != agent_id
            ):
                continue

            if (
                violation_type is not None
                and violation.violation_type
                is not violation_type
            ):
                continue

            if (
                minimum_severity is not None
                and severity_order[
                    violation.severity
                ]
                < severity_order[
                    minimum_severity
                ]
            ):
                continue

            results.append(
                violation.model_copy(
                    deep=True
                )
            )

        return results

    def count(self) -> int:
        return len(self._records)

    def clear(self) -> None:
        self._records.clear()
        self._fingerprints.clear()

    def _fingerprint(
        self,
        violation: ToolComplianceViolation,
    ) -> str:
        payload = {
            "rule_id": violation.rule_id,
            "violation_type": (
                violation.violation_type.value
            ),
            "tool_id": violation.subject.tool_id,
            "project_id": (
                violation.subject.project_id
            ),
            "agent_id": (
                violation.subject.agent_id
            ),
            "request_id": (
                violation.subject.request_id
            ),
            "evidence_event_ids": sorted(
                violation.evidence_event_ids
            ),
        }

        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        return sha256(encoded).hexdigest()


class ToolComplianceRuleEngine:
    def __init__(
        self,
        *,
        rules: ToolComplianceRuleRegistry,
        violations: (
            ToolComplianceViolationHistory
            | None
        ) = None,
    ) -> None:
        self.rules = rules
        self.violations = (
            violations
            or ToolComplianceViolationHistory()
        )
        self._violation_counter = 0

    def evaluate_record(
        self,
        *,
        record: ToolAuditRecord,
        chain_records: list[
            ToolAuditRecord
        ],
    ) -> list[ToolComplianceRuleEvaluation]:
        evaluations = []

        for rule in self.rules.list_rules(
            enabled_only=True
        ):
            if (
                rule.event_types
                and record.event.event_type
                not in rule.event_types
            ):
                continue

            evaluation = self._evaluate_rule(
                rule=rule,
                record=record,
                chain_records=chain_records,
            )

            evaluations.append(evaluation)

            if evaluation.violation is not None:
                self.violations.append(
                    evaluation.violation
                )

        return evaluations

    def _evaluate_rule(
        self,
        *,
        rule: ToolComplianceRule,
        record: ToolAuditRecord,
        chain_records: list[
            ToolAuditRecord
        ],
    ) -> ToolComplianceRuleEvaluation:
        if rule.rule_type is (
            ToolComplianceRuleType
            .FORBIDDEN_EVENT
        ):
            return self._violation_evaluation(
                rule=rule,
                record=record,
                message=(
                    f"Forbidden audit event "
                    f"{record.event.event_type.value} "
                    "was recorded."
                ),
            )

        if rule.rule_type is (
            ToolComplianceRuleType
            .REQUIRED_PREDECESSOR
        ):
            predecessors = self._predecessors(
                record=record,
                chain_records=chain_records,
                lookback=rule.lookback_records,
            )

            predecessor_types = {
                item.event.event_type
                for item in predecessors
                if self._same_subject(
                    item.event.subject,
                    record.event.subject,
                )
            }

            missing = (
                rule.required_predecessors
                - predecessor_types
            )

            if missing:
                return self._violation_evaluation(
                    rule=rule,
                    record=record,
                    message=(
                        "Required predecessor events "
                        "are missing: "
                        + ", ".join(
                            sorted(
                                item.value
                                for item in missing
                            )
                        )
                    ),
                )

        elif rule.rule_type is (
            ToolComplianceRuleType
            .METADATA_REQUIREMENT
        ):
            missing_keys = (
                rule.required_metadata_keys
                - set(record.event.metadata)
            )

            if missing_keys:
                return self._violation_evaluation(
                    rule=rule,
                    record=record,
                    message=(
                        "Required audit metadata is "
                        "missing: "
                        + ", ".join(
                            sorted(missing_keys)
                        )
                    ),
                )

        elif rule.rule_type is (
            ToolComplianceRuleType
            .EVENT_SEQUENCE
        ):
            predecessors = self._predecessors(
                record=record,
                chain_records=chain_records,
                lookback=rule.lookback_records,
            )

            forbidden_seen = {
                item.event.event_type
                for item in predecessors
                if self._same_subject(
                    item.event.subject,
                    record.event.subject,
                )
            } & rule.forbidden_after

            if forbidden_seen:
                return self._violation_evaluation(
                    rule=rule,
                    record=record,
                    message=(
                        "Event occurred after forbidden "
                        "predecessor state: "
                        + ", ".join(
                            sorted(
                                item.value
                                for item
                                in forbidden_seen
                            )
                        )
                    ),
                )

        return ToolComplianceRuleEvaluation(
            rule_id=rule.rule_id,
            compliant=True,
            record_sequence=record.sequence,
            event_id=record.event.event_id,
            message="Compliance rule passed.",
        )

    def _violation_evaluation(
        self,
        *,
        rule: ToolComplianceRule,
        record: ToolAuditRecord,
        message: str,
    ) -> ToolComplianceRuleEvaluation:
        self._violation_counter += 1

        violation = ToolComplianceViolation(
            violation_id=(
                f"compliance-violation-"
                f"{self._violation_counter}"
            ),
            violation_type=(
                rule.violation_type
            ),
            severity=rule.severity,
            status=(
                ToolComplianceStatus
                .NON_COMPLIANT
                if rule.severity
                in {
                    ToolAuditSeverity.HIGH,
                    ToolAuditSeverity.CRITICAL,
                }
                else ToolComplianceStatus.WARNING
            ),
            subject=(
                record.event.subject.model_copy(
                    deep=True
                )
            ),
            rule_id=rule.rule_id,
            message=message,
            evidence_event_ids=[
                record.event.event_id
            ],
            metadata={
                "record_sequence": (
                    record.sequence
                ),
                "event_type": (
                    record.event
                    .event_type.value
                ),
            },
        )

        return ToolComplianceRuleEvaluation(
            rule_id=rule.rule_id,
            compliant=False,
            record_sequence=record.sequence,
            event_id=record.event.event_id,
            message=message,
            violation=violation,
        )

    def _predecessors(
        self,
        *,
        record: ToolAuditRecord,
        chain_records: list[
            ToolAuditRecord
        ],
        lookback: int | None,
    ) -> list[ToolAuditRecord]:
        values = [
            item
            for item in chain_records
            if item.sequence < record.sequence
        ]

        if lookback is not None:
            values = values[-lookback:]

        return values

    def _same_subject(
        self,
        left: ToolAuditSubject,
        right: ToolAuditSubject,
    ) -> bool:
        if (
            left.request_id is not None
            or right.request_id is not None
        ):
            return (
                left.request_id
                == right.request_id
            )

        if (
            left.tool_id is not None
            or right.tool_id is not None
        ):
            return (
                left.tool_id == right.tool_id
                and left.project_id
                == right.project_id
                and left.agent_id
                == right.agent_id
            )

        return True


def default_tool_compliance_rules(
) -> list[ToolComplianceRule]:
    return [
        ToolComplianceRule(
            rule_id=(
                "install-completion-requires-approval"
            ),
            name=(
                "Install completion requires approval"
            ),
            rule_type=(
                ToolComplianceRuleType
                .REQUIRED_PREDECESSOR
            ),
            event_types={
                ToolAuditEventType
                .INSTALL_COMPLETED
            },
            required_predecessors={
                ToolAuditEventType
                .INSTALL_APPROVED
            },
            violation_type=(
                ToolComplianceViolationType
                .UNAPPROVED_INSTALLATION
            ),
            severity=ToolAuditSeverity.CRITICAL,
        ),
        ToolComplianceRule(
            rule_id=(
                "quarantined-tool-cannot-execute"
            ),
            name=(
                "Quarantined Tool cannot execute"
            ),
            rule_type=(
                ToolComplianceRuleType
                .EVENT_SEQUENCE
            ),
            event_types={
                ToolAuditEventType
                .TOOL_CALL_SUCCEEDED,
                ToolAuditEventType
                .TOOL_CALL_FAILED,
                ToolAuditEventType
                .TOOL_CALL_TIMED_OUT,
            },
            forbidden_after={
                ToolAuditEventType.QUARANTINED
            },
            violation_type=(
                ToolComplianceViolationType
                .QUARANTINED_TOOL_EXECUTION
            ),
            severity=ToolAuditSeverity.CRITICAL,
        ),
        ToolComplianceRule(
            rule_id="revoked-tool-cannot-execute",
            name="Revoked Tool cannot execute",
            rule_type=(
                ToolComplianceRuleType
                .EVENT_SEQUENCE
            ),
            event_types={
                ToolAuditEventType
                .TOOL_CALL_SUCCEEDED,
                ToolAuditEventType
                .TOOL_CALL_FAILED,
                ToolAuditEventType
                .TOOL_CALL_TIMED_OUT,
            },
            forbidden_after={
                ToolAuditEventType.REVOKED
            },
            violation_type=(
                ToolComplianceViolationType
                .REVOKED_TOOL_EXECUTION
            ),
            severity=ToolAuditSeverity.CRITICAL,
        ),
        ToolComplianceRule(
            rule_id=(
                "auto-quarantine-requires-result"
            ),
            name=(
                "Auto quarantine requires result metadata"
            ),
            rule_type=(
                ToolComplianceRuleType
                .METADATA_REQUIREMENT
            ),
            event_types={
                ToolAuditEventType
                .AUTO_QUARANTINE_TRIGGERED
            },
            required_metadata_keys={
                "successful",
                "lifecycle_state",
            },
            violation_type=(
                ToolComplianceViolationType
                .POLICY_BYPASS
            ),
            severity=ToolAuditSeverity.HIGH,
        ),
    ]


class ToolLifecycleAuditAdapter:
    def __init__(
        self,
        *,
        logger: ToolAuditLogger,
    ) -> None:
        self.logger = logger

    def record_case(
        self,
        case,
        *,
        actor: str | None = None,
        message: str = "",
    ) -> ToolAuditRecord:
        state = self._normalize(
            getattr(case, "state", None)
        )

        event_type = self._state_event_type(
            state
        )

        request = getattr(case, "request", None)

        tool_id = getattr(
            request,
            "ecosystem_id",
            getattr(request, "tool_id", None),
        )
        request_id = getattr(
            request,
            "request_id",
            getattr(case, "request_id", None),
        )

        return self.logger.record(
            event_type=event_type,
            source=(
                ToolAuditSource
                .INSTALLATION_LIFECYCLE
            ),
            severity=self._severity(event_type),
            subject=ToolAuditSubject(
                tool_id=tool_id,
                request_id=request_id,
            ),
            actor=actor,
            message=message,
            metadata={
                "lifecycle_state": state,
                "installed_version": getattr(
                    case,
                    "installed_version",
                    None,
                ),
                "previous_version": getattr(
                    case,
                    "previous_version",
                    None,
                ),
                "quarantined_reason": getattr(
                    case,
                    "quarantined_reason",
                    None,
                ),
                "revoked_reason": getattr(
                    case,
                    "revoked_reason",
                    None,
                ),
                "error": getattr(
                    case,
                    "error",
                    None,
                ),
            },
        )

    def record_history(
        self,
        case,
    ) -> list[ToolAuditRecord]:
        records = []

        history = self._case_history(case)

        for item in history:
            action = self._normalize(
                getattr(item, "action", None)
            )
            state = self._normalize(
                getattr(item, "state", None)
            )

            event_type = self._action_event_type(
                action=action,
                state=state,
            )

            request = getattr(
                case,
                "request",
                None,
            )

            records.append(
                self.logger.record(
                    event_type=event_type,
                    source=(
                        ToolAuditSource
                        .INSTALLATION_LIFECYCLE
                    ),
                    severity=self._severity(
                        event_type
                    ),
                    subject=ToolAuditSubject(
                        tool_id=getattr(
                            request,
                            "ecosystem_id",
                            None,
                        ),
                        request_id=getattr(
                            request,
                            "request_id",
                            None,
                        ),
                    ),
                    actor=getattr(
                        item,
                        "actor",
                        None,
                    ),
                    message=getattr(
                        item,
                        "message",
                        "",
                    ),
                    metadata={
                        "action": action,
                        "state": state,
                        "installation_state": (
                            self._normalize(
                                getattr(
                                    item,
                                    "installation_state",
                                    None,
                                )
                            )
                        ),
                    },
                    occurred_at=getattr(
                        item,
                        "occurred_at",
                        None,
                    ),
                )
            )

        return records

    def _case_history(
        self,
        case,
    ) -> list:
        for attribute in (
            "history",
            "records",
            "audit_records",
            "lifecycle_records",
            "transitions",
            "events",
        ):
            value = getattr(
                case,
                attribute,
                None,
            )

            if value is None:
                continue

            if isinstance(
                value,
                (list, tuple),
            ):
                return list(value)

        if isinstance(case, dict):
            for key in (
                "history",
                "records",
                "audit_records",
                "lifecycle_records",
                "transitions",
                "events",
            ):
                value = case.get(key)

                if isinstance(
                    value,
                    (list, tuple),
                ):
                    return list(value)

        return []

    def _state_event_type(
        self,
        state: str,
    ) -> ToolAuditEventType:
        mapping = {
            "REQUESTED": (
                ToolAuditEventType
                .INSTALL_REQUESTED
            ),
            "PENDING_APPROVAL": (
                ToolAuditEventType
                .INSTALL_REQUESTED
            ),
            "PENDING": (
                ToolAuditEventType
                .INSTALL_REQUESTED
            ),
            "APPROVED": (
                ToolAuditEventType
                .INSTALL_APPROVED
            ),
            "REJECTED": (
                ToolAuditEventType
                .INSTALL_REJECTED
            ),
            "INSTALLING": (
                ToolAuditEventType
                .INSTALL_STARTED
            ),
            "INSTALLED": (
                ToolAuditEventType
                .INSTALL_COMPLETED
            ),
            "INSTALL_FAILED": (
                ToolAuditEventType
                .INSTALL_FAILED
            ),
            "ROLLING_BACK": (
                ToolAuditEventType
                .ROLLBACK_STARTED
            ),
            "ROLLED_BACK": (
                ToolAuditEventType
                .ROLLBACK_COMPLETED
            ),
            "ROLLBACK_FAILED": (
                ToolAuditEventType
                .ROLLBACK_FAILED
            ),
            "QUARANTINED": (
                ToolAuditEventType.QUARANTINED
            ),
            "REVOKED": (
                ToolAuditEventType.REVOKED
            ),
            "REMOVED": (
                ToolAuditEventType.TOOL_REMOVED
            ),
        }

        return mapping.get(
            state,
            ToolAuditEventType.TOOL_UPDATED,
        )

    def _action_event_type(
        self,
        *,
        action: str,
        state: str,
    ) -> ToolAuditEventType:
        mapping = {
            "REQUEST": (
                ToolAuditEventType
                .INSTALL_REQUESTED
            ),
            "REQUEST_INSTALL": (
                ToolAuditEventType
                .INSTALL_REQUESTED
            ),
            "REQUEST_INSTALLATION": (
                ToolAuditEventType
                .INSTALL_REQUESTED
            ),
            "SUBMIT": (
                ToolAuditEventType
                .INSTALL_REQUESTED
            ),
            "SUBMIT_REQUEST": (
                ToolAuditEventType
                .INSTALL_REQUESTED
            ),
            "APPROVE": (
                ToolAuditEventType
                .INSTALL_APPROVED
            ),
            "REJECT": (
                ToolAuditEventType
                .INSTALL_REJECTED
            ),
            "START_INSTALL": (
                ToolAuditEventType
                .INSTALL_STARTED
            ),
            "COMPLETE_INSTALL": (
                ToolAuditEventType
                .INSTALL_COMPLETED
            ),
            "FAIL_INSTALL": (
                ToolAuditEventType
                .INSTALL_FAILED
            ),
            "START_ROLLBACK": (
                ToolAuditEventType
                .ROLLBACK_STARTED
            ),
            "COMPLETE_ROLLBACK": (
                ToolAuditEventType
                .ROLLBACK_COMPLETED
            ),
            "FAIL_ROLLBACK": (
                ToolAuditEventType
                .ROLLBACK_FAILED
            ),
            "QUARANTINE": (
                ToolAuditEventType.QUARANTINED
            ),
            "RELEASE_QUARANTINE": (
                ToolAuditEventType
                .QUARANTINE_RELEASED
            ),
            "REVOKE": (
                ToolAuditEventType.REVOKED
            ),
            "REMOVE": (
                ToolAuditEventType.TOOL_REMOVED
            ),
        }

        return mapping.get(
            action,
            self._state_event_type(state),
        )

    def _severity(
        self,
        event_type: ToolAuditEventType,
    ) -> ToolAuditSeverity:
        if event_type in {
            ToolAuditEventType.REVOKED,
            ToolAuditEventType
            .ROLLBACK_FAILED,
            ToolAuditEventType
            .INSTALL_FAILED,
        }:
            return ToolAuditSeverity.CRITICAL

        if event_type in {
            ToolAuditEventType.QUARANTINED,
            ToolAuditEventType
            .INSTALL_REJECTED,
        }:
            return ToolAuditSeverity.HIGH

        return ToolAuditSeverity.INFO

    def _normalize(
        self,
        value,
    ) -> str:
        if value is None:
            return ""

        return str(
            getattr(value, "value", value)
        ).upper()


class ToolComplianceAuditBindingError(RuntimeError):
    """Raised for invalid Audit Stream bindings."""


class ToolComplianceAuditBinding:
    def __init__(
        self,
        *,
        stream,
        chain: InMemoryToolAuditChain,
        telemetry_adapter: (
            ToolTelemetryAuditAdapter
        ),
        rule_engine: (
            ToolComplianceRuleEngine
            | None
        ) = None,
        subscriber_id: str = (
            "tool-compliance-audit"
        ),
    ) -> None:
        subscriber_id = subscriber_id.strip()

        if not subscriber_id:
            raise ValueError(
                "subscriber_id is required."
            )

        self.stream = stream
        self.chain = chain
        self.telemetry_adapter = (
            telemetry_adapter
        )
        self.rule_engine = rule_engine
        self.subscriber_id = subscriber_id

        self._attached = False
        self._received_events = 0
        self._audited_events = 0
        self._ignored_events = 0
        self._rule_evaluations = 0

    @property
    def attached(self) -> bool:
        return self._attached

    def attach(self) -> None:
        if self._attached:
            raise ToolComplianceAuditBindingError(
                "Compliance Audit binding is "
                "already attached."
            )

        try:
            self.stream.subscribe(
                self.subscriber_id,
                self._on_event,
            )
        except Exception as exc:
            raise ToolComplianceAuditBindingError(
                "Unable to attach Compliance "
                f"Audit binding: {exc}"
            ) from exc

        self._attached = True

    def detach(self) -> None:
        if not self._attached:
            raise ToolComplianceAuditBindingError(
                "Compliance Audit binding is "
                "not attached."
            )

        try:
            self.stream.unsubscribe(
                self.subscriber_id
            )
        except Exception as exc:
            raise ToolComplianceAuditBindingError(
                "Unable to detach Compliance "
                f"Audit binding: {exc}"
            ) from exc

        self._attached = False

    def _on_event(
        self,
        event: ToolTelemetryEvent,
    ) -> None:
        self._received_events += 1

        record = self.telemetry_adapter.record(
            event
        )

        if record is None:
            self._ignored_events += 1
            return

        self._audited_events += 1

        if self.rule_engine is not None:
            evaluations = (
                self.rule_engine
                .evaluate_record(
                    record=record,
                    chain_records=(
                        self.chain.records()
                    ),
                )
            )

            self._rule_evaluations += len(
                evaluations
            )

    def counters(self) -> dict[str, int]:
        return {
            "received_events": (
                self._received_events
            ),
            "audited_events": (
                self._audited_events
            ),
            "ignored_events": (
                self._ignored_events
            ),
            "rule_evaluations": (
                self._rule_evaluations
            ),
        }

    def __enter__(
        self,
    ) -> ToolComplianceAuditBinding:
        self.attach()
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ) -> None:
        del exc_type, exc, traceback

        if self._attached:
            self.detach()


class ToolComplianceAuditService:
    def __init__(
        self,
        *,
        chain: InMemoryToolAuditChain,
        rule_engine: ToolComplianceRuleEngine,
    ) -> None:
        self.chain = chain
        self.rule_engine = rule_engine

    def evaluate_record(
        self,
        record: ToolAuditRecord,
    ) -> list[ToolComplianceRuleEvaluation]:
        return self.rule_engine.evaluate_record(
            record=record,
            chain_records=self.chain.records(),
        )

    def evaluate_records(
        self,
        records: list[ToolAuditRecord],
    ) -> list[ToolComplianceRuleEvaluation]:
        evaluations = []

        for record in records:
            evaluations.extend(
                self.evaluate_record(record)
            )

        return evaluations

    def verify_chain(
        self,
    ) -> ToolAuditChainVerification:
        return self.chain.verify()


class ToolComplianceReportBuilder:
    def __init__(
        self,
        *,
        chain: InMemoryToolAuditChain,
        violations: (
            ToolComplianceViolationHistory
        ),
    ) -> None:
        self.chain = chain
        self.violations = violations

    def build(
        self,
        *,
        tool_id: str | None = None,
        project_id: str | None = None,
        agent_id: str | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        minimum_severity: (
            ToolAuditSeverity | None
        ) = None,
    ) -> ToolComplianceAuditReport:
        records = self._records(
            tool_id=tool_id,
            project_id=project_id,
            agent_id=agent_id,
            window_start=window_start,
            window_end=window_end,
        )

        violations = self.violations.history(
            tool_id=tool_id,
            project_id=project_id,
            agent_id=agent_id,
            minimum_severity=minimum_severity,
        )

        violations = [
            violation
            for violation in violations
            if self._within_window(
                violation.detected_at,
                window_start=window_start,
                window_end=window_end,
            )
        ]

        chain_verification = self.chain.verify()

        warning_count = sum(
            1
            for violation in violations
            if violation.severity is (
                ToolAuditSeverity.WARNING
            )
        )
        high_count = sum(
            1
            for violation in violations
            if violation.severity is (
                ToolAuditSeverity.HIGH
            )
        )
        critical_count = sum(
            1
            for violation in violations
            if violation.severity is (
                ToolAuditSeverity.CRITICAL
            )
        )

        status = self._status(
            record_count=len(records),
            warning_count=warning_count,
            high_count=high_count,
            critical_count=critical_count,
            chain_valid=chain_verification.valid,
        )

        return ToolComplianceAuditReport(
            summary=ToolComplianceSummary(
                status=status,
                total_events=len(records),
                total_violations=len(
                    violations
                ),
                warning_count=warning_count,
                high_count=high_count,
                critical_count=critical_count,
                chain_valid=(
                    chain_verification.valid
                ),
            ),
            records=records,
            violations=violations,
            window_start=window_start,
            window_end=window_end,
        )

    def _records(
        self,
        *,
        tool_id: str | None,
        project_id: str | None,
        agent_id: str | None,
        window_start: datetime | None,
        window_end: datetime | None,
    ) -> list[ToolAuditRecord]:
        values = []

        for record in self.chain.records():
            subject = record.event.subject

            if (
                tool_id is not None
                and subject.tool_id != tool_id
            ):
                continue

            if (
                project_id is not None
                and subject.project_id
                != project_id
            ):
                continue

            if (
                agent_id is not None
                and subject.agent_id
                != agent_id
            ):
                continue

            if not self._within_window(
                record.event.occurred_at,
                window_start=window_start,
                window_end=window_end,
            ):
                continue

            values.append(record)

        return values

    def _within_window(
        self,
        value: datetime,
        *,
        window_start: datetime | None,
        window_end: datetime | None,
    ) -> bool:
        if (
            window_start is not None
            and value < window_start
        ):
            return False

        if (
            window_end is not None
            and value > window_end
        ):
            return False

        return True

    def _status(
        self,
        *,
        record_count: int,
        warning_count: int,
        high_count: int,
        critical_count: int,
        chain_valid: bool,
    ) -> ToolComplianceStatus:
        if not chain_valid:
            return (
                ToolComplianceStatus
                .NON_COMPLIANT
            )

        if critical_count or high_count:
            return (
                ToolComplianceStatus
                .NON_COMPLIANT
            )

        if warning_count:
            return ToolComplianceStatus.WARNING

        if record_count == 0:
            return (
                ToolComplianceStatus
                .INSUFFICIENT_DATA
            )

        return ToolComplianceStatus.COMPLIANT
