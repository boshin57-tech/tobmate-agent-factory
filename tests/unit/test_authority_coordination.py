from af_core.orchestrator.authority_coordination import (
    AuthorityAwareCoordinationEngine,
)
from af_core.orchestrator.coordination_engine import (
    CoordinationEngine,
)
from af_core.orchestrator.coordination_models import (
    CoordinationAgent,
    CoordinationConflictType,
    CoordinationDecision,
    CoordinationTask,
)
from af_core.orchestrator.coordination_registry import (
    CoordinationRegistry,
)
from af_core.runtime.authority_engine import AuthorityEngine
from af_core.runtime.capability_models import (
    AuthorityDelegation,
    AuthorityGrant,
    CapabilityDefinition,
    CapabilityScope,
)
from af_core.runtime.capability_registry import (
    CapabilityRegistry,
)


def fixture():
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
            capability_ids=frozenset({"code"}),
        )
    )
    registry.register_agent(
        CoordinationAgent(
            agent_id="agent-2",
            name="Agent 2",
            role="developer",
            capability_ids=frozenset({"code"}),
        )
    )
    registry.register_task(
        CoordinationTask(
            task_id="task-1",
            name="Implement feature",
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

    return registry, authority, coordination, gated


def test_direct_grant_allows_assignment() -> None:
    _, authority, coordination, gated = fixture()

    authority.grant(
        AuthorityGrant(
            grant_id="grant-1",
            subject_id="agent-1",
            capability_id="code",
            scope=CapabilityScope.TASK,
            scope_id="task-1",
            granted_by="admin",
        )
    )

    result = gated.assign(
        task_id="task-1",
        agent_id="agent-1",
    )

    assert result.decision is (
        CoordinationDecision.ASSIGN
    )
    assert result.metadata["authority"][0][
        "allowed"
    ] is True
    assert coordination.conflicts() == ()


def test_missing_grant_blocks_assignment() -> None:
    _, _, coordination, gated = fixture()

    result = gated.assign(
        task_id="task-1",
        agent_id="agent-1",
    )

    assert result.decision is (
        CoordinationDecision.BLOCK
    )
    assert coordination.conflicts()[0].conflict_type is (
        CoordinationConflictType.AUTHORITY_DENIED
    )


def test_out_of_scope_grant_blocks_assignment() -> None:
    _, authority, coordination, gated = fixture()

    authority.grant(
        AuthorityGrant(
            grant_id="grant-wrong-scope",
            subject_id="agent-1",
            capability_id="code",
            scope=CapabilityScope.TASK,
            scope_id="task-other",
            granted_by="admin",
        )
    )

    result = gated.assign(
        task_id="task-1",
        agent_id="agent-1",
    )

    assert result.decision is (
        CoordinationDecision.BLOCK
    )
    assert coordination.conflicts()[0].conflict_type is (
        CoordinationConflictType.AUTHORITY_DENIED
    )


def test_delegated_grant_allows_assignment() -> None:
    _, authority, coordination, gated = fixture()

    authority.grant(
        AuthorityGrant(
            grant_id="grant-owner",
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
            delegation_id="delegation-1",
            parent_grant_id="grant-owner",
            delegated_by="agent-1",
            delegated_to="agent-2",
            capability_id="code",
            scope=CapabilityScope.TASK,
            scope_id="task-1",
        )
    )

    result = gated.assign(
        task_id="task-1",
        agent_id="agent-2",
    )

    assert result.decision is (
        CoordinationDecision.ASSIGN
    )
    assert result.metadata["authority"][0][
        "decision"
    ] == "delegated"
    assert coordination.conflicts() == ()


def test_revoked_grant_blocks_assignment() -> None:
    _, authority, coordination, gated = fixture()

    authority.grant(
        AuthorityGrant(
            grant_id="grant-revoked",
            subject_id="agent-1",
            capability_id="code",
            scope=CapabilityScope.TASK,
            scope_id="task-1",
            granted_by="admin",
        )
    )
    authority.revoke_grant("grant-revoked")

    result = gated.assign(
        task_id="task-1",
        agent_id="agent-1",
    )

    assert result.decision is (
        CoordinationDecision.BLOCK
    )
    assert coordination.conflicts()[0].conflict_type is (
        CoordinationConflictType.AUTHORITY_DENIED
    )
