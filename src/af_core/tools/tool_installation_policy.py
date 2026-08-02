from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field

from .ecosystem_models import (
    CompatibilityStatus,
    ToolEcosystemEntry,
    ToolTrustLevel,
)
from .models import ExternalToolRisk


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ManifestIntegrityStatus(StrEnum):
    VERIFIED = "VERIFIED"
    CHECKSUM_MISSING = "CHECKSUM_MISSING"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    SIGNATURE_MISSING = "SIGNATURE_MISSING"
    SIGNATURE_INVALID = "SIGNATURE_INVALID"
    UNSUPPORTED_ALGORITHM = "UNSUPPORTED_ALGORITHM"


class ToolInstallationDecision(StrEnum):
    ALLOW = "ALLOW"
    WARN = "WARN"
    BLOCK = "BLOCK"


class ToolCompatibilityReport(BaseModel):
    ecosystem_id: str
    status: CompatibilityStatus
    compatible: bool
    reasons: list[str] = Field(
        default_factory=list
    )
    checked_at: datetime = Field(
        default_factory=utc_now
    )


class ManifestIntegrityReport(BaseModel):
    ecosystem_id: str
    status: ManifestIntegrityStatus
    checksum_verified: bool = False
    signature_verified: bool = False
    reasons: list[str] = Field(
        default_factory=list
    )
    checked_at: datetime = Field(
        default_factory=utc_now
    )

    @property
    def verified(self) -> bool:
        return self.status is (
            ManifestIntegrityStatus.VERIFIED
        )


class ToolTrustReport(BaseModel):
    ecosystem_id: str
    declared_trust: ToolTrustLevel
    effective_trust: ToolTrustLevel
    trusted: bool
    reasons: list[str] = Field(
        default_factory=list
    )
    checked_at: datetime = Field(
        default_factory=utc_now
    )


class ToolInstallationPolicy(BaseModel):
    minimum_trust_level: ToolTrustLevel = (
        ToolTrustLevel.VERIFIED
    )
    maximum_risk: ExternalToolRisk = (
        ExternalToolRisk.WORKSPACE_WRITE
    )
    require_compatible: bool = True
    require_checksum: bool = True
    require_signature: bool = False
    allow_partially_compatible: bool = False
    allow_unsigned_first_party: bool = True
    allow_unverified_with_warning: bool = False
    blocked_tags: set[str] = Field(
        default_factory=set
    )
    required_tags: set[str] = Field(
        default_factory=set
    )


class ToolInstallationEvaluation(BaseModel):
    ecosystem_id: str
    decision: ToolInstallationDecision
    allowed: bool
    warnings: list[str] = Field(
        default_factory=list
    )
    reasons: list[str] = Field(
        default_factory=list
    )
    compatibility: ToolCompatibilityReport
    integrity: ManifestIntegrityReport
    trust: ToolTrustReport
    evaluated_at: datetime = Field(
        default_factory=utc_now
    )


class ToolInstallationAuditRecord(BaseModel):
    ecosystem_id: str
    decision: ToolInstallationDecision
    allowed: bool
    reasons: list[str] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(
        default_factory=list
    )
    created_at: datetime = Field(
        default_factory=utc_now
    )


import platform
import re

from packaging.version import (
    InvalidVersion,
    Version,
)

from .ecosystem_models import (
    ToolCompatibility,
    ToolVersionConstraint,
)


