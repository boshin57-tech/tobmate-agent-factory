"""Unified runtime policy models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import IntEnum, StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RuntimePolicyDecision(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    QUARANTINE = "quarantine"
    DENY = "deny"


class RuntimePolicyPriority(IntEnum):
    NOT_APPLICABLE = 0
    ALLOW = 100
    REQUIRE_APPROVAL = 200
    QUARANTINE = 300
    DENY = 400

    @classmethod
    def for_decision(
        cls,
        decision: RuntimePolicyDecision,
    ) -> "RuntimePolicyPriority":
        return {
            RuntimePolicyDecision.NOT_APPLICABLE:
                cls.NOT_APPLICABLE,
            RuntimePolicyDecision.ALLOW:
                cls.ALLOW,
            RuntimePolicyDecision.REQUIRE_APPROVAL:
                cls.REQUIRE_APPROVAL,
            RuntimePolicyDecision.QUARANTINE:
                cls.QUARANTINE,
            RuntimePolicyDecision.DENY:
                cls.DENY,
        }[decision]


class RuntimePolicyScope(StrEnum):
    GLOBAL = "global"
    PROJECT = "project"
    RUN = "run"
    AGENT = "agent"
    TASK = "task"
    TOOL = "tool"


class RuntimeConstraintOperator(StrEnum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    NOT_IN = "not_in"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"


class RuntimeConstraint(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str = Field(min_length=1)
    operator: RuntimeConstraintOperator
    expected: Any = None

    def matches(self, attributes: dict[str, Any]) -> bool:
        exists = self.key in attributes
        actual = attributes.get(self.key)

        if self.operator is RuntimeConstraintOperator.EXISTS:
            return exists

        if self.operator is RuntimeConstraintOperator.NOT_EXISTS:
            return not exists

        if not exists:
            return False

        if self.operator is RuntimeConstraintOperator.EQUALS:
            return actual == self.expected

        if self.operator is RuntimeConstraintOperator.NOT_EQUALS:
            return actual != self.expected

        if self.operator is RuntimeConstraintOperator.IN:
            return (
                isinstance(
                    self.expected,
                    (list, tuple, set, frozenset),
                )
                and actual in self.expected
            )

        if self.operator is RuntimeConstraintOperator.NOT_IN:
            return (
                isinstance(
                    self.expected,
                    (list, tuple, set, frozenset),
                )
                and actual not in self.expected
            )

        return False


class RuntimeEvaluationContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str = Field(
        default_factory=lambda: str(uuid4()),
    )
    subject_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    resource: str = Field(min_length=1)

    scope: RuntimePolicyScope = RuntimePolicyScope.GLOBAL
    scope_id: str = "global"

    attributes: dict[str, Any] = Field(default_factory=dict)
    evaluated_at: datetime = Field(default_factory=utc_now)


class RuntimePolicyRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule_id: str = Field(min_length=1)
    policy_id: str = Field(min_length=1)
    name: str = Field(min_length=1)

    decision: RuntimePolicyDecision
    priority: int = Field(default=0, ge=0)

    subjects: frozenset[str] = frozenset({"*"})
    actions: frozenset[str] = frozenset({"*"})
    resources: frozenset[str] = frozenset({"*"})

    scopes: frozenset[RuntimePolicyScope] = frozenset(
        {RuntimePolicyScope.GLOBAL}
    )

    constraints: tuple[RuntimeConstraint, ...] = ()
    reason: str = ""
    enabled: bool = True

    def matches(
        self,
        context: RuntimeEvaluationContext,
    ) -> bool:
        if not self.enabled:
            return False

        if not self._matches(
            self.subjects,
            context.subject_id,
        ):
            return False

        if not self._matches(
            self.actions,
            context.action,
        ):
            return False

        if not self._matches(
            self.resources,
            context.resource,
        ):
            return False

        if (
            RuntimePolicyScope.GLOBAL not in self.scopes
            and context.scope not in self.scopes
        ):
            return False

        return all(
            constraint.matches(context.attributes)
            for constraint in self.constraints
        )

    @staticmethod
    def _matches(
        selectors: frozenset[str],
        value: str,
    ) -> bool:
        return "*" in selectors or value in selectors


class RuntimePolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)
    rules: tuple[RuntimePolicyRule, ...]
    enabled: bool = True
    created_at: datetime = Field(default_factory=utc_now)


class RuntimeRuleEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_id: str
    policy_version: int
    rule_id: str
    decision: RuntimePolicyDecision
    decision_priority: RuntimePolicyPriority
    rule_priority: int
    reason: str = ""


class RuntimePolicyResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    evaluation_id: str = Field(
        default_factory=lambda: str(uuid4()),
    )
    request_id: str
    subject_id: str
    action: str
    resource: str

    decision: RuntimePolicyDecision
    decision_priority: RuntimePolicyPriority

    matched_rules: tuple[RuntimeRuleEvaluation, ...] = ()
    reason: str = ""

    approval_required: bool = False
    quarantined: bool = False
    allowed: bool = False

    evaluated_at: datetime = Field(default_factory=utc_now)
