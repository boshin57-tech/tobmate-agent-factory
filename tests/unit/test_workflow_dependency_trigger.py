from enum import Enum

import pytest

from af_core.orchestrator.workflow_dependency_graph import (
    DependencyCondition,
    DependencyJoinPolicy,
    WorkflowDependencyError,
    WorkflowDependencyGraph,
)
from af_core.orchestrator.workflow_trigger_engine import (
    WorkflowTriggerEngine,
    WorkflowTriggerError,
    WorkflowTriggerEvent,
    WorkflowTriggerKind,
    WorkflowTriggerRule,
)


class ExampleState(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


def test_01_stable_topological_order() -> None:
    graph = WorkflowDependencyGraph()
    graph.connect("build", "test")
    graph.connect("test", "deploy")

    assert graph.topological_order() == (
        "build",
        "test",
        "deploy",
    )


def test_02_cycle_is_rejected() -> None:
    graph = WorkflowDependencyGraph()
    graph.connect("build", "test")
    graph.connect("test", "deploy")

    with pytest.raises(
        WorkflowDependencyError,
        match="cycle",
    ):
        graph.connect("deploy", "build")


def test_03_duplicate_dependency_is_rejected() -> None:
    graph = WorkflowDependencyGraph()
    graph.connect("build", "test")

    with pytest.raises(
        WorkflowDependencyError,
        match="duplicate workflow dependency",
    ):
        graph.connect("build", "test")


def test_04_all_join_requires_every_dependency() -> None:
    graph = WorkflowDependencyGraph()
    graph.connect("linux-build", "package")
    graph.connect("windows-build", "package")

    states = {
        "linux-build": "succeeded",
        "windows-build": "pending",
        "package": "pending",
    }

    assert graph.is_ready("package", states) is False
    assert graph.blocked_by("package", states) == (
        "windows-build",
    )

    states["windows-build"] = "succeeded"

    assert graph.is_ready("package", states) is True
    assert graph.blocked_by("package", states) == ()


def test_05_any_join_accepts_one_dependency() -> None:
    graph = WorkflowDependencyGraph()
    graph.connect("primary", "continue")
    graph.connect("fallback", "continue")

    graph.set_join_policy(
        "continue",
        DependencyJoinPolicy.ANY,
    )

    states = {
        "primary": "failed",
        "fallback": ExampleState.SUCCEEDED,
        "continue": "pending",
    }

    assert graph.is_ready("continue", states) is True


def test_06_failure_completion_and_cancellation_conditions() -> None:
    graph = WorkflowDependencyGraph()

    graph.connect(
        "deploy",
        "rollback",
        condition=DependencyCondition.ON_FAILURE,
    )
    graph.connect(
        "deploy",
        "audit",
        condition=DependencyCondition.ON_COMPLETION,
    )
    graph.connect(
        "deploy",
        "cleanup",
        condition=DependencyCondition.ON_CANCELLATION,
    )

    failed = {
        "deploy": ExampleState.FAILED,
        "rollback": "pending",
        "audit": "pending",
        "cleanup": "pending",
    }

    assert graph.is_ready("rollback", failed) is True
    assert graph.is_ready("audit", failed) is True
    assert graph.is_ready("cleanup", failed) is False

    cancelled = dict(failed)
    cancelled["deploy"] = ExampleState.CANCELLED

    assert graph.is_ready("cleanup", cancelled) is True


def test_07_running_or_terminal_target_is_not_ready_again() -> None:
    graph = WorkflowDependencyGraph()
    graph.add_step("build")

    assert graph.is_ready(
        "build",
        {"build": "pending"},
    ) is True

    assert graph.is_ready(
        "build",
        {"build": "running"},
    ) is False

    assert graph.is_ready(
        "build",
        {"build": "succeeded"},
    ) is False


def test_08_workflow_started_trigger() -> None:
    engine = WorkflowTriggerEngine()

    engine.register(
        WorkflowTriggerRule(
            trigger_id="start-build",
            target_step_id="build",
            kind=WorkflowTriggerKind.WORKFLOW_STARTED,
        )
    )

    activations = engine.process(
        WorkflowTriggerEvent(
            workflow_id="workflow-1",
            event_id="start-1",
            kind=WorkflowTriggerKind.WORKFLOW_STARTED,
        )
    )

    assert len(activations) == 1
    assert activations[0].target_step_id == "build"


def test_09_state_change_trigger_supports_enum_state() -> None:
    engine = WorkflowTriggerEngine()

    engine.register(
        WorkflowTriggerRule(
            trigger_id="test-after-build",
            target_step_id="test",
            kind=WorkflowTriggerKind.STEP_STATE_CHANGED,
            source_step_id="build",
            expected_state="succeeded",
        )
    )

    activations = engine.process(
        WorkflowTriggerEvent(
            workflow_id="workflow-1",
            event_id="state-1",
            kind=WorkflowTriggerKind.STEP_STATE_CHANGED,
            source_step_id="build",
            state=ExampleState.SUCCEEDED,
        )
    )

    assert len(activations) == 1
    assert activations[0].trigger_id == "test-after-build"


def test_10_named_event_requires_exact_name() -> None:
    engine = WorkflowTriggerEngine()

    engine.register(
        WorkflowTriggerRule(
            trigger_id="deployment-approved",
            target_step_id="deploy",
            kind=WorkflowTriggerKind.EVENT_RECEIVED,
            event_name="deployment.approved",
        )
    )

    ignored = engine.process(
        WorkflowTriggerEvent(
            workflow_id="workflow-1",
            event_id="event-1",
            kind=WorkflowTriggerKind.EVENT_RECEIVED,
            event_name="deployment.rejected",
        )
    )

    matched = engine.process(
        WorkflowTriggerEvent(
            workflow_id="workflow-1",
            event_id="event-2",
            kind=WorkflowTriggerKind.EVENT_RECEIVED,
            event_name="deployment.approved",
        )
    )

    assert ignored == ()
    assert len(matched) == 1
    assert matched[0].target_step_id == "deploy"


def test_11_event_processing_is_idempotent() -> None:
    engine = WorkflowTriggerEngine()

    engine.register(
        WorkflowTriggerRule(
            trigger_id="manual-deploy",
            target_step_id="deploy",
            kind=WorkflowTriggerKind.MANUAL,
            once_per_workflow=False,
        )
    )

    event = WorkflowTriggerEvent(
        workflow_id="workflow-1",
        event_id="manual-1",
        kind=WorkflowTriggerKind.MANUAL,
    )

    assert len(engine.process(event)) == 1
    assert engine.process(event) == ()

    assert engine.has_seen_event(
        "workflow-1",
        "manual-1",
    ) is True


def test_12_once_per_workflow_and_clear() -> None:
    engine = WorkflowTriggerEngine()

    engine.register(
        WorkflowTriggerRule(
            trigger_id="start-build",
            target_step_id="build",
            kind=WorkflowTriggerKind.WORKFLOW_STARTED,
        )
    )

    first = WorkflowTriggerEvent(
        workflow_id="workflow-1",
        event_id="start-1",
        kind=WorkflowTriggerKind.WORKFLOW_STARTED,
    )
    second = WorkflowTriggerEvent(
        workflow_id="workflow-1",
        event_id="start-2",
        kind=WorkflowTriggerKind.WORKFLOW_STARTED,
    )

    assert len(engine.process(first)) == 1
    assert engine.process(second) == ()

    engine.clear_workflow("workflow-1")

    assert len(engine.process(first)) == 1


def test_13_dependency_graph_gates_manual_trigger() -> None:
    graph = WorkflowDependencyGraph()
    graph.connect("build", "deploy")

    engine = WorkflowTriggerEngine()
    engine.register(
        WorkflowTriggerRule(
            trigger_id="manual-deploy",
            target_step_id="deploy",
            kind=WorkflowTriggerKind.MANUAL,
            once_per_workflow=False,
        )
    )

    blocked = engine.process(
        WorkflowTriggerEvent(
            workflow_id="workflow-1",
            event_id="manual-1",
            kind=WorkflowTriggerKind.MANUAL,
        ),
        dependency_graph=graph,
        states={
            "build": "running",
            "deploy": "pending",
        },
    )

    permitted = engine.process(
        WorkflowTriggerEvent(
            workflow_id="workflow-1",
            event_id="manual-2",
            kind=WorkflowTriggerKind.MANUAL,
        ),
        dependency_graph=graph,
        states={
            "build": "succeeded",
            "deploy": "pending",
        },
    )

    assert blocked == ()
    assert len(permitted) == 1


def test_14_dependency_ready_activation_is_emitted_once() -> None:
    graph = WorkflowDependencyGraph()
    graph.connect("build", "test")

    engine = WorkflowTriggerEngine()

    states = {
        "build": "succeeded",
        "test": "pending",
    }

    first = engine.evaluate_dependencies(
        "workflow-1",
        graph,
        states,
    )
    second = engine.evaluate_dependencies(
        "workflow-1",
        graph,
        states,
    )

    assert len(first) == 1
    assert first[0].target_step_id == "test"
    assert (
        first[0].kind
        is WorkflowTriggerKind.DEPENDENCY_READY
    )
    assert second == ()


def test_15_duplicate_trigger_registration_is_rejected() -> None:
    engine = WorkflowTriggerEngine()

    rule = WorkflowTriggerRule(
        trigger_id="start-build",
        target_step_id="build",
        kind=WorkflowTriggerKind.WORKFLOW_STARTED,
    )

    engine.register(rule)

    with pytest.raises(
        WorkflowTriggerError,
        match="duplicate workflow trigger",
    ):
        engine.register(rule)