class ToolCompatibilityValidator:
    def __init__(
        self,
        *,
        af_core_version: str,
        protocol_version: str | None = None,
        python_version: str | None = None,
        operating_system: str | None = None,
        architecture: str | None = None,
    ) -> None:
        self.af_core_version = af_core_version
        self.protocol_version = protocol_version
        self.python_version = (
            python_version
            or platform.python_version()
        )
        self.operating_system = (
            operating_system
            or platform.system().casefold()
        )
        self.architecture = (
            architecture
            or platform.machine().casefold()
        )

    def validate(
        self,
        entry: ToolEcosystemEntry,
    ) -> ToolCompatibilityReport:
        compatibility = self._compatibility(entry)

        reasons: list[str] = []
        unknown = False
        partial = False

        checks = [
            (
                "AF-Core",
                self.af_core_version,
                compatibility.af_core_version,
            ),
            (
                "Protocol",
                self.protocol_version,
                compatibility.protocol_version,
            ),
            (
                "Python",
                self.python_version,
                compatibility.python_version,
            ),
        ]

        for label, current, constraint in checks:
            if constraint is None:
                continue

            if current is None:
                unknown = True
                reasons.append(
                    f"{label} runtime version is unknown."
                )
                continue

            matched, message = (
                self._matches_constraint(
                    current=current,
                    constraint=constraint,
                    label=label,
                )
            )

            if not matched:
                reasons.append(message)

        if compatibility.operating_systems:
            allowed_os = {
                value.casefold()
                for value
                in compatibility.operating_systems
            }

            if (
                self.operating_system
                not in allowed_os
            ):
                reasons.append(
                    "Operating system "
                    f"{self.operating_system!r} is not "
                    "supported."
                )

        if compatibility.architectures:
            allowed_architectures = {
                value.casefold()
                for value
                in compatibility.architectures
            }

            if (
                self.architecture
                not in allowed_architectures
            ):
                reasons.append(
                    "Architecture "
                    f"{self.architecture!r} is not "
                    "supported."
                )

        declared = compatibility.status

        if declared is (
            CompatibilityStatus.INCOMPATIBLE
        ):
            reasons.append(
                "Manifest declares the Tool "
                "incompatible."
            )

        elif declared is (
            CompatibilityStatus
            .PARTIALLY_COMPATIBLE
        ):
            partial = True

        elif declared is (
            CompatibilityStatus.UNKNOWN
        ):
            unknown = True

        hard_failure = any(
            "not supported" in reason
            or "does not satisfy" in reason
            or "declares the Tool incompatible"
            in reason
            for reason in reasons
        )

        if hard_failure:
            status = (
                CompatibilityStatus.INCOMPATIBLE
            )
            compatible = False

        elif unknown:
            status = CompatibilityStatus.UNKNOWN
            compatible = False

        elif partial:
            status = (
                CompatibilityStatus
                .PARTIALLY_COMPATIBLE
            )
            compatible = True

        else:
            status = CompatibilityStatus.COMPATIBLE
            compatible = True

        return ToolCompatibilityReport(
            ecosystem_id=entry.ecosystem_id,
            status=status,
            compatible=compatible,
            reasons=reasons,
        )

    def _compatibility(
        self,
        entry: ToolEcosystemEntry,
    ) -> ToolCompatibility:
        if entry.tool is not None:
            return entry.tool.compatibility

        if entry.server is not None:
            return entry.server.compatibility

        return ToolCompatibility()

    def _matches_constraint(
        self,
        *,
        current: str,
        constraint: ToolVersionConstraint,
        label: str,
    ) -> tuple[bool, str]:
        try:
            current_version = Version(
                self._normalize_version(current)
            )
        except InvalidVersion:
            return (
                False,
                f"{label} version {current!r} "
                "is invalid.",
            )

        if constraint.exact_version is not None:
            expected = self._parse_version(
                constraint.exact_version,
                label=label,
            )

            if current_version != expected:
                return (
                    False,
                    f"{label} version {current} "
                    f"does not satisfy exact version "
                    f"{constraint.exact_version}.",
                )

        if constraint.minimum_version is not None:
            minimum = self._parse_version(
                constraint.minimum_version,
                label=label,
            )

            if current_version < minimum:
                return (
                    False,
                    f"{label} version {current} "
                    "does not satisfy minimum version "
                    f"{constraint.minimum_version}.",
                )

        if constraint.maximum_version is not None:
            maximum = self._parse_version(
                constraint.maximum_version,
                label=label,
            )

            if current_version > maximum:
                return (
                    False,
                    f"{label} version {current} "
                    "does not satisfy maximum version "
                    f"{constraint.maximum_version}.",
                )

        return True, ""

    def _parse_version(
        self,
        value: str,
        *,
        label: str,
    ) -> Version:
        try:
            return Version(
                self._normalize_version(value)
            )
        except InvalidVersion as exc:
            raise ValueError(
                f"Invalid {label} version "
                f"constraint: {value!r}"
            ) from exc

    def _normalize_version(
        self,
        value: str,
    ) -> str:
        normalized = value.strip()

        if normalized.startswith(("v", "V")):
            normalized = normalized[1:]

        match = re.match(
            r"^(\d+(?:\.\d+){0,3})",
            normalized,
        )

        if match is not None:
            return match.group(1)

        return normalized


import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any


