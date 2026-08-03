"""AF-Core production configuration and secret boundaries."""

from .configuration import (
    DeploymentEnvironment,
    ProductionConfigurationError,
    ProductionSettings,
)
from .secrets import (
    SecretReference,
    SecretResolutionError,
    is_sensitive_key,
    redact_structure,
    redact_text,
    sanitized_environment,
    validate_environment_key,
)

__all__ = [
    "DeploymentEnvironment",
    "ProductionConfigurationError",
    "ProductionSettings",
    "SecretReference",
    "SecretResolutionError",
    "is_sensitive_key",
    "redact_structure",
    "redact_text",
    "sanitized_environment",
    "validate_environment_key",
]
