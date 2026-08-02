from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from af_core.runtime.authority_engine import (
    AuthorityEngine,
    AuthorityEngineError,
)
from af_core.runtime.capability_models import (
    AuthorityDecision,
    AuthorityDelegation,
    AuthorityGrant,
    AuthorityRequest,
    CapabilityDefinition,
    CapabilityScope,
)
from af_core.runtime.capability_registry import (
    CapabilityRegistry,
    CapabilityRegistryError,
)


def registry() -> CapabilityRegistry:
    value = CapabilityRegistry()

    value.register(
        CapabilityDefinition(
            capability_id="tool",
            name="Tool access",
        )
    )
    value.register(
        CapabilityDefinition(
            capability_id="tool.read",
            name="Tool read",
            parent_capability_id="tool",
        )
    )
    value.register(
        CapabilityDefinition(
            capability_id="tool.write",
            name="Tool write",
            parent_capability_id="tool",
        )
    )

    return value


def request(
    *,
    subject_id: str = "agent-1",
    capability_id: str = "tool.read",
    scope: CapabilityScope = CapabilityScope.TOOL,
    scope_id: str = "tool.echo",
) -> AuthorityRequest:
    return AuthorityRequest(
        request_id="request-1",
        subject_id=subject_id,
        capability_id=capability_id,
        scope=scope,
        scope_id=scope_id,
    )


def test_capability_registry_supports_inheritance() -> None:
    capabilities = registry()

    assert capabilities.inherits_from(
        "tool.read",
        "tool",
    )
    assert not capabilities.inherits_from(
        "tool",
        "tool.read",
    )


def test_registry_rejects_unknown_parent() -> None:
    capabilities = CapabilityRegistry()

    with pytest.raises(
        CapabilityRegistryError,
        match="Unknown parent capability",
    ):
        capabilities.register(
            CapabilityDefinition(
                capability_id="tool.read",
                name="Tool read",
                parent_capability_id="tool",
            )
        )


def test_direct_grant_allows_request() -> None:
    engine = AuthorityEngine(capabilities=registry())

    grant = engine.grant(
        AuthorityGrant(
            grant_id="grant-1",
            subject_id="agent-1",
            capability_id="tool.read",
            scope=CapabilityScope.TOOL,
            scope_id="tool.echo",
            granted_by="admin",
        )
    )

    evaluation = engine.evaluate(request())

    assert evaluation.allowed is True
    assert evaluation.decision is AuthorityDecision.ALLOW
    assert evaluation.matched_grant_id == grant.grant_id


def test_parent_capability_grant_allows_child() -> None:
    engine = AuthorityEngine(capabilities=registry())

    engine.grant(
        AuthorityGrant(
            grant_id="grant-parent",
            subject_id="agent-1",
            capability_id="tool",
            scope=CapabilityScope.GLOBAL,
            scope_id="global",
            granted_by="admin",
        )
    )

    evaluation = engine.evaluate(request())

    assert evaluation.allowed is True
    assert evaluation.decision is AuthorityDecision.ALLOW


def test_out_of_scope_is_rejected() -> None:
    engine = AuthorityEngine(capabilities=registry())

    engine.grant(
        AuthorityGrant(
            grant_id="grant-scope",
            subject_id="agent-1",
            capability_id="tool.read",
            scope=CapabilityScope.TOOL,
            scope_id="tool.alpha",
            granted_by="admin",
        )
    )

    evaluation = engine.evaluate(
        request(scope_id="tool.beta")
    )

    assert evaluation.allowed is False
    assert evaluation.decision is (
        AuthorityDecision.OUT_OF_SCOPE
    )


def test_missing_grant_returns_not_granted() -> None:
    engine = AuthorityEngine(capabilities=registry())

    evaluation = engine.evaluate(request())

    assert evaluation.allowed is False
    assert evaluation.decision is (
        AuthorityDecision.NOT_GRANTED
    )


