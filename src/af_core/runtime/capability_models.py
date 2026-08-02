"""Capability and authority domain models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CapabilityScope(StrEnum):
    GLOBAL = "global"
    PROJECT = "project"
    RUN = "run"
    AGENT = "agent"
    TASK = "task"
    TOOL = "tool"


class AuthorityDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    DELEGATED = "delegated"
    OUT_OF_SCOPE = "out_of_scope"
    NOT_GRANTED = "not_granted"
    REVOKED = "revoked"
    EXPIRED = "expired"


class CapabilityDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    capability_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    parent_capability_id: str | None = None
    enabled: bool = True
    metadata: dict[str, object] = Field(
        default_factory=dict
    )


class AuthorityGrant(BaseModel):
    model_config = ConfigDict(frozen=True)

    grant_id: str = Field(
        default_factory=lambda: str(uuid4())
    )
    subject_id: str = Field(min_length=1)
    capability_id: str = Field(min_length=1)

    scope: CapabilityScope = CapabilityScope.GLOBAL
    scope_id: str = "global"

    granted_by: str = Field(min_length=1)
    delegable: bool = False
    revoked: bool = False

    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None
    metadata: dict[str, object] = Field(
        default_factory=dict
    )

    def is_expired(
        self,
        *,
        now: datetime | None = None,
    ) -> bool:
        if self.expires_at is None:
            return False

        current = now or utc_now()
        return current >= self.expires_at


class AuthorityDelegation(BaseModel):
    model_config = ConfigDict(frozen=True)

    delegation_id: str = Field(
        default_factory=lambda: str(uuid4())
    )
    parent_grant_id: str = Field(min_length=1)

    delegated_by: str = Field(min_length=1)
    delegated_to: str = Field(min_length=1)
    capability_id: str = Field(min_length=1)

    scope: CapabilityScope
    scope_id: str

    revoked: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None
    metadata: dict[str, object] = Field(
        default_factory=dict
    )

    def is_expired(
        self,
        *,
        now: datetime | None = None,
    ) -> bool:
        if self.expires_at is None:
            return False

        current = now or utc_now()
        return current >= self.expires_at


class AuthorityRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str = Field(
        default_factory=lambda: str(uuid4())
    )
    subject_id: str = Field(min_length=1)
    capability_id: str = Field(min_length=1)

    scope: CapabilityScope
    scope_id: str

    resource: str | None = None
    action: str | None = None
    metadata: dict[str, object] = Field(
        default_factory=dict
    )


class AuthorityEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True)

    evaluation_id: str = Field(
        default_factory=lambda: str(uuid4())
    )
    request_id: str

    subject_id: str
    capability_id: str
    scope: CapabilityScope
    scope_id: str

    decision: AuthorityDecision
    allowed: bool = False

    matched_grant_id: str | None = None
    matched_delegation_id: str | None = None

    reason: str = ""
    evaluated_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, object] = Field(
        default_factory=dict
    )
