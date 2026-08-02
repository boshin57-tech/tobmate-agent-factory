from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .models import (
    ExternalToolRisk,
    ExternalToolTransport,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ToolTrustLevel(StrEnum):
    UNTRUSTED = "UNTRUSTED"
    COMMUNITY = "COMMUNITY"
    VERIFIED = "VERIFIED"
    FIRST_PARTY = "FIRST_PARTY"
    SYSTEM = "SYSTEM"


class ToolInstallationState(StrEnum):
    NOT_INSTALLED = "NOT_INSTALLED"
    INSTALLING = "INSTALLING"
    INSTALLED = "INSTALLED"
    DISABLED = "DISABLED"
    FAILED = "FAILED"
    REMOVED = "REMOVED"


class ToolHealthState(StrEnum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    INCOMPATIBLE = "INCOMPATIBLE"


class CompatibilityStatus(StrEnum):
    COMPATIBLE = "COMPATIBLE"
    PARTIALLY_COMPATIBLE = "PARTIALLY_COMPATIBLE"
    INCOMPATIBLE = "INCOMPATIBLE"
    UNKNOWN = "UNKNOWN"


class CapabilityKind(StrEnum):
    FILESYSTEM = "FILESYSTEM"
    GIT = "GIT"
    SHELL = "SHELL"
    DATABASE = "DATABASE"
    BROWSER = "BROWSER"
    NETWORK = "NETWORK"
    CLOUD = "CLOUD"
    MESSAGING = "MESSAGING"
    PROJECT_MANAGEMENT = "PROJECT_MANAGEMENT"
    DESIGN = "DESIGN"
    BLOCKCHAIN = "BLOCKCHAIN"
    GSOS = "GSOS"
    TMID = "TMID"
    KNOWLEDGE = "KNOWLEDGE"
    CODE_ANALYSIS = "CODE_ANALYSIS"
    TESTING = "TESTING"
    DEPLOYMENT = "DEPLOYMENT"
    SECURITY = "SECURITY"
    OBSERVABILITY = "OBSERVABILITY"
    CUSTOM = "CUSTOM"


class ToolCapability(BaseModel):
    capability_id: str
    kind: CapabilityKind
    name: str
    description: str = ""
    operations: set[str] = Field(
        default_factory=set
    )
    tags: set[str] = Field(
        default_factory=set
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict
    )


class ToolVersionConstraint(BaseModel):
    minimum_version: str | None = None
    maximum_version: str | None = None
    exact_version: str | None = None


class ToolCompatibility(BaseModel):
    status: CompatibilityStatus = (
        CompatibilityStatus.UNKNOWN
    )
    af_core_version: ToolVersionConstraint | None = None
    protocol_version: ToolVersionConstraint | None = None
    python_version: ToolVersionConstraint | None = None
    operating_systems: set[str] = Field(
        default_factory=set
    )
    architectures: set[str] = Field(
        default_factory=set
    )
    reasons: list[str] = Field(
        default_factory=list
    )


class ToolManifest(BaseModel):
    tool_id: str
    name: str
    version: str
    description: str = ""
    provider_id: str | None = None
    server_id: str | None = None
    transport: ExternalToolTransport = (
        ExternalToolTransport.INTERNAL
    )
    risk: ExternalToolRisk = (
        ExternalToolRisk.READ_ONLY
    )
    trust_level: ToolTrustLevel = (
        ToolTrustLevel.UNTRUSTED
    )
    capabilities: list[ToolCapability] = Field(
        default_factory=list
    )
    required_permissions: set[str] = Field(
        default_factory=set
    )
    allowed_roles: set[str] = Field(
        default_factory=set
    )
    tags: set[str] = Field(
        default_factory=set
    )
    homepage: str | None = None
    source_repository: str | None = None
    documentation_uri: str | None = None
    license: str | None = None
    checksum: str | None = None
    signature: str | None = None
    compatibility: ToolCompatibility = Field(
        default_factory=ToolCompatibility
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict
    )


class MCPServerManifest(BaseModel):
    server_id: str
    name: str
    version: str
    description: str = ""
    transport: ExternalToolTransport
    command: str | None = None
    arguments: list[str] = Field(
        default_factory=list
    )
    url: str | None = None
    environment_keys: set[str] = Field(
        default_factory=set
    )
    header_keys: set[str] = Field(
        default_factory=set
    )
    trust_level: ToolTrustLevel = (
        ToolTrustLevel.UNTRUSTED
    )
    capabilities: list[ToolCapability] = Field(
        default_factory=list
    )
    declared_tools: list[str] = Field(
        default_factory=list
    )
    declared_resources: list[str] = Field(
        default_factory=list
    )
    declared_prompts: list[str] = Field(
        default_factory=list
    )
    homepage: str | None = None
    source_repository: str | None = None
    documentation_uri: str | None = None
    checksum: str | None = None
    signature: str | None = None
    compatibility: ToolCompatibility = Field(
        default_factory=ToolCompatibility
    )
    tags: set[str] = Field(
        default_factory=set
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict
    )


class ToolInstallationRecord(BaseModel):
    ecosystem_id: str
    state: ToolInstallationState = (
        ToolInstallationState.NOT_INSTALLED
    )
    installed_version: str | None = None
    installed_at: datetime | None = None
    updated_at: datetime = Field(
        default_factory=utc_now
    )
    error: str | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict
    )


class ToolHealthRecord(BaseModel):
    ecosystem_id: str
    state: ToolHealthState = (
        ToolHealthState.UNKNOWN
    )
    checked_at: datetime = Field(
        default_factory=utc_now
    )
    latency_ms: float | None = Field(
        default=None,
        ge=0,
    )
    message: str = ""
    metadata: dict[str, Any] = Field(
        default_factory=dict
    )


class AgentToolRequirement(BaseModel):
    role: str
    required_capabilities: set[str] = Field(
        default_factory=set
    )
    optional_capabilities: set[str] = Field(
        default_factory=set
    )
    maximum_risk: ExternalToolRisk = (
        ExternalToolRisk.WORKSPACE_WRITE
    )
    minimum_trust_level: ToolTrustLevel = (
        ToolTrustLevel.VERIFIED
    )
    required_tags: set[str] = Field(
        default_factory=set
    )
    denied_tags: set[str] = Field(
        default_factory=set
    )


class ProjectToolBundle(BaseModel):
    bundle_id: str
    project_id: str
    name: str
    description: str = ""
    tool_ids: list[str] = Field(
        default_factory=list
    )
    server_ids: list[str] = Field(
        default_factory=list
    )
    role_requirements: list[
        AgentToolRequirement
    ] = Field(default_factory=list)
    enabled: bool = True
    metadata: dict[str, Any] = Field(
        default_factory=dict
    )


class ToolEcosystemEntry(BaseModel):
    ecosystem_id: str
    tool: ToolManifest | None = None
    server: MCPServerManifest | None = None
    installation: ToolInstallationRecord
    health: ToolHealthRecord
    registered_at: datetime = Field(
        default_factory=utc_now
    )
    updated_at: datetime = Field(
        default_factory=utc_now
    )

    @property
    def name(self) -> str:
        if self.tool is not None:
            return self.tool.name

        if self.server is not None:
            return self.server.name

        return self.ecosystem_id

    @property
    def trust_level(self) -> ToolTrustLevel:
        if self.tool is not None:
            return self.tool.trust_level

        if self.server is not None:
            return self.server.trust_level

        return ToolTrustLevel.UNTRUSTED

    @property
    def capabilities(self) -> list[ToolCapability]:
        if self.tool is not None:
            return list(self.tool.capabilities)

        if self.server is not None:
            return list(self.server.capabilities)

        return []
