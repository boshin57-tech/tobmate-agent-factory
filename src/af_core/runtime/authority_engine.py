"""Capability authority grant and delegation engine."""

from __future__ import annotations

from datetime import datetime
from threading import RLock

from af_core.runtime.capability_models import (
    AuthorityDecision,
    AuthorityDelegation,
    AuthorityEvaluation,
    AuthorityGrant,
    AuthorityRequest,
    CapabilityScope,
)
from af_core.runtime.capability_registry import (
    CapabilityRegistry,
    CapabilityRegistryError,
)


class AuthorityEngineError(RuntimeError):
    pass


class AuthorityEngine:
    def __init__(
        self,
        *,
        capabilities: CapabilityRegistry,
    ) -> None:
        self._capabilities = capabilities
        self._grants: dict[str, AuthorityGrant] = {}
        self._delegations: dict[
            str,
            AuthorityDelegation,
        ] = {}
        self._history: list[AuthorityEvaluation] = []
        self._lock = RLock()

    def grant(
        self,
        grant: AuthorityGrant,
    ) -> AuthorityGrant:
        self._require_capability(grant.capability_id)

        with self._lock:
            if grant.grant_id in self._grants:
                raise AuthorityEngineError(
                    "Authority grant already exists: "
                    f"{grant.grant_id}"
                )

            self._grants[grant.grant_id] = grant
            return grant

    def revoke_grant(
        self,
        grant_id: str,
    ) -> AuthorityGrant:
        with self._lock:
            grant = self._get_grant(grant_id)

            revoked = grant.model_copy(
                update={"revoked": True}
            )
            self._grants[grant_id] = revoked
            return revoked

    def delegate(
        self,
        delegation: AuthorityDelegation,
    ) -> AuthorityDelegation:
        self._require_capability(
            delegation.capability_id
        )

        with self._lock:
            parent = self._get_grant(
                delegation.parent_grant_id
            )

            if parent.revoked:
                raise AuthorityEngineError(
                    "Cannot delegate a revoked grant"
                )

            if parent.is_expired():
                raise AuthorityEngineError(
                    "Cannot delegate an expired grant"
                )

            if not parent.delegable:
                raise AuthorityEngineError(
                    "Authority grant is not delegable"
                )

            if parent.subject_id != delegation.delegated_by:
                raise AuthorityEngineError(
                    "Delegator does not own parent grant"
                )

            if not self._capability_matches(
                granted=parent.capability_id,
                requested=delegation.capability_id,
            ):
                raise AuthorityEngineError(
                    "Delegated capability exceeds "
                    "parent grant"
                )

            if not self._scope_contains(
                grant_scope=parent.scope,
                grant_scope_id=parent.scope_id,
                request_scope=delegation.scope,
                request_scope_id=delegation.scope_id,
            ):
                raise AuthorityEngineError(
                    "Delegated scope exceeds parent grant"
                )

            if (
                delegation.delegation_id
                in self._delegations
            ):
                raise AuthorityEngineError(
                    "Authority delegation already exists: "
                    f"{delegation.delegation_id}"
                )

            self._delegations[
                delegation.delegation_id
            ] = delegation

            return delegation

    def revoke_delegation(
        self,
        delegation_id: str,
    ) -> AuthorityDelegation:
        with self._lock:
            try:
                delegation = self._delegations[
                    delegation_id
                ]
            except KeyError as exc:
                raise AuthorityEngineError(
                    "Unknown authority delegation: "
                    f"{delegation_id}"
                ) from exc

            revoked = delegation.model_copy(
                update={"revoked": True}
            )
            self._delegations[
                delegation_id
            ] = revoked
            return revoked

    def evaluate(
        self,
        request: AuthorityRequest,
        *,
        now: datetime | None = None,
    ) -> AuthorityEvaluation:
        self._require_capability(
            request.capability_id
        )

        with self._lock:
            grants = tuple(self._grants.values())
            delegations = tuple(
                self._delegations.values()
            )

        for grant in grants:
            if grant.subject_id != request.subject_id:
                continue

            evaluation = self._evaluate_grant(
                grant,
                request,
                now=now,
            )

            if evaluation is not None:
                return self._record(evaluation)

        for delegation in delegations:
            if (
                delegation.delegated_to
                != request.subject_id
            ):
                continue

            evaluation = self._evaluate_delegation(
                delegation,
                request,
                now=now,
            )

            if evaluation is not None:
                return self._record(evaluation)

        return self._record(
            AuthorityEvaluation(
                request_id=request.request_id,
                subject_id=request.subject_id,
                capability_id=request.capability_id,
                scope=request.scope,
                scope_id=request.scope_id,
                decision=AuthorityDecision.NOT_GRANTED,
                allowed=False,
                reason="No matching authority grant",
            )
        )

    def list_grants(
        self,
    ) -> tuple[AuthorityGrant, ...]:
        with self._lock:
            return tuple(self._grants.values())

    def list_delegations(
        self,
    ) -> tuple[AuthorityDelegation, ...]:
        with self._lock:
            return tuple(self._delegations.values())

    def history(
        self,
    ) -> tuple[AuthorityEvaluation, ...]:
        with self._lock:
            return tuple(self._history)

    def _evaluate_grant(
        self,
        grant: AuthorityGrant,
        request: AuthorityRequest,
        *,
        now: datetime | None,
    ) -> AuthorityEvaluation | None:
        if not self._capability_matches(
            granted=grant.capability_id,
            requested=request.capability_id,
        ):
            return None

        if grant.revoked:
            return self._evaluation(
                request,
                AuthorityDecision.REVOKED,
                reason="Matching authority grant is revoked",
                grant_id=grant.grant_id,
            )

        if grant.is_expired(now=now):
            return self._evaluation(
                request,
                AuthorityDecision.EXPIRED,
                reason="Matching authority grant is expired",
                grant_id=grant.grant_id,
            )

        if not self._scope_contains(
            grant_scope=grant.scope,
            grant_scope_id=grant.scope_id,
            request_scope=request.scope,
            request_scope_id=request.scope_id,
        ):
            return self._evaluation(
                request,
                AuthorityDecision.OUT_OF_SCOPE,
                reason="Requested scope exceeds grant scope",
                grant_id=grant.grant_id,
            )

        return self._evaluation(
            request,
            AuthorityDecision.ALLOW,
            reason="Direct authority grant matched",
            grant_id=grant.grant_id,
            allowed=True,
        )

    def _evaluate_delegation(
        self,
        delegation: AuthorityDelegation,
        request: AuthorityRequest,
        *,
        now: datetime | None,
    ) -> AuthorityEvaluation | None:
        if not self._capability_matches(
            granted=delegation.capability_id,
            requested=request.capability_id,
        ):
            return None

        if delegation.revoked:
            return self._evaluation(
                request,
                AuthorityDecision.REVOKED,
                reason="Matching delegation is revoked",
                delegation_id=(
                    delegation.delegation_id
                ),
            )

        if delegation.is_expired(now=now):
            return self._evaluation(
                request,
                AuthorityDecision.EXPIRED,
                reason="Matching delegation is expired",
                delegation_id=(
                    delegation.delegation_id
                ),
            )

        if not self._scope_contains(
            grant_scope=delegation.scope,
            grant_scope_id=delegation.scope_id,
            request_scope=request.scope,
            request_scope_id=request.scope_id,
        ):
            return self._evaluation(
                request,
                AuthorityDecision.OUT_OF_SCOPE,
                reason="Requested scope exceeds delegation",
                delegation_id=(
                    delegation.delegation_id
                ),
            )

        return self._evaluation(
            request,
            AuthorityDecision.DELEGATED,
            reason="Delegated authority matched",
            delegation_id=delegation.delegation_id,
            allowed=True,
        )

    def _capability_matches(
        self,
        *,
        granted: str,
        requested: str,
    ) -> bool:
        if granted == requested:
            return True

        try:
            return self._capabilities.inherits_from(
                requested,
                granted,
            )
        except CapabilityRegistryError:
            return False

    @staticmethod
    def _scope_contains(
        *,
        grant_scope: CapabilityScope,
        grant_scope_id: str,
        request_scope: CapabilityScope,
        request_scope_id: str,
    ) -> bool:
        if grant_scope is CapabilityScope.GLOBAL:
            return True

        return (
            grant_scope is request_scope
            and grant_scope_id == request_scope_id
        )

    def _require_capability(
        self,
        capability_id: str,
    ) -> None:
        self._capabilities.get(capability_id)

    def _get_grant(
        self,
        grant_id: str,
    ) -> AuthorityGrant:
        try:
            return self._grants[grant_id]
        except KeyError as exc:
            raise AuthorityEngineError(
                f"Unknown authority grant: {grant_id}"
            ) from exc

    def _record(
        self,
        evaluation: AuthorityEvaluation,
    ) -> AuthorityEvaluation:
        with self._lock:
            self._history.append(evaluation)

        return evaluation

    @staticmethod
    def _evaluation(
        request: AuthorityRequest,
        decision: AuthorityDecision,
        *,
        reason: str,
        grant_id: str | None = None,
        delegation_id: str | None = None,
        allowed: bool = False,
    ) -> AuthorityEvaluation:
        return AuthorityEvaluation(
            request_id=request.request_id,
            subject_id=request.subject_id,
            capability_id=request.capability_id,
            scope=request.scope,
            scope_id=request.scope_id,
            decision=decision,
            allowed=allowed,
            matched_grant_id=grant_id,
            matched_delegation_id=delegation_id,
            reason=reason,
        )
