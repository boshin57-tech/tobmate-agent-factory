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

from .backup_models import (
    BackupError,
    BackupFileKind,
    BackupFileRecord,
    BackupIntegrityError,
    BackupManifest,
    BackupPlan,
    BackupPolicyError,
    BackupResult,
)

from .backup_service import (
    BackupService,
)

from .recovery_models import (
    RecoveryDrillReport,
    RecoveryDrillResult,
    RecoveryError,
    RecoveryIntegrityError,
    RecoveryPlan,
    RecoveryPolicyError,
    RecoveryResult,
    RecoveryVerification,
)

from .recovery_service import (
    RecoveryService,
)

from .operational_audit import (
    OperationalAuditCheck,
    OperationalAuditError,
    OperationalAuditMetric,
    OperationalAuditPlan,
    OperationalAuditPolicyError,
    OperationalAuditReport,
    OperationalAuditService,
    OperationalAuditStatus,
)

from .deployment_models import (
    DeploymentError,
    DeploymentFileKind,
    DeploymentFileRecord,
    DeploymentIntegrityError,
    DeploymentManifest,
    DeploymentPackagePlan,
    DeploymentPackageResult,
    DeploymentPolicyError,
    ReleaseIdentity,
    ReleasePackageInput,
)

from .deployment_package import (
    DeploymentPackageService,
)

from .process_models import (
    ProcessExitKind,
    ProcessIdentityRecord,
    ProcessOwnershipError,
    ProcessReadinessError,
    ProcessRestartLimitError,
    ProcessRestartRecord,
    ProcessSpecification,
    ProcessSupervisorError,
    ProcessSupervisorPolicyError,
    ProcessSupervisorSnapshot,
    ProcessSupervisorState,
    RestartMode,
    RestartPolicy,
    SystemdUnitSpecification,
)

from .process_identity import (
    ProcessIdentityManager,
)

from .process_supervisor import (
    ProcessSupervisor,
)

from .systemd_renderer import (
    SystemdUnitRenderer,
)

from .release_models import (
    ReleaseCommand,
    ReleaseCommandOutcome,
    ReleaseDrillReport,
    ReleaseDrillResult,
    ReleaseDrillStatus,
    ReleaseExecutionError,
    ReleaseMode,
    ReleasePhase,
    ReleaseRunbookError,
    ReleaseRunbookPlan,
    ReleaseRunbookPolicyError,
    ReleaseStepResult,
    ReleaseStepStatus,
)

from .release_runbook import (
    ReleaseRunbookService,
)
