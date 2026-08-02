from af_core.runtime.authority_policy_adapter import (
    AuthorityPolicyAdapter,
)
from af_core.runtime.capability_models import (
    AuthorityDecision,
    AuthorityEvaluation,
    CapabilityScope,
)
from af_core.runtime.runtime_policy_models import (
    RuntimePolicyDecision,
)


def evaluation(
    decision: AuthorityDecision,
) -> AuthorityEvaluation:
    return AuthorityEvaluation(
        request_id="request-1",
        subject_id="agent-1",
        capability_id="tool.read",
        scope=CapabilityScope.TOOL,
        scope_id="tool.echo",
        decision=decision,
        allowed=decision in {
            AuthorityDecision.ALLOW,
            AuthorityDecision.DELEGATED,
        },
        reason=decision.value,
    )


def test_direct_authority_maps_to_allow() -> None:
    result = AuthorityPolicyAdapter.decision_for(
        evaluation(AuthorityDecision.ALLOW)
    )

    assert result is RuntimePolicyDecision.ALLOW


def test_delegated_authority_maps_to_allow() -> None:
    result = AuthorityPolicyAdapter.decision_for(
        evaluation(AuthorityDecision.DELEGATED)
    )

    assert result is RuntimePolicyDecision.ALLOW


def test_missing_authority_maps_to_deny() -> None:
    result = AuthorityPolicyAdapter.decision_for(
        evaluation(AuthorityDecision.NOT_GRANTED)
    )

    assert result is RuntimePolicyDecision.DENY


def test_restricted_authority_states_map_to_deny() -> None:
    restricted = (
        AuthorityDecision.OUT_OF_SCOPE,
        AuthorityDecision.REVOKED,
        AuthorityDecision.EXPIRED,
        AuthorityDecision.DENY,
    )

    for decision in restricted:
        assert AuthorityPolicyAdapter.decision_for(
            evaluation(decision)
        ) is RuntimePolicyDecision.DENY


def test_metadata_preserves_authority_evidence() -> None:
    value = evaluation(AuthorityDecision.ALLOW)

    metadata = AuthorityPolicyAdapter.metadata_for(value)

    assert metadata["authority_decision"] == "allow"
    assert metadata["capability_id"] == "tool.read"
    assert metadata["scope_id"] == "tool.echo"