class ManifestIntegrityValidator:
    def __init__(
        self,
        *,
        signature_keys: Mapping[
            str,
            bytes | str,
        ] | None = None,
    ) -> None:
        self.signature_keys = {
            key_id: (
                value.encode("utf-8")
                if isinstance(value, str)
                else value
            )
            for key_id, value in (
                signature_keys or {}
            ).items()
        }

    def canonical_payload(
        self,
        entry: ToolEcosystemEntry,
    ) -> bytes:
        manifest = (
            entry.tool
            if entry.tool is not None
            else entry.server
        )

        if manifest is None:
            raise ValueError(
                "Ecosystem entry has no manifest."
            )

        payload = manifest.model_dump(
            mode="json",
            exclude={
                "checksum",
                "signature",
            },
        )

        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def compute_checksum(
        self,
        entry: ToolEcosystemEntry,
    ) -> str:
        digest = hashlib.sha256(
            self.canonical_payload(entry)
        ).hexdigest()

        return f"sha256:{digest}"

    def verify_checksum(
        self,
        entry: ToolEcosystemEntry,
    ) -> tuple[bool, str]:
        manifest = (
            entry.tool
            if entry.tool is not None
            else entry.server
        )

        if manifest is None:
            return False, "Manifest is missing."

        expected = manifest.checksum

        if not expected:
            return False, "Manifest checksum is missing."

        actual = self.compute_checksum(entry)

        return (
            hmac.compare_digest(
                expected,
                actual,
            ),
            actual,
        )

    def compute_signature(
        self,
        entry: ToolEcosystemEntry,
        *,
        key_id: str,
    ) -> str:
        try:
            key = self.signature_keys[key_id]
        except KeyError as exc:
            raise KeyError(
                f"Unknown signature key: {key_id}"
            ) from exc

        digest = hmac.new(
            key,
            self.canonical_payload(entry),
            hashlib.sha256,
        ).hexdigest()

        return f"hmac-sha256:{key_id}:{digest}"

    def verify_signature(
        self,
        entry: ToolEcosystemEntry,
    ) -> tuple[
        bool,
        ManifestIntegrityStatus,
        str,
    ]:
        manifest = (
            entry.tool
            if entry.tool is not None
            else entry.server
        )

        if manifest is None:
            return (
                False,
                ManifestIntegrityStatus
                .SIGNATURE_MISSING,
                "Manifest is missing.",
            )

        signature = manifest.signature

        if not signature:
            return (
                False,
                ManifestIntegrityStatus
                .SIGNATURE_MISSING,
                "Manifest signature is missing.",
            )

        parts = signature.split(":", 2)

        if (
            len(parts) != 3
            or parts[0] != "hmac-sha256"
        ):
            return (
                False,
                ManifestIntegrityStatus
                .UNSUPPORTED_ALGORITHM,
                "Unsupported signature format.",
            )

        _, key_id, supplied = parts

        key = self.signature_keys.get(key_id)

        if key is None:
            return (
                False,
                ManifestIntegrityStatus
                .SIGNATURE_INVALID,
                f"Unknown signature key: {key_id}",
            )

        expected = hmac.new(
            key,
            self.canonical_payload(entry),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(
            supplied,
            expected,
        ):
            return (
                False,
                ManifestIntegrityStatus
                .SIGNATURE_INVALID,
                "Manifest signature does not match.",
            )

        return (
            True,
            ManifestIntegrityStatus.VERIFIED,
            "",
        )

    def validate(
        self,
        entry: ToolEcosystemEntry,
        *,
        require_checksum: bool = True,
        require_signature: bool = False,
    ) -> ManifestIntegrityReport:
        reasons: list[str] = []

        checksum_verified = False
        signature_verified = False

        checksum_ok, checksum_message = (
            self.verify_checksum(entry)
        )

        if checksum_ok:
            checksum_verified = True
        elif require_checksum:
            reasons.append(checksum_message)

        signature_ok, signature_status, (
            signature_message
        ) = self.verify_signature(entry)

        if signature_ok:
            signature_verified = True
        elif require_signature:
            reasons.append(signature_message)

        if require_checksum and not checksum_verified:
            manifest = (
                entry.tool
                if entry.tool is not None
                else entry.server
            )

            status = (
                ManifestIntegrityStatus
                .CHECKSUM_MISSING
                if manifest is not None
                and not manifest.checksum
                else ManifestIntegrityStatus
                .CHECKSUM_MISMATCH
            )

        elif require_signature and not signature_verified:
            status = signature_status

        else:
            status = ManifestIntegrityStatus.VERIFIED

        return ManifestIntegrityReport(
            ecosystem_id=entry.ecosystem_id,
            status=status,
            checksum_verified=checksum_verified,
            signature_verified=signature_verified,
            reasons=reasons,
        )


class ToolTrustGovernor:
    _TRUST_RANK = {
        ToolTrustLevel.UNTRUSTED: 0,
        ToolTrustLevel.COMMUNITY: 1,
        ToolTrustLevel.VERIFIED: 2,
        ToolTrustLevel.FIRST_PARTY: 3,
        ToolTrustLevel.SYSTEM: 4,
    }

    def evaluate(
        self,
        entry: ToolEcosystemEntry,
        *,
        compatibility: ToolCompatibilityReport,
        integrity: ManifestIntegrityReport,
        allow_unsigned_first_party: bool = True,
    ) -> ToolTrustReport:
        declared = entry.trust_level
        effective = declared
        reasons: list[str] = []

        if not compatibility.compatible:
            effective = ToolTrustLevel.UNTRUSTED
            reasons.append(
                "Compatibility validation did not pass."
            )

        if not integrity.checksum_verified:
            effective = self._lower_to(
                effective,
                ToolTrustLevel.COMMUNITY,
            )
            reasons.append(
                "Manifest checksum is not verified."
            )

        if not integrity.signature_verified:
            unsigned_allowed = (
                allow_unsigned_first_party
                and declared in {
                    ToolTrustLevel.FIRST_PARTY,
                    ToolTrustLevel.SYSTEM,
                }
                and integrity.checksum_verified
            )

            if unsigned_allowed:
                reasons.append(
                    "Unsigned first-party manifest "
                    "accepted by policy."
                )
            else:
                effective = self._lower_to(
                    effective,
                    ToolTrustLevel.COMMUNITY,
                )
                reasons.append(
                    "Manifest signature is not verified."
                )

        trusted = (
            self._TRUST_RANK[effective]
            >= self._TRUST_RANK[
                ToolTrustLevel.VERIFIED
            ]
        )

        return ToolTrustReport(
            ecosystem_id=entry.ecosystem_id,
            declared_trust=declared,
            effective_trust=effective,
            trusted=trusted,
            reasons=reasons,
        )

    def at_least(
        self,
        actual: ToolTrustLevel,
        minimum: ToolTrustLevel,
    ) -> bool:
        return (
            self._TRUST_RANK[actual]
            >= self._TRUST_RANK[minimum]
        )

    def _lower_to(
        self,
        current: ToolTrustLevel,
        maximum: ToolTrustLevel,
    ) -> ToolTrustLevel:
        if (
            self._TRUST_RANK[current]
            <= self._TRUST_RANK[maximum]
        ):
            return current

        return maximum


class ToolInstallationPolicyEvaluator:
    _RISK_RANK = {
        ExternalToolRisk.READ_ONLY: 0,
        ExternalToolRisk.WORKSPACE_WRITE: 1,
        ExternalToolRisk.EXTERNAL_WRITE: 2,
        ExternalToolRisk.PRIVILEGED: 3,
    }

    def __init__(
        self,
        *,
        compatibility_validator: (
            ToolCompatibilityValidator
        ),
        integrity_validator: (
            ManifestIntegrityValidator
        ),
        trust_governor: ToolTrustGovernor | None = None,
    ) -> None:
        self.compatibility_validator = (
            compatibility_validator
        )
        self.integrity_validator = (
            integrity_validator
        )
        self.trust_governor = (
            trust_governor
            or ToolTrustGovernor()
        )
        self._audit: list[
            ToolInstallationAuditRecord
        ] = []

    def evaluate(
        self,
        entry: ToolEcosystemEntry,
        policy: ToolInstallationPolicy,
    ) -> ToolInstallationEvaluation:
        compatibility = (
            self.compatibility_validator.validate(
                entry
            )
        )

        integrity = (
            self.integrity_validator.validate(
                entry,
                require_checksum=(
                    policy.require_checksum
                ),
                require_signature=(
                    policy.require_signature
                ),
            )
        )

        trust = self.trust_governor.evaluate(
            entry,
            compatibility=compatibility,
            integrity=integrity,
            allow_unsigned_first_party=(
                policy.allow_unsigned_first_party
            ),
        )

        reasons: list[str] = []
        warnings: list[str] = []

        if policy.require_compatible:
            if compatibility.status is (
                CompatibilityStatus
                .PARTIALLY_COMPATIBLE
            ):
                if policy.allow_partially_compatible:
                    warnings.extend(
                        compatibility.reasons
                        or [
                            "Tool is only partially "
                            "compatible."
                        ]
                    )
                else:
                    reasons.append(
                        "Partially compatible Tools are "
                        "not allowed."
                    )

            elif not compatibility.compatible:
                reasons.extend(
                    compatibility.reasons
                    or [
                        "Tool compatibility validation "
                        "failed."
                    ]
                )

        elif not compatibility.compatible:
            warnings.extend(
                compatibility.reasons
                or [
                    "Tool compatibility is not confirmed."
                ]
            )

        if not integrity.verified:
            if (
                policy.allow_unverified_with_warning
                and not policy.require_checksum
                and not policy.require_signature
            ):
                warnings.extend(
                    integrity.reasons
                    or [
                        "Manifest integrity is not "
                        "fully verified."
                    ]
                )
            else:
                reasons.extend(
                    integrity.reasons
                    or [
                        "Manifest integrity validation "
                        "failed."
                    ]
                )

        if not self.trust_governor.at_least(
            trust.effective_trust,
            policy.minimum_trust_level,
        ):
            message = (
                "Effective Trust level "
                f"{trust.effective_trust.value} is below "
                f"required level "
                f"{policy.minimum_trust_level.value}."
            )

            if policy.allow_unverified_with_warning:
                warnings.append(message)
            else:
                reasons.append(message)

        risk = self._entry_risk(entry)

        if (
            self._RISK_RANK[risk]
            > self._RISK_RANK[
                policy.maximum_risk
            ]
        ):
            reasons.append(
                f"Tool risk {risk.value} exceeds "
                f"maximum allowed risk "
                f"{policy.maximum_risk.value}."
            )

        tags = self._entry_tags(entry)

        missing_tags = (
            policy.required_tags - tags
        )

        if missing_tags:
            reasons.append(
                "Required tags are missing: "
                + ", ".join(sorted(missing_tags))
            )

        blocked_tags = (
            policy.blocked_tags & tags
        )

        if blocked_tags:
            reasons.append(
                "Blocked tags are present: "
                + ", ".join(sorted(blocked_tags))
            )

        if reasons:
            decision = ToolInstallationDecision.BLOCK
            allowed = False
        elif warnings:
            decision = ToolInstallationDecision.WARN
            allowed = True
        else:
            decision = ToolInstallationDecision.ALLOW
            allowed = True

        evaluation = ToolInstallationEvaluation(
            ecosystem_id=entry.ecosystem_id,
            decision=decision,
            allowed=allowed,
            warnings=warnings,
            reasons=reasons,
            compatibility=compatibility,
            integrity=integrity,
            trust=trust,
        )

        self._audit.append(
            ToolInstallationAuditRecord(
                ecosystem_id=entry.ecosystem_id,
                decision=decision,
                allowed=allowed,
                reasons=list(reasons),
                warnings=list(warnings),
            )
        )

        return evaluation

    def enforce(
        self,
        evaluation: ToolInstallationEvaluation,
    ) -> None:
        if not evaluation.allowed:
            raise PermissionError(
                "Tool installation blocked: "
                + "; ".join(
                    evaluation.reasons
                    or ["Policy rejected the Tool."]
                )
            )

    def audit_records(
        self,
    ) -> list[ToolInstallationAuditRecord]:
        return [
            item.model_copy(deep=True)
            for item in self._audit
        ]

    def latest_audit(
        self,
    ) -> ToolInstallationAuditRecord | None:
        if not self._audit:
            return None

        return self._audit[-1].model_copy(
            deep=True
        )

    def _entry_risk(
        self,
        entry: ToolEcosystemEntry,
    ) -> ExternalToolRisk:
        if entry.tool is not None:
            return entry.tool.risk

        return ExternalToolRisk.READ_ONLY

    def _entry_tags(
        self,
        entry: ToolEcosystemEntry,
    ) -> set[str]:
        if entry.tool is not None:
            return set(entry.tool.tags)

        if entry.server is not None:
            return set(entry.server.tags)

        return set()