def test_revoked_grant_is_rejected() -> None:
    engine = AuthorityEngine(capabilities=registry())

    engine.grant(
        AuthorityGrant(
            grant_id="grant-revoke",
            subject_id="agent-1",
            capability_id="tool.read",
            scope=CapabilityScope.TOOL,
            scope_id="tool.echo",
            granted_by="admin",
        )
    )
    engine.revoke_grant("grant-revoke")

    evaluation = engine.evaluate(request())

    assert evaluation.decision is AuthorityDecision.REVOKED
    assert evaluation.allowed is False


def test_expired_grant_is_rejected() -> None:
    engine = AuthorityEngine(capabilities=registry())

    expired_at = datetime.now(timezone.utc) - timedelta(
        minutes=1
    )

    engine.grant(
        AuthorityGrant(
            grant_id="grant-expired",
            subject_id="agent-1",
            capability_id="tool.read",
            scope=CapabilityScope.TOOL,
            scope_id="tool.echo",
            granted_by="admin",
            expires_at=expired_at,
        )
    )

    evaluation = engine.evaluate(request())

    assert evaluation.decision is AuthorityDecision.EXPIRED
    assert evaluation.allowed is False


def test_delegated_authority_allows_request() -> None:
    engine = AuthorityEngine(capabilities=registry())

    engine.grant(
        AuthorityGrant(
            grant_id="grant-owner",
            subject_id="agent-owner",
            capability_id="tool",
            scope=CapabilityScope.GLOBAL,
            scope_id="global",
            granted_by="admin",
            delegable=True,
        )
    )

    delegation = engine.delegate(
        AuthorityDelegation(
            delegation_id="delegation-1",
            parent_grant_id="grant-owner",
            delegated_by="agent-owner",
            delegated_to="agent-worker",
            capability_id="tool.read",
            scope=CapabilityScope.TOOL,
            scope_id="tool.echo",
        )
    )

    evaluation = engine.evaluate(
        request(subject_id="agent-worker")
    )

    assert evaluation.allowed is True
    assert evaluation.decision is (
        AuthorityDecision.DELEGATED
    )
    assert evaluation.matched_delegation_id == (
        delegation.delegation_id
    )


def test_non_delegable_grant_is_blocked() -> None:
    engine = AuthorityEngine(capabilities=registry())

    engine.grant(
        AuthorityGrant(
            grant_id="grant-fixed",
            subject_id="agent-owner",
            capability_id="tool",
            scope=CapabilityScope.GLOBAL,
            scope_id="global",
            granted_by="admin",
            delegable=False,
        )
    )

    with pytest.raises(
        AuthorityEngineError,
        match="not delegable",
    ):
        engine.delegate(
            AuthorityDelegation(
                delegation_id="delegation-blocked",
                parent_grant_id="grant-fixed",
                delegated_by="agent-owner",
                delegated_to="agent-worker",
                capability_id="tool.read",
                scope=CapabilityScope.TOOL,
                scope_id="tool.echo",
            )
        )


def test_delegation_cannot_exceed_scope() -> None:
    engine = AuthorityEngine(capabilities=registry())

    engine.grant(
        AuthorityGrant(
            grant_id="grant-limited",
            subject_id="agent-owner",
            capability_id="tool",
            scope=CapabilityScope.TOOL,
            scope_id="tool.alpha",
            granted_by="admin",
            delegable=True,
        )
    )

    with pytest.raises(
        AuthorityEngineError,
        match="scope exceeds",
    ):
        engine.delegate(
            AuthorityDelegation(
                delegation_id="delegation-wide",
                parent_grant_id="grant-limited",
                delegated_by="agent-owner",
                delegated_to="agent-worker",
                capability_id="tool.read",
                scope=CapabilityScope.TOOL,
                scope_id="tool.beta",
            )
        )


def test_evaluation_history_is_recorded() -> None:
    engine = AuthorityEngine(capabilities=registry())

    engine.evaluate(request())

    assert len(engine.history()) == 1
    assert engine.history()[0].request_id == "request-1"
