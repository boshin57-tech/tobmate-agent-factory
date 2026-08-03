from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from .message_models import AgentMessage


AuthorityChecker = Callable[
    [str, str, str, str],
    bool,
]


class AuthorityDecisionStatus(
    str,
    Enum,
):
    NOT_REQUIRED = "not_required"
    ALLOWED = "allowed"
    DENIED = "denied"


class AuthorityDecision(BaseModel):
    """
    Immutable result of a communication authority evaluation.
    """

    model_config = {
        "frozen": True,
    }

    message_id: str
    agent_id: str

    status: AuthorityDecisionStatus

    permission: str | None = None
    environment: str | None = None
    resource_scope: str | None = None

    reason: str

    evaluated_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    @property
    def allowed(self) -> bool:
        return self.status in {
            AuthorityDecisionStatus.NOT_REQUIRED,
            AuthorityDecisionStatus.ALLOWED,
        }


class CommunicationAuthorityGate:
    """
    Enforces authorization before an AgentMessage reaches subscribers.

    Security behavior:

    - Messages without `required_permission` are allowed.
    - Messages declaring a permission require an authority checker.
    - Missing checker for a protected message results in denial.
    - Checker errors fail closed and result in denial.
    """

    REQUIRED_PERMISSION_KEY = (
        "required_permission"
    )

    ENVIRONMENT_KEY = "environment"

    RESOURCE_SCOPE_KEY = (
        "resource_scope"
    )

    DEFAULT_ENVIRONMENT = "runtime"
    DEFAULT_SCOPE = "global"

    def __init__(
        self,
        checker: AuthorityChecker | None = None,
    ) -> None:
        self._checker = checker

    def evaluate(
        self,
        message: AgentMessage,
    ) -> AuthorityDecision:
        permission = (
            message.metadata.get(
                self.REQUIRED_PERMISSION_KEY
            )
        )

        if permission is None:
            return AuthorityDecision(
                message_id=message.message_id,
                agent_id=(
                    message.sender_agent_id
                ),
                status=(
                    AuthorityDecisionStatus
                    .NOT_REQUIRED
                ),
                reason=(
                    "message does not require "
                    "explicit authority"
                ),
            )

        normalized_permission = (
            permission.strip()
        )

        environment = (
            message.metadata.get(
                self.ENVIRONMENT_KEY,
                self.DEFAULT_ENVIRONMENT,
            )
            .strip()
        )

        resource_scope = (
            message.metadata.get(
                self.RESOURCE_SCOPE_KEY,
                self.DEFAULT_SCOPE,
            )
            .strip()
        )

        if not normalized_permission:
            return AuthorityDecision(
                message_id=message.message_id,
                agent_id=(
                    message.sender_agent_id
                ),
                status=(
                    AuthorityDecisionStatus
                    .DENIED
                ),
                permission=permission,
                environment=environment,
                resource_scope=resource_scope,
                reason=(
                    "required permission "
                    "must not be empty"
                ),
            )

        if self._checker is None:
            return AuthorityDecision(
                message_id=message.message_id,
                agent_id=(
                    message.sender_agent_id
                ),
                status=(
                    AuthorityDecisionStatus
                    .DENIED
                ),
                permission=(
                    normalized_permission
                ),
                environment=environment,
                resource_scope=resource_scope,
                reason=(
                    "protected message has no "
                    "configured authority checker"
                ),
            )

        try:
            allowed = self._checker(
                message.sender_agent_id,
                normalized_permission,
                environment,
                resource_scope,
            )
        except Exception:
            return AuthorityDecision(
                message_id=message.message_id,
                agent_id=(
                    message.sender_agent_id
                ),
                status=(
                    AuthorityDecisionStatus
                    .DENIED
                ),
                permission=(
                    normalized_permission
                ),
                environment=environment,
                resource_scope=resource_scope,
                reason=(
                    "authority checker failed"
                ),
            )

        if not allowed:
            return AuthorityDecision(
                message_id=message.message_id,
                agent_id=(
                    message.sender_agent_id
                ),
                status=(
                    AuthorityDecisionStatus
                    .DENIED
                ),
                permission=(
                    normalized_permission
                ),
                environment=environment,
                resource_scope=resource_scope,
                reason=(
                    "sender lacks required "
                    "authority"
                ),
            )

        return AuthorityDecision(
            message_id=message.message_id,
            agent_id=(
                message.sender_agent_id
            ),
            status=(
                AuthorityDecisionStatus.ALLOWED
            ),
            permission=normalized_permission,
            environment=environment,
            resource_scope=resource_scope,
            reason=(
                "required authority granted"
            ),
        )
