from __future__ import annotations

import pytest

from af_core.runtime.runtime_policy_engine import (
    RuntimePolicyApprovalRequiredError,
    RuntimePolicyDeniedError,
    RuntimePolicyEngine,
    RuntimePolicyQuarantinedError,
)
from af_core.runtime.runtime_policy_history import (
    GENESIS_HASH,
    RuntimePolicyHistory,
)
from af_core.runtime.runtime_policy_models import (
    RuntimeConstraint,
    RuntimeConstraintOperator,
    RuntimeEvaluationContext,
    RuntimePolicy,
    RuntimePolicyDecision,
    RuntimePolicyRule,
)
from af_core.runtime.runtime_policy_registry import (
    RuntimePolicyRegistry,
    RuntimePolicyRegistryError,
)


def make_rule(
    rule_id: str,
    decision: RuntimePolicyDecision,
    priority: int = 0,
) -> RuntimePolicyRule:
    return RuntimePolicyRule(
        rule_id=rule_id,
        policy_id="runtime.default",
        name=rule_id,
        decision=decision,
        priority=priority,
        reason=f"{rule_id} decision",
    )


def make_engine(
    *rules: RuntimePolicyRule,
) -> RuntimePolicyEngine:
    registry = RuntimePolicyRegistry()
    registry.register(
        RuntimePolicy(
            policy_id="runtime.default",
            name="Default runtime policy",
            rules=rules,
        )
    )
    return RuntimePolicyEngine(registry=registry)


def make_context(
    **attributes: object,
) -> RuntimeEvaluationContext:
    return RuntimeEvaluationContext(
        request_id="request-1",
        subject_id="agent-1",
        action="tool.execute",
        resource="tool.echo",
        attributes=attributes,
    )


def test_registry_registers_policy() -> None:
    registry = RuntimePolicyRegistry()
    policy = RuntimePolicy(
        policy_id="runtime.default",
        name="Default",
        rules=(
            make_rule(
                "allow",
                RuntimePolicyDecision.ALLOW,
            ),
        ),
    )

    registry.register(policy)

    assert registry.get("runtime.default") == policy
    assert len(registry) == 1


def test_registry_rejects_duplicate() -> None:
    registry = RuntimePolicyRegistry()
    policy = RuntimePolicy(
        policy_id="runtime.default",
        name="Default",
        rules=(),
    )

    registry.register(policy)

    with pytest.raises(RuntimePolicyRegistryError):
        registry.register(policy)


def test_constraint_matching() -> None:
    constraint = RuntimeConstraint(
        key="environment",
        operator=RuntimeConstraintOperator.EQUALS,
        expected="production",
    )

    assert constraint.matches(
        {"environment": "production"}
    )
    assert not constraint.matches(
        {"environment": "development"}
    )


def test_allow_decision() -> None:
    engine = make_engine(
        make_rule(
            "allow",
            RuntimePolicyDecision.ALLOW,
        )
    )

    result = engine.evaluate(make_context())

    assert result.allowed is True
    assert result.decision is RuntimePolicyDecision.ALLOW
    assert engine.enforce(result) == result


def test_deny_has_highest_precedence() -> None:
    engine = make_engine(
        make_rule(
            "allow",
            RuntimePolicyDecision.ALLOW,
            priority=999,
        ),
        make_rule(
            "approval",
            RuntimePolicyDecision.REQUIRE_APPROVAL,
        ),
        make_rule(
            "quarantine",
            RuntimePolicyDecision.QUARANTINE,
        ),
        make_rule(
            "deny",
            RuntimePolicyDecision.DENY,
        ),
    )

    result = engine.evaluate(make_context())

    assert result.decision is RuntimePolicyDecision.DENY
    assert result.matched_rules[0].rule_id == "deny"


def test_deny_enforcement() -> None:
    engine = make_engine(
        make_rule(
            "deny",
            RuntimePolicyDecision.DENY,
        )
    )

    result = engine.evaluate(make_context())

    with pytest.raises(RuntimePolicyDeniedError):
        engine.enforce(result)


def test_approval_enforcement() -> None:
    engine = make_engine(
        make_rule(
            "approval",
            RuntimePolicyDecision.REQUIRE_APPROVAL,
        )
    )

    result = engine.evaluate(make_context())

    with pytest.raises(
        RuntimePolicyApprovalRequiredError
    ):
        engine.enforce(result)

    assert engine.enforce(
        result,
        approved=True,
    ) == result


def test_quarantine_enforcement() -> None:
    engine = make_engine(
        make_rule(
            "quarantine",
            RuntimePolicyDecision.QUARANTINE,
        )
    )

    result = engine.evaluate(make_context())

    with pytest.raises(
        RuntimePolicyQuarantinedError
    ):
        engine.enforce(result)


def test_no_match_is_not_applicable() -> None:
    registry = RuntimePolicyRegistry()
    engine = RuntimePolicyEngine(registry=registry)

    result = engine.evaluate(make_context())

    assert result.decision is (
        RuntimePolicyDecision.NOT_APPLICABLE
    )


def test_history_chain_is_valid() -> None:
    history = RuntimePolicyHistory()
    registry = RuntimePolicyRegistry()
    registry.register(
        RuntimePolicy(
            policy_id="runtime.default",
            name="Default",
            rules=(
                make_rule(
                    "allow",
                    RuntimePolicyDecision.ALLOW,
                ),
            ),
        )
    )

    engine = RuntimePolicyEngine(
        registry=registry,
        history=history,
    )

    engine.evaluate(make_context())
    engine.evaluate(make_context())

    records = history.list_records()

    assert len(records) == 2
    assert records[0].previous_hash == GENESIS_HASH
    assert records[1].previous_hash == (
        records[0].record_hash
    )
    assert history.verify_chain().valid is True
