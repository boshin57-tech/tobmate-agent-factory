"""Capability registry."""

from __future__ import annotations

from threading import RLock

from af_core.runtime.capability_models import (
    CapabilityDefinition,
)


class CapabilityRegistryError(RuntimeError):
    pass


class CapabilityRegistry:
    def __init__(self) -> None:
        self._capabilities: dict[
            str,
            CapabilityDefinition,
        ] = {}
        self._lock = RLock()

    def register(
        self,
        capability: CapabilityDefinition,
        *,
        replace: bool = False,
    ) -> CapabilityDefinition:
        with self._lock:
            existing = self._capabilities.get(
                capability.capability_id
            )

            if existing is not None and not replace:
                raise CapabilityRegistryError(
                    "Capability already registered: "
                    f"{capability.capability_id}"
                )

            parent_id = (
                capability.parent_capability_id
            )

            if (
                parent_id is not None
                and parent_id not in self._capabilities
            ):
                raise CapabilityRegistryError(
                    "Unknown parent capability: "
                    f"{parent_id}"
                )

            self._capabilities[
                capability.capability_id
            ] = capability

            return capability

    def get(
        self,
        capability_id: str,
    ) -> CapabilityDefinition:
        with self._lock:
            try:
                return self._capabilities[
                    capability_id
                ]
            except KeyError as exc:
                raise CapabilityRegistryError(
                    f"Unknown capability: {capability_id}"
                ) from exc

    def unregister(
        self,
        capability_id: str,
    ) -> CapabilityDefinition:
        with self._lock:
            children = [
                item.capability_id
                for item in self._capabilities.values()
                if item.parent_capability_id
                == capability_id
            ]

            if children:
                raise CapabilityRegistryError(
                    "Capability has registered children: "
                    + ", ".join(sorted(children))
                )

            try:
                return self._capabilities.pop(
                    capability_id
                )
            except KeyError as exc:
                raise CapabilityRegistryError(
                    f"Unknown capability: {capability_id}"
                ) from exc

    def list_capabilities(
        self,
        *,
        enabled_only: bool = False,
    ) -> tuple[CapabilityDefinition, ...]:
        with self._lock:
            capabilities = tuple(
                self._capabilities.values()
            )

        if enabled_only:
            capabilities = tuple(
                item
                for item in capabilities
                if item.enabled
            )

        return tuple(
            sorted(
                capabilities,
                key=lambda item: item.capability_id,
            )
        )

    def inheritance_chain(
        self,
        capability_id: str,
    ) -> tuple[CapabilityDefinition, ...]:
        chain: list[CapabilityDefinition] = []
        current = self.get(capability_id)
        visited: set[str] = set()

        while True:
            if current.capability_id in visited:
                raise CapabilityRegistryError(
                    "Capability inheritance cycle detected"
                )

            visited.add(current.capability_id)
            chain.append(current)

            if current.parent_capability_id is None:
                break

            current = self.get(
                current.parent_capability_id
            )

        return tuple(chain)

    def inherits_from(
        self,
        capability_id: str,
        parent_capability_id: str,
    ) -> bool:
        return any(
            item.capability_id
            == parent_capability_id
            for item in self.inheritance_chain(
                capability_id
            )[1:]
        )

    def __len__(self) -> int:
        with self._lock:
            return len(self._capabilities)
