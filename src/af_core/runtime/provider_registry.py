from __future__ import annotations

from collections.abc import Iterable

from .provider_protocol import (
    ProviderAdapter,
    ProviderCapability,
)


class ProviderRegistryError(RuntimeError):
    """Raised for invalid provider registration or lookup."""


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ProviderAdapter] = {}

    def register(
        self,
        provider: ProviderAdapter,
    ) -> None:
        provider_id = provider.provider_id.strip()

        if not provider_id:
            raise ProviderRegistryError(
                "Provider ID is required."
            )

        if provider_id in self._providers:
            raise ProviderRegistryError(
                f"Provider already registered: {provider_id}"
            )

        self._providers[provider_id] = provider

    def unregister(
        self,
        provider_id: str,
    ) -> None:
        if provider_id not in self._providers:
            raise ProviderRegistryError(
                f"Provider not registered: {provider_id}"
            )

        del self._providers[provider_id]

    def get(
        self,
        provider_id: str,
    ) -> ProviderAdapter:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise ProviderRegistryError(
                f"Unknown provider: {provider_id}"
            ) from exc

    def list(self) -> list[ProviderAdapter]:
        return [
            self._providers[key]
            for key in sorted(self._providers)
        ]

    def find_by_capabilities(
        self,
        required: Iterable[ProviderCapability],
    ) -> list[ProviderAdapter]:
        required_set = set(required)

        return [
            provider
            for provider in self.list()
            if required_set.issubset(
                provider.capabilities
            )
        ]

    def contains(
        self,
        provider_id: str,
    ) -> bool:
        return provider_id in self._providers
