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

from .service_runtime import (
    ServiceResource,
    ServiceRuntime,
    ServiceRuntimeError,
    ServiceRuntimeSnapshot,
    ServiceShutdownError,
    ServiceStartupError,
    ServiceState,
)

from .health import (
    HealthCheck,
    HealthEvaluation,
    HealthOutcome,
    HealthProbeResult,
    HealthRegistry,
    HealthRegistryError,
    HealthScope,
    HealthSnapshot,
    HealthStatus,
    ServiceRuntimeHealthAdapter,
)

from .metrics import (
    Counter,
    Gauge,
    Histogram,
    HistogramPoint,
    MetricPoint,
    MetricSnapshot,
    MetricsRegistry,
    MetricsRegistryError,
    MetricType,
    PROMETHEUS_CONTENT_TYPE,
    ServiceRuntimeMetricsAdapter,
)

from .probe_http import (
    JSON_CONTENT_TYPE,
    ProbeResponse,
    ServiceProbeApplication,
)

from .signals import (
    SignalBindingError,
    SignalShutdownController,
)
