from __future__ import annotations

from uuid import uuid4

from af_core.orchestrator.execution_audit_models import (
    AuditEventType,
    ExecutionAuditRecord,
)

from .learning_models import (
    KnowledgeCandidate,
    LearningConfidence,
    LearningEvent,
    LearningEventType,
)


class KnowledgeExtractorError(RuntimeError):
    pass


class KnowledgeExtractorEngine:
    """
    Converts execution audit results into
    reusable learning knowledge candidates.
    """

    def __init__(self) -> None:
        self._events: list[
            LearningEvent
        ] = []

        self._candidates: list[
            KnowledgeCandidate
        ] = []

    def extract(
        self,
        record: ExecutionAuditRecord,
    ) -> LearningEvent:

        event_type = (
            LearningEventType.FAILURE_PATTERN
        )

        confidence = (
            LearningConfidence.MEDIUM
        )

        summary = (
            "Execution failure pattern detected"
        )

        reusable = False
        category = "failure"

        if (
            record.event_type
            is AuditEventType
            .EXECUTION_COMPLETED
        ):
            event_type = (
                LearningEventType
                .SUCCESS_PATTERN
            )

            confidence = (
                LearningConfidence.HIGH
            )

            summary = (
                "Successful execution pattern detected"
            )

            reusable = True
            category = "success"

        elif (
            record.event_type
            is AuditEventType
            .RECOVERY_TRIGGERED
        ):
            event_type = (
                LearningEventType
                .RECOVERY_LESSON
            )

            summary = (
                "Recovery execution lesson detected"
            )

            category = "recovery"

        event = LearningEvent(
            event_id=str(uuid4()),
            source_run_id=(
                record.run_id
            ),
            source_step_id=(
                record.step_id
            ),
            event_type=event_type,
            confidence=confidence,
            summary=summary,
            tags=(
                category,
            ),
        )

        candidate = KnowledgeCandidate(
            candidate_id=str(uuid4()),
            learning_event_id=(
                event.event_id
            ),
            category=category,
            content=summary,
            reusable=reusable,
        )

        self._events.append(
            event
        )

        self._candidates.append(
            candidate
        )

        return event

    def events(
        self,
    ) -> tuple[LearningEvent, ...]:
        return tuple(
            self._events
        )

    def candidates(
        self,
    ) -> tuple[
        KnowledgeCandidate,
        ...
    ]:
        return tuple(
            self._candidates
        )
