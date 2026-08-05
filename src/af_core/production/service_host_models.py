"""Production service host configuration and lifecycle models."""

from __future__ import annotations

import os
import re
from enum import StrEnum
from typing import Mapping

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


_HOST_PATTERN = re.compile(
    r"^[A-Za-z0-9_.:-]+$"
)


class ServiceHostError(RuntimeError):
    """Base production service-host failure."""


class ServiceHostConfigurationError(
    ServiceHostError,
    ValueError,
):
    """Raised when service-host configuration is invalid."""


class ServiceHostStartupError(
    ServiceHostError,
):
    """Raised when the production host cannot start."""


class ServiceHostShutdownError(
    ServiceHostError,
):
    """Raised when the production host cannot stop safely."""


class ServiceHostState(StrEnum):
    """Observable production service-host states."""

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class ServiceHostSettings(BaseModel):
    """Validated non-secret settings for the production host."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    probe_enabled: bool = True

    probe_host: str = "127.0.0.1"

    probe_port: int = Field(
        default=8080,
        ge=0,
        le=65535,
    )

    request_timeout_seconds: float = Field(
        default=5.0,
        gt=0.0,
        le=300.0,
    )

    shutdown_timeout_seconds: float = Field(
        default=30.0,
        gt=0.0,
        le=600.0,
    )

    maximum_request_bytes: int = Field(
        default=8192,
        ge=1024,
        le=1048576,
    )

    backlog: int = Field(
        default=128,
        ge=1,
        le=4096,
    )

    @field_validator("probe_host")
    @classmethod
    def validate_probe_host(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if (
            not normalized
            or len(normalized) > 253
            or not _HOST_PATTERN.fullmatch(
                normalized
            )
        ):
            raise ValueError(
                "probe host is invalid"
            )

        return normalized

    @staticmethod
    def _parse_boolean(
        name: str,
        value: str,
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

        raise ServiceHostConfigurationError(
            f"{name} must be a boolean"
        )

    @classmethod
    def from_environment(
        cls,
        source: Mapping[str, str] | None = None,
        *,
        prefix: str = "AF_CORE_HOST_",
    ) -> "ServiceHostSettings":
        """Load validated host settings from an environment mapping."""

        environment = (
            os.environ
            if source is None
            else source
        )

        keys = {
            "probe_enabled":
                f"{prefix}PROBE_ENABLED",
            "probe_host":
                f"{prefix}PROBE_HOST",
            "probe_port":
                f"{prefix}PROBE_PORT",
            "request_timeout_seconds":
                f"{prefix}REQUEST_TIMEOUT_SECONDS",
            "shutdown_timeout_seconds":
                f"{prefix}SHUTDOWN_TIMEOUT_SECONDS",
            "maximum_request_bytes":
                f"{prefix}MAXIMUM_REQUEST_BYTES",
            "backlog":
                f"{prefix}BACKLOG",
        }

        allowed = set(keys.values())

        unknown = sorted(
            name
            for name in environment
            if (
                name.startswith(prefix)
                and name not in allowed
            )
        )

        if unknown:
            raise ServiceHostConfigurationError(
                "unknown service-host "
                "environment keys"
            )

        values: dict[str, object] = {}

        if keys["probe_enabled"] in environment:
            values["probe_enabled"] = (
                cls._parse_boolean(
                    keys["probe_enabled"],
                    environment[
                        keys["probe_enabled"]
                    ],
                )
            )

        string_fields = (
            "probe_host",
        )

        integer_fields = (
            "probe_port",
            "maximum_request_bytes",
            "backlog",
        )

        float_fields = (
            "request_timeout_seconds",
            "shutdown_timeout_seconds",
        )

        for field_name in string_fields:
            key = keys[field_name]

            if key in environment:
                values[field_name] = (
                    environment[key]
                )

        try:
            for field_name in integer_fields:
                key = keys[field_name]

                if key in environment:
                    values[field_name] = int(
                        environment[key]
                    )

            for field_name in float_fields:
                key = keys[field_name]

                if key in environment:
                    values[field_name] = float(
                        environment[key]
                    )

            return cls.model_validate(values)

        except ValueError as exc:
            raise ServiceHostConfigurationError(
                "service-host environment "
                "configuration is invalid"
            ) from exc

    def public_snapshot(
        self,
    ) -> dict[str, object]:
        """Return a credential-free host configuration snapshot."""

        return {
            "probe_enabled":
                self.probe_enabled,
            "probe_host":
                self.probe_host,
            "probe_port":
                self.probe_port,
            "request_timeout_seconds":
                self.request_timeout_seconds,
            "shutdown_timeout_seconds":
                self.shutdown_timeout_seconds,
            "maximum_request_bytes":
                self.maximum_request_bytes,
            "backlog":
                self.backlog,
        }

class ServiceHostSnapshot(BaseModel):
    """Immutable credential-free service-host state."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    state: ServiceHostState

    service_name: str = Field(
        min_length=1,
        max_length=128,
    )

    instance_id: str = Field(
        min_length=1,
        max_length=128,
    )

    runtime_state: str = Field(
        min_length=1,
        max_length=64,
    )

    probe_enabled: bool

    configured_probe_host: str = Field(
        min_length=1,
        max_length=253,
    )

    configured_probe_port: int = Field(
        ge=0,
        le=65535,
    )

    bound_probe_host: str | None = None

    bound_probe_port: int | None = Field(
        default=None,
        ge=1,
        le=65535,
    )

    signal_controller_installed: bool = False

    shutdown_reason: str | None = Field(
        default=None,
        max_length=256,
    )

    @field_validator(
        "service_name",
        "instance_id",
        "runtime_state",
    )
    @classmethod
    def validate_identifier(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "service-host identifier "
                "must not be empty"
            )

        return normalized

    @field_validator("shutdown_reason")
    @classmethod
    def validate_shutdown_reason(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "shutdown reason must not be empty"
            )

        return normalized
