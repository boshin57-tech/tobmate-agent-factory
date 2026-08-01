from __future__ import annotations

from pydantic import BaseModel, Field

from .models import (
    ExternalToolCall,
    ExternalToolDescriptor,
    ExternalToolRisk,
)


class ToolPolicyDecision(BaseModel):
    allowed: bool
    reasons: list[str] = Field(default_factory=list)
    requires_approval: bool = False


class ToolPolicyViolation(RuntimeError):
    """Raised when an external tool call violates policy."""


class ExternalToolPolicy(BaseModel):
    allowed_tool_ids: set[str] = Field(default_factory=set)
    denied_tool_ids: set[str] = Field(default_factory=set)
    allowed_tags: set[str] = Field(default_factory=set)
    maximum_risk: ExternalToolRisk = (
        ExternalToolRisk.WORKSPACE_WRITE
    )
    require_approval_for: set[ExternalToolRisk] = Field(
        default_factory=lambda: {
            ExternalToolRisk.EXTERNAL_WRITE,
            ExternalToolRisk.PRIVILEGED,
        }
    )
    allow_external_network: bool = False
    allow_privileged: bool = False

    def evaluate(
        self,
        *,
        descriptor: ExternalToolDescriptor,
        call: ExternalToolCall,
        approved: bool = False,
    ) -> ToolPolicyDecision:
        del call
        reasons: list[str] = []

        if not descriptor.enabled:
            reasons.append("Tool is disabled.")

        if descriptor.tool_id in self.denied_tool_ids:
            reasons.append("Tool is explicitly denied.")

        if (
            self.allowed_tool_ids
            and descriptor.tool_id not in self.allowed_tool_ids
        ):
            reasons.append("Tool is not in the allowed tool set.")

        if (
            self.allowed_tags
            and not descriptor.tags.intersection(
                self.allowed_tags
            )
        ):
            reasons.append("Tool does not have an allowed tag.")

        if self._risk_rank(
            descriptor.risk
        ) > self._risk_rank(
            self.maximum_risk
        ):
            reasons.append(
                f"Tool risk {descriptor.risk.value} exceeds "
                f"maximum {self.maximum_risk.value}."
            )

        if (
            descriptor.risk is ExternalToolRisk.PRIVILEGED
            and not self.allow_privileged
        ):
            reasons.append(
                "Privileged tool execution is disabled."
            )

        external_transport = descriptor.transport.value in {
            "MCP_HTTP",
            "REST",
        }

        if external_transport and not self.allow_external_network:
            reasons.append(
                "External network tool execution is disabled."
            )

        requires_approval = (
            descriptor.risk in self.require_approval_for
        )

        if requires_approval and not approved:
            reasons.append(
                "Human approval is required for this tool risk."
            )

        return ToolPolicyDecision(
            allowed=not reasons,
            reasons=reasons,
            requires_approval=requires_approval,
        )

    def enforce(
        self,
        decision: ToolPolicyDecision,
    ) -> None:
        if decision.allowed:
            return

        raise ToolPolicyViolation(
            "; ".join(decision.reasons)
            or "Tool execution was blocked."
        )

    def _risk_rank(
        self,
        risk: ExternalToolRisk,
    ) -> int:
        return {
            ExternalToolRisk.READ_ONLY: 0,
            ExternalToolRisk.WORKSPACE_WRITE: 1,
            ExternalToolRisk.EXTERNAL_WRITE: 2,
            ExternalToolRisk.PRIVILEGED: 3,
        }[risk]
