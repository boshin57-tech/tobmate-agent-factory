from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from .usage import UsageRecord, UsageSummary


class BudgetScope(StrEnum):
    GLOBAL = "GLOBAL"
    PROJECT = "PROJECT"
    RUN = "RUN"
    TASK = "TASK"
    AGENT = "AGENT"


class BudgetDecision(StrEnum):
    ALLOW = "ALLOW"
    WARN = "WARN"
    BLOCK = "BLOCK"


class BudgetLimit(BaseModel):
    scope: BudgetScope
    scope_id: str
    maximum_cost_usd: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
    )
    maximum_input_tokens: int | None = Field(
        default=None,
        ge=0,
    )
    maximum_output_tokens: int | None = Field(
        default=None,
        ge=0,
    )
    maximum_total_tokens: int | None = Field(
        default=None,
        ge=0,
    )
    warning_ratio: Decimal = Field(
        default=Decimal("0.80"),
        ge=Decimal("0"),
        le=Decimal("1"),
    )
    enabled: bool = True


class BudgetEvaluation(BaseModel):
    decision: BudgetDecision
    scope: BudgetScope
    scope_id: str
    reasons: list[str] = Field(default_factory=list)
    current_cost_usd: Decimal = Decimal("0")
    projected_cost_usd: Decimal = Decimal("0")
    current_total_tokens: int = 0
    projected_total_tokens: int = 0


class BudgetExceededError(RuntimeError):
    """Raised when an execution exceeds its permitted budget."""


class BudgetPolicy:
    def __init__(
        self,
        limits: list[BudgetLimit] | None = None,
    ) -> None:
        self._limits = list(limits or [])

    def add_limit(
        self,
        limit: BudgetLimit,
    ) -> None:
        self._limits.append(limit)

    def list_limits(self) -> list[BudgetLimit]:
        return list(self._limits)

    def evaluate(
        self,
        *,
        current: UsageSummary,
        projected: UsageRecord,
        scope: BudgetScope,
        scope_id: str,
    ) -> BudgetEvaluation:
        limit = self._find_limit(
            scope=scope,
            scope_id=scope_id,
        )

        projected_cost = (
            current.total_cost_usd
            + projected.cost.total_cost_usd
        )
        projected_input = (
            current.input_tokens
            + projected.usage.input_tokens
        )
        projected_output = (
            current.output_tokens
            + projected.usage.output_tokens
        )
        projected_total = (
            current.total_tokens
            + projected.usage.total_tokens
        )

        if limit is None or not limit.enabled:
            return BudgetEvaluation(
                decision=BudgetDecision.ALLOW,
                scope=scope,
                scope_id=scope_id,
                current_cost_usd=current.total_cost_usd,
                projected_cost_usd=projected_cost,
                current_total_tokens=current.total_tokens,
                projected_total_tokens=projected_total,
            )

        reasons: list[str] = []

        self._check_maximum(
            name="cost",
            projected=projected_cost,
            maximum=limit.maximum_cost_usd,
            reasons=reasons,
        )
        self._check_maximum(
            name="input tokens",
            projected=projected_input,
            maximum=limit.maximum_input_tokens,
            reasons=reasons,
        )
        self._check_maximum(
            name="output tokens",
            projected=projected_output,
            maximum=limit.maximum_output_tokens,
            reasons=reasons,
        )
        self._check_maximum(
            name="total tokens",
            projected=projected_total,
            maximum=limit.maximum_total_tokens,
            reasons=reasons,
        )

        if reasons:
            decision = BudgetDecision.BLOCK
        elif self._warning_threshold_reached(
            projected_cost=projected_cost,
            projected_input=projected_input,
            projected_output=projected_output,
            projected_total=projected_total,
            limit=limit,
        ):
            decision = BudgetDecision.WARN
            reasons.append(
                "Projected usage reached the configured warning threshold."
            )
        else:
            decision = BudgetDecision.ALLOW

        return BudgetEvaluation(
            decision=decision,
            scope=scope,
            scope_id=scope_id,
            reasons=reasons,
            current_cost_usd=current.total_cost_usd,
            projected_cost_usd=projected_cost,
            current_total_tokens=current.total_tokens,
            projected_total_tokens=projected_total,
        )

    def enforce(
        self,
        evaluation: BudgetEvaluation,
    ) -> None:
        if evaluation.decision is BudgetDecision.BLOCK:
            detail = "; ".join(
                evaluation.reasons
            ) or "Budget limit exceeded."

            raise BudgetExceededError(detail)

    def _find_limit(
        self,
        *,
        scope: BudgetScope,
        scope_id: str,
    ) -> BudgetLimit | None:
        matches = [
            limit
            for limit in self._limits
            if (
                limit.scope is scope
                and limit.scope_id == scope_id
            )
        ]

        if not matches:
            return None

        if len(matches) > 1:
            raise ValueError(
                f"Multiple budget limits configured for "
                f"{scope.value}:{scope_id}"
            )

        return matches[0]

    def _check_maximum(
        self,
        *,
        name: str,
        projected,
        maximum,
        reasons: list[str],
    ) -> None:
        if maximum is None:
            return

        if projected > maximum:
            reasons.append(
                f"Projected {name} {projected} exceeds maximum {maximum}."
            )

    def _warning_threshold_reached(
        self,
        *,
        projected_cost: Decimal,
        projected_input: int,
        projected_output: int,
        projected_total: int,
        limit: BudgetLimit,
    ) -> bool:
        values = [
            (
                Decimal(projected_cost),
                limit.maximum_cost_usd,
            ),
            (
                Decimal(projected_input),
                limit.maximum_input_tokens,
            ),
            (
                Decimal(projected_output),
                limit.maximum_output_tokens,
            ),
            (
                Decimal(projected_total),
                limit.maximum_total_tokens,
            ),
        ]

        for projected, maximum in values:
            if maximum is None:
                continue

            threshold = (
                Decimal(maximum)
                * limit.warning_ratio
            )

            if projected >= threshold:
                return True

        return False
