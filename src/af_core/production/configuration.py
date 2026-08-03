"""Typed and validated AF-Core production configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from .secrets import (
    redact_structure,
    validate_environment_key,
)


class ProductionConfigurationError(ValueError):
    """Raised when deployment configuration is invalid."""


class DeploymentEnvironment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


_ENVIRONMENT_FIELDS = {
    "ENVIRONMENT": "environment",
    "SERVICE_NAME": "service_name",
    "INSTANCE_ID": "instance_id",
    "DATA_DIR": "data_dir",
    "ARTIFACT_DIR": "artifact_dir",
    "DATABASE_URL": "database_url",
    "LOG_LEVEL": "log_level",
    "COMMAND_TIMEOUT_SECONDS": (
        "command_timeout_seconds"
    ),
    "MCP_TIMEOUT_SECONDS": (
        "mcp_timeout_seconds"
    ),
    "MAX_CONCURRENCY": "max_concurrency",
    "ALLOWED_ENVIRONMENT_KEYS": (
        "allowed_environment_keys"
    ),
    "SECRET_ENVIRONMENT_KEYS": (
        "secret_environment_keys"
    ),
    "INHERIT_PARENT_ENVIRONMENT": (
        "inherit_parent_environment"
    ),
}

_SEQUENCE_FIELDS = {
    "ALLOWED_ENVIRONMENT_KEYS",
    "SECRET_ENVIRONMENT_KEYS",
}

_BOOLEAN_FIELDS = {
    "INHERIT_PARENT_ENVIRONMENT",
}

_ALLOWED_LOG_LEVELS = {
    "CRITICAL",
    "ERROR",
    "WARNING",
    "INFO",
    "DEBUG",
}


def _parse_boolean(
    value: str,
    *,
    variable_name: str,
) -> bool:
    normalized = value.strip().lower()

    if normalized in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True

    if normalized in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False

    raise ProductionConfigurationError(
        f"{variable_name} must be a boolean value"
    )


class ProductionSettings(BaseModel):
    """Immutable AF-Core process configuration."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    environment: DeploymentEnvironment = (
        DeploymentEnvironment.DEVELOPMENT
    )

    service_name: str = "af-core"
    instance_id: str = "local"

    data_dir: Path = Path(
        "./var/lib/af-core"
    )
    artifact_dir: Path = Path(
        "./var/lib/af-core/artifacts"
    )

    database_url: str = (
        "sqlite:///./var/lib/af-core/af-core.db"
    )

    log_level: str = "INFO"

    command_timeout_seconds: int = Field(
        default=60,
        ge=1,
        le=3600,
    )

    mcp_timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        le=3600,
    )

    max_concurrency: int = Field(
        default=4,
        ge=1,
        le=128,
    )

    allowed_environment_keys: tuple[str, ...] = (
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "TMPDIR",
    )

    secret_environment_keys: tuple[str, ...] = ()

    inherit_parent_environment: bool = False

    @field_validator(
        "service_name",
        "instance_id",
        "database_url",
    )
    @classmethod
    def validate_non_empty(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "configuration value must not be empty"
            )

        return normalized

    @field_validator("log_level")
    @classmethod
    def validate_log_level(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().upper()

        if normalized not in _ALLOWED_LOG_LEVELS:
            raise ValueError(
                "unsupported log level"
            )

        return normalized

    @field_validator(
        "allowed_environment_keys",
        "secret_environment_keys",
    )
    @classmethod
    def validate_environment_keys(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        normalized: list[str] = []

        for value in values:
            key = validate_environment_key(value)

            if key not in normalized:
                normalized.append(key)

        return tuple(normalized)

    @model_validator(mode="after")
    def validate_environment_contract(
        self,
    ) -> "ProductionSettings":
        overlap = (
            set(self.allowed_environment_keys)
            & set(self.secret_environment_keys)
        )

        if overlap:
            raise ValueError(
                "allowed and secret environment keys "
                "must not overlap: "
                + ", ".join(sorted(overlap))
            )

        if (
            self.environment
            is DeploymentEnvironment.PRODUCTION
        ):
            if self.instance_id.lower() in {
                "local",
                "development",
                "dev",
                "test",
            }:
                raise ValueError(
                    "production instance_id must be "
                    "deployment-specific"
                )

            if not self.data_dir.is_absolute():
                raise ValueError(
                    "production data_dir must be absolute"
                )

            if not self.artifact_dir.is_absolute():
                raise ValueError(
                    "production artifact_dir "
                    "must be absolute"
                )

            if self.database_url.lower().startswith(
                "sqlite:"
            ):
                raise ValueError(
                    "production database_url must use "
                    "an external durable database"
                )

            if self.inherit_parent_environment:
                raise ValueError(
                    "production processes must not inherit "
                    "the complete parent environment"
                )

        return self

    @classmethod
    def from_environment(
        cls,
        source: Mapping[str, str] | None = None,
        *,
        prefix: str = "AF_CORE_",
    ) -> "ProductionSettings":
        """Load only declared AF-Core environment variables."""

        environment = (
            os.environ
            if source is None
            else source
        )

        unknown = sorted(
            key
            for key in environment
            if key.startswith(prefix)
            and key[len(prefix):]
            not in _ENVIRONMENT_FIELDS
        )

        if unknown:
            raise ProductionConfigurationError(
                "unknown AF-Core environment variables: "
                + ", ".join(unknown)
            )

        payload: dict[str, Any] = {}

        for suffix, field_name in (
            _ENVIRONMENT_FIELDS.items()
        ):
            variable_name = f"{prefix}{suffix}"

            if variable_name not in environment:
                continue

            value = environment[variable_name]

            if suffix in _SEQUENCE_FIELDS:
                payload[field_name] = tuple(
                    item.strip()
                    for item in value.split(",")
                    if item.strip()
                )
            elif suffix in _BOOLEAN_FIELDS:
                payload[field_name] = _parse_boolean(
                    value,
                    variable_name=variable_name,
                )
            else:
                payload[field_name] = value

        try:
            return cls.model_validate(payload)
        except ValidationError as exc:
            raise ProductionConfigurationError(
                str(exc)
            ) from exc

    def public_snapshot(self) -> dict[str, Any]:
        """Return configuration safe for logs and diagnostics."""

        return redact_structure(
            self.model_dump(mode="json"),
            explicit_keys=(
                "secret_environment_keys",
            ),
        )
