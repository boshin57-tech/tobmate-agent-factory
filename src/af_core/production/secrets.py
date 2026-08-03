"""Secret references, environment filtering and safe redaction."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


_ENVIRONMENT_KEY_PATTERN = re.compile(
    r"^[A-Z_][A-Z0-9_]*$"
)

_SENSITIVE_KEY_MARKERS = (
    "authorization",
    "credential",
    "cookie",
    "private_key",
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
)

_BEARER_PATTERN = re.compile(
    r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"
)

_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b("
    r"password|passwd|secret|token|"
    r"api[_-]?key|authorization"
    r")\s*([=:])\s*([^\s,;]+)"
)

_URL_CREDENTIAL_PATTERN = re.compile(
    r"(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*://)"
    r"(?P<user>[^:/@\s]+):"
    r"(?P<password>[^@\s]+)@"
)


class SecretResolutionError(RuntimeError):
    """Raised when a required external secret cannot be resolved."""


def validate_environment_key(value: str) -> str:
    """Validate and normalize an environment-variable name."""

    normalized = value.strip().upper()

    if not _ENVIRONMENT_KEY_PATTERN.fullmatch(
        normalized
    ):
        raise ValueError(
            "environment key must contain only "
            "uppercase letters, digits and underscores"
        )

    return normalized


class SecretReference(BaseModel):
    """A reference to a secret without storing its value."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    environment_key: str
    required: bool = True

    @field_validator("environment_key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        return validate_environment_key(value)

    def resolve(
        self,
        source: Mapping[str, str] | None = None,
    ) -> str | None:
        environment = (
            os.environ
            if source is None
            else source
        )

        value = environment.get(
            self.environment_key
        )

        if value is None or value == "":
            if self.required:
                raise SecretResolutionError(
                    "required secret is unavailable: "
                    f"{self.environment_key}"
                )

            return None

        return value


def is_sensitive_key(
    key: str,
    *,
    explicit_keys: Sequence[str] = (),
) -> bool:
    """Return whether a mapping key is secret-bearing."""

    normalized = key.strip().lower().replace(
        "-",
        "_",
    )

    explicit = {
        item.strip().lower()
        for item in explicit_keys
    }

    if normalized in explicit:
        return True

    return any(
        marker in normalized
        for marker in _SENSITIVE_KEY_MARKERS
    )


def redact_text(
    text: str,
    *,
    known_secrets: Sequence[str] = (),
    replacement: str = "[REDACTED]",
) -> str:
    """Redact known and commonly formatted secrets."""

    redacted = text

    for secret in sorted(
        {
            secret
            for secret in known_secrets
            if secret
        },
        key=len,
        reverse=True,
    ):
        redacted = redacted.replace(
            secret,
            replacement,
        )

    redacted = _BEARER_PATTERN.sub(
        f"Bearer {replacement}",
        redacted,
    )

    redacted = _ASSIGNMENT_PATTERN.sub(
        lambda match: (
            f"{match.group(1)}"
            f"{match.group(2)}"
            f"{replacement}"
        ),
        redacted,
    )

    redacted = _URL_CREDENTIAL_PATTERN.sub(
        lambda match: (
            f"{match.group('scheme')}"
            f"{match.group('user')}:"
            f"{replacement}@"
        ),
        redacted,
    )

    return redacted


def redact_structure(
    value: Any,
    *,
    explicit_keys: Sequence[str] = (),
    known_secrets: Sequence[str] = (),
    replacement: str = "[REDACTED]",
) -> Any:
    """Recursively redact structured diagnostic data."""

    if isinstance(value, Mapping):
        result: dict[Any, Any] = {}

        for key, item in value.items():
            if is_sensitive_key(
                str(key),
                explicit_keys=explicit_keys,
            ):
                result[key] = replacement
            else:
                result[key] = redact_structure(
                    item,
                    explicit_keys=explicit_keys,
                    known_secrets=known_secrets,
                    replacement=replacement,
                )

        return result

    if isinstance(value, tuple):
        return tuple(
            redact_structure(
                item,
                explicit_keys=explicit_keys,
                known_secrets=known_secrets,
                replacement=replacement,
            )
            for item in value
        )

    if isinstance(value, list):
        return [
            redact_structure(
                item,
                explicit_keys=explicit_keys,
                known_secrets=known_secrets,
                replacement=replacement,
            )
            for item in value
        ]

    if isinstance(value, set):
        return {
            redact_structure(
                item,
                explicit_keys=explicit_keys,
                known_secrets=known_secrets,
                replacement=replacement,
            )
            for item in value
        }

    if isinstance(value, str):
        return redact_text(
            value,
            known_secrets=known_secrets,
            replacement=replacement,
        )

    return value


def sanitized_environment(
    source: Mapping[str, str],
    *,
    allowed_keys: Sequence[str],
    secret_keys: Sequence[str] = (),
) -> dict[str, str]:
    """Build a minimal non-secret subprocess environment."""

    allowed = {
        validate_environment_key(key)
        for key in allowed_keys
    }

    secrets = {
        validate_environment_key(key)
        for key in secret_keys
    }

    return {
        key: value
        for key, value in source.items()
        if key in allowed and key not in secrets
    }
