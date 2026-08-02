"""Unified runtime policy registry."""

from __future__ import annotations

from threading import RLock

from af_core.runtime.runtime_policy_models import RuntimePolicy


class RuntimePolicyRegistryError(RuntimeError):
    pass


class RuntimePolicyRegistry:
    def __init__(self) -> None:
        self._policies: dict[str, RuntimePolicy] = {}
        self._lock = RLock()

    def register(
        self,
        policy: RuntimePolicy,
        *,
        replace: bool = False,
    ) -> RuntimePolicy:
        with self._lock:
            existing = self._policies.get(policy.policy_id)

            if existing is not None and not replace:
                raise RuntimePolicyRegistryError(
                    "Runtime policy already registered: "
                    f"{policy.policy_id}"
                )

            if (
                existing is not None
                and policy.version <= existing.version
            ):
                raise RuntimePolicyRegistryError(
                    "Replacement policy version must increase"
                )

            self._policies[policy.policy_id] = policy
            return policy

    def get(self, policy_id: str) -> RuntimePolicy:
        with self._lock:
            try:
                return self._policies[policy_id]
            except KeyError as exc:
                raise RuntimePolicyRegistryError(
                    f"Unknown runtime policy: {policy_id}"
                ) from exc

    def unregister(self, policy_id: str) -> RuntimePolicy:
        with self._lock:
            try:
                return self._policies.pop(policy_id)
            except KeyError as exc:
                raise RuntimePolicyRegistryError(
                    f"Unknown runtime policy: {policy_id}"
                ) from exc

    def list_policies(
        self,
        *,
        enabled_only: bool = False,
    ) -> tuple[RuntimePolicy, ...]:
        with self._lock:
            policies = tuple(self._policies.values())

        if enabled_only:
            policies = tuple(
                policy
                for policy in policies
                if policy.enabled
            )

        return tuple(
            sorted(
                policies,
                key=lambda policy: policy.policy_id,
            )
        )

    def __len__(self) -> int:
        with self._lock:
            return len(self._policies)
