"""Unified runtime policy evaluation engine."""

from __future__ import annotations

from af_core.runtime.runtime_policy_history import (
    RuntimePolicyHistory,
)
from af_core.runtime.runtime_policy_models import (
    RuntimeEvaluationContext,
    RuntimePolicyDecision,
    RuntimePolicyPriority,
    RuntimePolicyResult,
    RuntimeRuleEvaluation,
)
from af_core.runtime.runtime_policy_registry import (
    RuntimePolicyRegistry,
)


class RuntimePolicyEnforcementError(PermissionError):
    def __init__(
        self,
        message: str,
        result: RuntimePolicyResult,
    ) -> None:
        super().__init__(message)
        self.result = result


class RuntimePolicyDeniedError(
    RuntimePolicyEnforcementError
):
    pass


class RuntimePolicyApprovalRequiredError(
    RuntimePolicyEnforcementError
):
    pass


class RuntimePolicyQuarantinedError(
    RuntimePolicyEnforcementError
):
    pass


class RuntimePolicyEngine:
    def __init__(
        self,
        *,
        registry: RuntimePolicyRegistry,
        history: RuntimePolicyHistory | None = None,
        default_decision: RuntimePolicyDecision = (
            RuntimePolicyDecision.NOT_APPLICABLE
        ),
    ) -> None:
        self._registry = registry
        self._history = history or RuntimePolicyHistory()
        self._default_decision = default_decision

    @property
    def history(self) -> RuntimePolicyHistory:
        return self._history

    def evaluate(
        self,
        context: RuntimeEvaluationContext,
    ) -> RuntimePolicyResult:
        evaluations: list[RuntimeRuleEvaluation] = []

        for policy in self._registry.list_policies(
            enabled_only=True,
        ):
            for rule in policy.rules:
                if not rule.matches(context):
                    continue

                evaluations.append(
                    RuntimeRuleEvaluation(
                        policy_id=policy.policy_id,
                        policy_version=policy.version,
                        rule_id=rule.rule_id,
                        decision=rule.decision,
                        decision_priority=(
                            RuntimePolicyPriority.for_decision(
                                rule.decision
                            )
                        ),
                        rule_priority=rule.priority,
                        reason=rule.reason,
                    )
                )

        evaluations.sort(
            key=lambda item: (
                int(item.decision_priority),
                item.rule_priority,
                item.policy_id,
                item.rule_id,
            ),
            reverse=True,
        )

        if evaluations:
            winner = evaluations[0]
            decision = winner.decision
            priority = winner.decision_priority
            reason = (
                winner.reason
                or "Selected by policy precedence"
            )
        else:
            decision = self._default_decision
            priority = RuntimePolicyPriority.for_decision(
                decision
            )
            reason = "No matching runtime policy rule"

        result = RuntimePolicyResult(
            request_id=context.request_id,
            subject_id=context.subject_id,
            action=context.action,
            resource=context.resource,
            decision=decision,
            decision_priority=priority,
            matched_rules=tuple(evaluations),
            reason=reason,
            approval_required=(
                decision
                is RuntimePolicyDecision.REQUIRE_APPROVAL
            ),
            quarantined=(
                decision is RuntimePolicyDecision.QUARANTINE
            ),
            allowed=(
                decision is RuntimePolicyDecision.ALLOW
            ),
        )

        self._history.append(result)
        return result

    def enforce(
        self,
        result: RuntimePolicyResult,
        *,
        approved: bool = False,
    ) -> RuntimePolicyResult:
        if result.decision is RuntimePolicyDecision.DENY:
            raise RuntimePolicyDeniedError(
                result.reason,
                result,
            )

        if (
            result.decision
            is RuntimePolicyDecision.QUARANTINE
        ):
            raise RuntimePolicyQuarantinedError(
                result.reason,
                result,
            )

        if (
            result.decision
            is RuntimePolicyDecision.REQUIRE_APPROVAL
            and not approved
        ):
            raise RuntimePolicyApprovalRequiredError(
                result.reason,
                result,
            )

        return result

    def evaluate_and_enforce(
        self,
        context: RuntimeEvaluationContext,
        *,
        approved: bool = False,
    ) -> RuntimePolicyResult:
        result = self.evaluate(context)
        return self.enforce(
            result,
            approved=approved,
        )
