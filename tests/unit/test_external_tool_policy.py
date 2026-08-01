import pytest

from af_core.tools.models import (
    ExternalToolCall,
    ExternalToolDescriptor,
    ExternalToolRisk,
    ExternalToolTransport,
)
from af_core.tools.policy import (
    ExternalToolPolicy,
    ToolPolicyViolation,
)


def call(
    tool_id: str = "tool.read",
) -> ExternalToolCall:
    return ExternalToolCall(
        call_id="call-1",
        tool_id=tool_id,
        arguments={},
    )


def descriptor(
    *,
    tool_id: str = "tool.read",
    risk: ExternalToolRisk = (
        ExternalToolRisk.READ_ONLY
    ),
    transport: ExternalToolTransport = (
        ExternalToolTransport.INTERNAL
    ),
    enabled: bool = True,
    tags: set[str] | None = None,
) -> ExternalToolDescriptor:
    return ExternalToolDescriptor(
        tool_id=tool_id,
        name=tool_id,
        description="Test tool",
        risk=risk,
        transport=transport,
        enabled=enabled,
        tags=tags or {"test"},
    )


def test_read_only_internal_tool_is_allowed() -> None:
    decision = ExternalToolPolicy().evaluate(
        descriptor=descriptor(),
        call=call(),
    )

    assert decision.allowed is True
    assert decision.requires_approval is False
    assert decision.reasons == []


def test_explicit_denial_and_allowed_set_are_enforced() -> None:
    policy = ExternalToolPolicy(
        allowed_tool_ids={"tool.allowed"},
        denied_tool_ids={"tool.denied"},
    )

    denied = policy.evaluate(
        descriptor=descriptor(
            tool_id="tool.denied"
        ),
        call=call("tool.denied"),
    )

    missing = policy.evaluate(
        descriptor=descriptor(
            tool_id="tool.other"
        ),
        call=call("tool.other"),
    )

    assert denied.allowed is False
    assert any(
        "explicitly denied" in reason
        for reason in denied.reasons
    )

    assert missing.allowed is False
    assert any(
        "allowed tool set" in reason
        for reason in missing.reasons
    )


def test_risk_and_human_approval_are_enforced() -> None:
    external_write = descriptor(
        tool_id="tool.external-write",
        risk=ExternalToolRisk.EXTERNAL_WRITE,
    )

    policy = ExternalToolPolicy(
        maximum_risk=ExternalToolRisk.EXTERNAL_WRITE,
    )

    blocked = policy.evaluate(
        descriptor=external_write,
        call=call("tool.external-write"),
        approved=False,
    )

    allowed = policy.evaluate(
        descriptor=external_write,
        call=call("tool.external-write"),
        approved=True,
    )

    assert blocked.allowed is False
    assert blocked.requires_approval is True
    assert allowed.allowed is True


def test_external_network_is_disabled_by_default() -> None:
    remote = descriptor(
        tool_id="tool.remote",
        transport=ExternalToolTransport.REST,
    )

    blocked = ExternalToolPolicy().evaluate(
        descriptor=remote,
        call=call("tool.remote"),
    )

    allowed = ExternalToolPolicy(
        allow_external_network=True,
    ).evaluate(
        descriptor=remote,
        call=call("tool.remote"),
    )

    assert blocked.allowed is False
    assert allowed.allowed is True


def test_privileged_tool_requires_permissions() -> None:
    privileged = descriptor(
        tool_id="tool.root",
        risk=ExternalToolRisk.PRIVILEGED,
    )

    policy = ExternalToolPolicy(
        maximum_risk=ExternalToolRisk.PRIVILEGED,
        allow_privileged=True,
    )

    blocked = policy.evaluate(
        descriptor=privileged,
        call=call("tool.root"),
    )

    approved = policy.evaluate(
        descriptor=privileged,
        call=call("tool.root"),
        approved=True,
    )

    assert blocked.allowed is False
    assert approved.allowed is True


def test_disabled_and_tag_filtered_tools_are_blocked() -> None:
    policy = ExternalToolPolicy(
        allowed_tags={"git"},
    )

    decision = policy.evaluate(
        descriptor=descriptor(
            enabled=False,
            tags={"filesystem"},
        ),
        call=call(),
    )

    assert decision.allowed is False
    assert len(decision.reasons) == 2


def test_enforce_raises() -> None:
    policy = ExternalToolPolicy(
        denied_tool_ids={"tool.read"},
    )

    decision = policy.evaluate(
        descriptor=descriptor(),
        call=call(),
    )

    with pytest.raises(
        ToolPolicyViolation,
    ):
        policy.enforce(decision)
