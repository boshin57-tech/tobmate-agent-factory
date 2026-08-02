from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from af_core.tools.models import (
    ExternalToolCall,
    ExternalToolDescriptor,
)

from .budget import (
    BudgetDecision,
    BudgetEvaluation,
    BudgetPolicy,
    BudgetScope,
)
from .usage import (
    UsageAccumulator,
    UsageRecord,
    UsageSummary,
)


class ToolBudgetError(RuntimeError):
    """Raised when Tool Call budget evaluation fails."""


class ToolBudgetScopeBinding(BaseModel):
    scope: BudgetScope
    scope_id: str


class ToolBudgetEvaluationResult(BaseModel):
    allowed: bool
    warning: bool = False
    projected: UsageRecord
    evaluations: list[BudgetEvaluation] = Field(
        default_factory=list
    )

    @property
    def blocked_evaluations(
        self,
    ) -> list[BudgetEvaluation]:
        return [
            item
            for item in self.evaluations
            if item.decision is BudgetDecision.BLOCK
        ]

    @property
    def warning_evaluations(
        self,
    ) -> list[BudgetEvaluation]:
        return [
            item
            for item in self.evaluations
            if item.decision is BudgetDecision.WARN
        ]

    @property
    def reasons(self) -> list[str]:
        values: list[str] = []

        for evaluation in self.evaluations:
            values.extend(evaluation.reasons)

        return values


class ToolBudgetAuditRecord(BaseModel):
    call_id: str
    tool_id: str
    projected: UsageRecord
    evaluation: ToolBudgetEvaluationResult
    committed: bool = False
    actual: UsageRecord | None = None


ToolUsageEstimator = Callable[
    [
        ExternalToolCall,
        ExternalToolDescriptor,
        int,
    ],
    UsageRecord,
]


class ToolCallBudgetGovernor:
    def __init__(
        self,
        *,
        policy: BudgetPolicy,
        estimator: ToolUsageEstimator,
        accumulator: UsageAccumulator | None = None,
    ) -> None:
        self.policy = policy
        self.estimator = estimator
        self.accumulator = (
            accumulator or UsageAccumulator()
        )
        self._audit: list[
            ToolBudgetAuditRecord
        ] = []

    def evaluate(
        self,
        *,
        call: ExternalToolCall,
        descriptor: ExternalToolDescriptor,
        attempt_count: int = 1,
        scopes: list[
            ToolBudgetScopeBinding
        ] | None = None,
    ) -> ToolBudgetEvaluationResult:
        if attempt_count < 1:
            raise ValueError(
                "attempt_count must be at least 1."
            )

        projected = self.estimator(
            call,
            descriptor,
            attempt_count,
        )

        current = self.accumulator.summarize()
        evaluations: list[BudgetEvaluation] = []

        for binding in scopes or []:
            evaluation = self.policy.evaluate(
                current=current,
                projected=projected,
                scope=binding.scope,
                scope_id=binding.scope_id,
            )
            evaluations.append(evaluation)

        blocked = any(
            item.decision is BudgetDecision.BLOCK
            for item in evaluations
        )
        warning = any(
            item.decision is BudgetDecision.WARN
            for item in evaluations
        )

        result = ToolBudgetEvaluationResult(
            allowed=not blocked,
            warning=warning,
            projected=projected,
            evaluations=evaluations,
        )

        self._audit.append(
            ToolBudgetAuditRecord(
                call_id=call.call_id,
                tool_id=call.tool_id,
                projected=projected,
                evaluation=result,
            )
        )

        return result

    def enforce(
        self,
        result: ToolBudgetEvaluationResult,
    ) -> None:
        for evaluation in result.evaluations:
            self.policy.enforce(evaluation)

    def commit(
        self,
        *,
        call_id: str,
        actual: UsageRecord | None = None,
    ) -> UsageRecord:
        record = self._find_latest(
            call_id
        )

        if record.committed:
            raise ToolBudgetError(
                f"Budget usage already committed: "
                f"{call_id}"
            )

        usage = actual or record.projected
        self.accumulator.add(usage)

        record.committed = True
        record.actual = usage

        return usage

    def current_usage(
        self,
    ) -> UsageSummary:
        return self.accumulator.summarize()

    def audit_records(
        self,
    ) -> list[ToolBudgetAuditRecord]:
        return [
            item.model_copy(deep=True)
            for item in self._audit
        ]

    def latest(
        self,
        call_id: str,
    ) -> ToolBudgetAuditRecord | None:
        for record in reversed(self._audit):
            if record.call_id == call_id:
                return record.model_copy(
                    deep=True
                )

        return None

    def scope_bindings(
        self,
        *,
        project_id: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
        agent_name: str | None = None,
        include_global: bool = True,
        global_scope_id: str = "global",
    ) -> list[ToolBudgetScopeBinding]:
        bindings: list[
            ToolBudgetScopeBinding
        ] = []

        if include_global:
            bindings.append(
                ToolBudgetScopeBinding(
                    scope=BudgetScope.GLOBAL,
                    scope_id=global_scope_id,
                )
            )

        values = [
            (
                BudgetScope.PROJECT,
                project_id,
            ),
            (
                BudgetScope.RUN,
                run_id,
            ),
            (
                BudgetScope.TASK,
                task_id,
            ),
            (
                BudgetScope.AGENT,
                agent_name,
            ),
        ]

        for scope, scope_id in values:
            if scope_id:
                bindings.append(
                    ToolBudgetScopeBinding(
                        scope=scope,
                        scope_id=scope_id,
                    )
                )

        return bindings

    def _find_latest(
        self,
        call_id: str,
    ) -> ToolBudgetAuditRecord:
        for record in reversed(self._audit):
            if record.call_id == call_id:
                return record

        raise ToolBudgetError(
            f"No budget evaluation exists for "
            f"call: {call_id}"
        )
