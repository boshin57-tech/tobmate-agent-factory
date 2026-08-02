from __future__ import annotations

from af_core.learning.knowledge_extractor import (
    KnowledgeExtractorEngine,
)

from af_core.learning.lessons_learned_store import (
    LessonsLearnedStore,
)

from af_core.learning.pattern_update_engine import (
    PatternUpdateEngine,
)

from af_core.learning.knowledge_feedback import (
    KnowledgeFeedbackEngine,
)

from af_core.orchestrator.execution_audit_models import (
    AuditEventType,
    CompletionState,
    ExecutionAuditRecord,
)


def build_record(
    event_type,
):
    return ExecutionAuditRecord(
        audit_id="audit-1",
        run_id="run-1",
        step_id="step-1",
        event_type=event_type,
        completion_state=(
            CompletionState.VERIFIED
            if event_type
            is AuditEventType.EXECUTION_COMPLETED
            else CompletionState.FAILED
        ),
        message="execution event",
    )


def test_success_execution_creates_learning_event():

    extractor = KnowledgeExtractorEngine()

    event = extractor.extract(
        build_record(
            AuditEventType.EXECUTION_COMPLETED
        )
    )

    assert event.event_type.value == (
        "success_pattern"
    )

    assert len(
        extractor.candidates()
    ) == 1


def test_failure_execution_creates_failure_pattern():

    extractor = KnowledgeExtractorEngine()

    event = extractor.extract(
        build_record(
            AuditEventType.EXECUTION_FAILED
        )
    )

    assert event.event_type.value == (
        "failure_pattern"
    )


def test_lesson_store_keeps_experience():

    extractor = KnowledgeExtractorEngine()

    event = extractor.extract(
        build_record(
            AuditEventType.EXECUTION_COMPLETED
        )
    )

    store = LessonsLearnedStore()

    lesson = store.add(
        event,
        reusable=True,
    )

    assert store.count == 1
    assert lesson.reusable is True


def test_pattern_update_from_lesson():

    extractor = KnowledgeExtractorEngine()

    event = extractor.extract(
        build_record(
            AuditEventType.EXECUTION_COMPLETED
        )
    )

    store = LessonsLearnedStore()

    lesson = store.add(
        event,
        reusable=True,
    )

    engine = PatternUpdateEngine()

    pattern = engine.update(
        lesson
    )

    assert engine.count == 1
    assert pattern.pattern_type == (
        "success"
    )


def test_feedback_snapshot():

    lessons = LessonsLearnedStore()

    patterns = PatternUpdateEngine()

    feedback = KnowledgeFeedbackEngine(
        lessons_store=lessons,
        pattern_engine=patterns,
    )

    snapshot = (
        feedback.generate_snapshot()
    )

    assert snapshot.lesson_count == 0
    assert snapshot.pattern_count == 0

    assert len(
        feedback.snapshots()
    ) == 1
