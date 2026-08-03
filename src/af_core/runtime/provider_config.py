from __future__ import annotations

import json
import os
from pathlib import Path
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field, field_validator

from af_core.production import (
    SecretReference,
    redact_structure,
    redact_text,
    validate_environment_key,
)


class ProviderEndpointConfig(BaseModel):
    provider_id: str
    base_url: str
    api_key_environment: str | None = None
    timeout_seconds: float = Field(
        default=120.0,
        gt=0,
        le=1800,
    )
    maximum_retries: int = Field(
        default=1,
        ge=0,
        le=10,
    )
    enabled: bool = True
    headers: dict[str, str] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("api_key_environment")
    @classmethod
    def validate_api_key_environment(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        return validate_environment_key(value)

    def secret_reference(
        self,
    ) -> SecretReference | None:
        if self.api_key_environment is None:
            return None

        return SecretReference(
            environment_key=self.api_key_environment,
            required=False,
        )

    def api_key(
        self,
        source: Mapping[str, str] | None = None,
    ) -> str | None:
        reference = self.secret_reference()

        if reference is None:
            return None

        return reference.resolve(
            os.environ if source is None else source
        )

    def resolved_headers(
        self,
        source: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        headers = dict(self.headers)
        api_key = self.api_key(source)

        if api_key is not None:
            headers.setdefault(
                "Authorization",
                f"Bearer {api_key}",
            )

        return headers

    def public_snapshot(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")

        payload["base_url"] = redact_text(
            str(payload["base_url"])
        )

        payload["headers"] = redact_structure(
            payload["headers"]
        )

        payload["options"] = redact_structure(
            payload["options"]
        )

        return payload


class ProviderRuntimeConfig(BaseModel):
    providers: dict[str, ProviderEndpointConfig] = Field(
        default_factory=dict
    )

    def get(
        self,
        provider_id: str,
    ) -> ProviderEndpointConfig:
        try:
            config = self.providers[provider_id]
        except KeyError as exc:
            raise ValueError(
                f"Provider configuration not found: {provider_id}"
            ) from exc

        if not config.enabled:
            raise ValueError(
                f"Provider is disabled: {provider_id}"
            )

        return config

    def public_snapshot(self) -> dict[str, Any]:
        return {
            "providers": {
                provider_id: config.public_snapshot()
                for provider_id, config
                in self.providers.items()
            }
        }

    @classmethod
    def from_json_file(
        cls,
        path: str | Path,
    ) -> "ProviderRuntimeConfig":
        target = Path(path).expanduser().resolve()

        if not target.is_file():
            raise FileNotFoundError(
                f"Provider configuration not found: {target}"
            )

        return cls.model_validate_json(
            target.read_text(encoding="utf-8")
        )

    def write_template(
        self,
        path: str | Path,
    ) -> Path:
        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        temporary = target.with_suffix(
            target.suffix + ".tmp"
        )
        temporary.write_text(
            json.dumps(
                self.public_snapshot(),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)

        return target
