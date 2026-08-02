from __future__ import annotations

from af_core.orchestrator.authority_coordination import (
    AuthorityAwareCoordinationEngine,
)
from af_core.orchestrator.coordination_engine import (
    CoordinationEngine,
)
from af_core.orchestrator.coordination_models import (
    CoordinationAgent,
)
from af_core.orchestrator.coordination_registry import (
    CoordinationRegistry,
)
from af_core.orchestrator.team_formation import (
    TeamFormationEngine,
)
from af_core.orchestrator.workflow_coordinator import (
    WorkflowCoordinator,
)
from af_core.orchestrator.workflow_engine import (
    WorkflowEngine,
)
from af_core.orchestrator.workflow_models import (
    WorkflowDefinition,
    WorkflowStep,
)
from af_core.runtime.authority_engine import (
    AuthorityEngine,
)
from af_core.runtime.capability_models import (
    AuthorityDelegation,
    AuthorityGrant,
    AuthorityRequest,
    CapabilityDefinition,
    CapabilityScope,
)
from af_core.runtime.capability_registry import (
    CapabilityRegistry,
)


def build_stack():
    capabilities = CapabilityRegistry()

    capabilities.register(
        CapabilityDefinition(
            capability_id="code",
            name="Code",
        )
    )

    authority = AuthorityEngine(
        capabilities=capabilities
    )

    registry = CoordinationRegistry()

    registry.register_agent(
        CoordinationAgent(
            agent_id="agent-1",
            name="Agent 1",
            role="developer",
            capability_ids=frozenset(
                {"code"}
            ),
        )
    )

    registry.register_agent(
        CoordinationAgent(
            agent_id="agent-2",
            name="Agent 2",
            role="developer",
            capability_ids=frozenset(
                {"code"}
            ),
        )
    )

    registry.register_task(
        # Workflow step과 coordination task 공유 목적
        # 실제 assignment 대상
        __import__(
            "af_core.orchestrator.coordination_models",
            fromlist=[
                "CoordinationTask"
            ],
        ).CoordinationTask(
            task_id="step-1",
            name="Step 1",
            required_capability_ids=frozenset(
                {"code"}
            ),
        )
    )

    coordination = CoordinationEngine(
        registry=registry
    )

    gated = AuthorityAwareCoordinationEngine(
        registry=registry,
        coordination=coordination,
        authority=authority,
    )

    workflow_engine = WorkflowEngine()

    workflow = WorkflowDefinition(
        workflow_id="workflow-1",
        name="Workflow",
        steps=(
            WorkflowStep(
                step_id="step-1",
                name="Step 1",
                required_capability_ids=frozenset(
                    {"code"}
                ),
            ),
        ),
    )

    run = workflow_engine.create_run(
        workflow
    )

    workflow_engine.start_run(
        run.run_id
    )

    coordinator = WorkflowCoordinator(
        workflow_engine=workflow_engine,
        coordination_registry=registry,
        team_builder=TeamFormationEngine(
            registry=registry
        ),
        authority_coordination=gated,
    )

    return (
        authority,
        coordination,
        workflow_engine,
        coordinator,
        run,
    )


def test_authorized_agent_receives_workflow_step():
    (
        authority,
        coordination,
        _,
        coordinator,
        run,
    ) = build_stack()

    authority.grant(
        AuthorityGrant(
            grant_id="grant-1",
            subject_id="agent-1",
            capability_id="code",
            scope=CapabilityScope.TASK,
            scope_id="step-1",
            granted_by="admin",
        )
    )

    result = coordinator.schedule_and_assign(
        run_id=run.run_id
    )

    assert len(result) == 1
    assert coordination.assignments()[0].agent_id == (
        "agent-1"
    )


def test_missing_authority_blocks_assignment():
    (
        _,
        coordination,
        _,
        coordinator,
        run,
    ) = build_stack()

    try:
        coordinator.schedule_and_assign(
            run_id=run.run_id
        )
    except Exception:
        pass

    assert coordination.conflicts()
    assert (
        coordination.conflicts()[0]
        .conflict_type.value
        == "authority_denied"
    )


def test_delegated_authority_allows_assignment():
    (
        authority,
        coordination,
        _,
        coordinator,
        run,
    ) = build_stack()

    authority.grant(
        AuthorityGrant(
            grant_id="owner-grant",
            subject_id="agent-1",
            capability_id="code",
            scope=CapabilityScope.GLOBAL,
            scope_id="global",
            granted_by="admin",
            delegable=True,
        )
    )

    authority.delegate(
        AuthorityDelegation(
            delegation_id="delegate-1",
            parent_grant_id="owner-grant",
            delegated_by="agent-1",
            delegated_to="agent-2",
            capability_id="code",
            scope=CapabilityScope.TASK,
            scope_id="step-1",
        )
    )

    coordinator.schedule_and_assign(
        run_id=run.run_id
    )

    assert coordination.assignments()[0].agent_id in {
        "agent-1",
        "agent-2",
    }
