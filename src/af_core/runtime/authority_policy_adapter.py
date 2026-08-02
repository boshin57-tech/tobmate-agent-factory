"""Convert authority evaluations into runtime policy decisions."""

from __future__ import annotations

from af_core.runtime.capability_models import (
    AuthorityDecision,
    AuthorityEvaluation,
)
from af_core.runtime.runtime_policy_models import (
    RuntimePolicyDecision,
)


class AuthorityPolicyAdapter:
    @staticmethod
    def decision_for(
        evaluation: AuthorityEvaluation,
    ) -> RuntimePolicyDecision:
        if evaluation.decision in {
            AuthorityDecision.ALLOW,
            AuthorityDecision.DELEGATED,
        }:
            return RuntimePolicyDecision.ALLOW

        return RuntimePolicyDecision.DENY

    @staticmethod
    def metadata_for(
        evaluation: AuthorityEvaluation,
    ) -> dict[str, object]:
        return {
            "authority_evaluation_id": (
                evaluation.evaluation_id
            ),
            "authority_decision": (
                evaluation.decision.value
            ),
            "capability_id": evaluation.capability_id,
            "scope": evaluation.scope.value,
            "scope_id": evaluation.scope_id,
            "matched_grant_id": (
                evaluation.matched_grant_id
            ),
            "matched_delegation_id": (
                evaluation.matched_delegation_id
            ),
            "reason": evaluation.reason,
        }
