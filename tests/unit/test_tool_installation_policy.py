from __future__ import annotations

import pytest

from af_core.tools.ecosystem_models import (
    CompatibilityStatus,
    ToolCompatibility,
    ToolEcosystemEntry,
    ToolHealthRecord,
    ToolInstallationRecord,
    ToolManifest,
    ToolTrustLevel,
    ToolVersionConstraint,
)
from af_core.tools.models import (
    ExternalToolRisk,
)
from af_core.tools.tool_installation_policy import (
    ManifestIntegrityStatus,
    ManifestIntegrityValidator,
    ToolCompatibilityValidator,
    ToolInstallationDecision,
    ToolInstallationPolicy,
    ToolInstallationPolicyEvaluator,
    ToolTrustGovernor,
)


def entry(
    *,
    tool_id: str = "tool.secure",
    version: str = "1.0.0",
    risk: ExternalToolRisk = (
        ExternalToolRisk.READ_ONLY
    ),
    trust: ToolTrustLevel = (
        ToolTrustLevel.FIRST_PARTY
    ),
    compatibility: (
        ToolCompatibility | None
    ) = None,
    tags: set[str] | None = None,
) -> ToolEcosystemEntry:
    manifest = ToolManifest(
        tool_id=tool_id,
        name="Secure Tool",
        version=version,
        risk=risk,
        trust_level=trust,
        tags=tags or {"core"},
        compatibility=(
            compatibility
            or ToolCompatibility(
                status=(
                    CompatibilityStatus
                    .COMPATIBLE
                ),
                af_core_version=(
                    ToolVersionConstraint(
                        minimum_version="1.0.0",
                        maximum_version="2.0.0",
                    )
                ),
            )
        ),
    )

    return ToolEcosystemEntry(
        ecosystem_id=tool_id,
        tool=manifest,
        installation=ToolInstallationRecord(
            ecosystem_id=tool_id
        ),
        health=ToolHealthRecord(
            ecosystem_id=tool_id
        ),
    )


def integrity_validator() -> (
    ManifestIntegrityValidator
):
    return ManifestIntegrityValidator(
        signature_keys={
            "release": "secret",
        }
    )


def sign(
    value: ToolEcosystemEntry,
    validator: ManifestIntegrityValidator,
) -> ToolEcosystemEntry:
    assert value.tool is not None

    value.tool.checksum = (
        validator.compute_checksum(value)
    )
    value.tool.signature = (
        validator.compute_signature(
            value,
            key_id="release",
        )
    )

    return value


def policy_evaluator(
    validator: ManifestIntegrityValidator,
    *,
    af_core_version: str = "1.5.0",
) -> ToolInstallationPolicyEvaluator:
    return ToolInstallationPolicyEvaluator(
        compatibility_validator=(
            ToolCompatibilityValidator(
                af_core_version=af_core_version,
                python_version="3.11.2",
                operating_system="linux",
                architecture="x86_64",
            )
        ),
        integrity_validator=validator,
        trust_governor=ToolTrustGovernor(),
    )


def test_compatible_versions_pass() -> None:
    value = entry()

    report = ToolCompatibilityValidator(
        af_core_version="1.5.0",
        python_version="3.11.2",
        operating_system="linux",
        architecture="x86_64",
    ).validate(value)

    assert report.compatible is True
    assert report.status is (
        CompatibilityStatus.COMPATIBLE
    )
    assert report.reasons == []


def test_af_core_version_outside_range_fails() -> None:
    value = entry()

    report = ToolCompatibilityValidator(
        af_core_version="3.0.0",
        python_version="3.11.2",
        operating_system="linux",
        architecture="x86_64",
    ).validate(value)

    assert report.compatible is False
    assert report.status is (
        CompatibilityStatus.INCOMPATIBLE
    )
    assert any(
        "maximum version" in reason
        for reason in report.reasons
    )


def test_operating_system_and_architecture_mismatch() -> None:
    value = entry(
        compatibility=ToolCompatibility(
            status=CompatibilityStatus.COMPATIBLE,
            operating_systems={"linux"},
            architectures={"x86_64"},
        )
    )

    report = ToolCompatibilityValidator(
        af_core_version="1.5.0",
        python_version="3.11.2",
        operating_system="windows",
        architecture="arm64",
    ).validate(value)

    assert report.compatible is False
    assert report.status is (
        CompatibilityStatus.INCOMPATIBLE
    )
    assert any(
        "Operating system" in reason
        for reason in report.reasons
    )
    assert any(
        "Architecture" in reason
        for reason in report.reasons
    )


def test_unknown_runtime_version_returns_unknown() -> None:
    value = entry(
        compatibility=ToolCompatibility(
            status=CompatibilityStatus.COMPATIBLE,
            protocol_version=ToolVersionConstraint(
                minimum_version="1.0.0",
            ),
        )
    )

    report = ToolCompatibilityValidator(
        af_core_version="1.5.0",
        protocol_version=None,
        python_version="3.11.2",
        operating_system="linux",
        architecture="x86_64",
    ).validate(value)

    assert report.compatible is False
    assert report.status is (
        CompatibilityStatus.UNKNOWN
    )
    assert any(
        "Protocol runtime version is unknown"
        in reason
        for reason in report.reasons
    )


def test_valid_checksum_and_signature_pass() -> None:
    validator = integrity_validator()
    value = sign(
        entry(),
        validator,
    )

    report = validator.validate(
        value,
        require_checksum=True,
        require_signature=True,
    )

    assert report.verified is True
    assert report.status is (
        ManifestIntegrityStatus.VERIFIED
    )
    assert report.checksum_verified is True
    assert report.signature_verified is True
    assert report.reasons == []


def test_missing_checksum_is_reported() -> None:
    validator = integrity_validator()
    value = entry()

    report = validator.validate(
        value,
        require_checksum=True,
        require_signature=False,
    )

    assert report.verified is False
    assert report.status is (
        ManifestIntegrityStatus.CHECKSUM_MISSING
    )
    assert report.checksum_verified is False
    assert any(
        "checksum is missing" in reason
        for reason in report.reasons
    )


def test_manifest_tampering_breaks_integrity() -> None:
    validator = integrity_validator()
    value = sign(
        entry(),
        validator,
    )

    assert value.tool is not None
    value.tool.version = "2.0.0"

    report = validator.validate(
        value,
        require_checksum=True,
        require_signature=True,
    )

    assert report.verified is False
    assert report.checksum_verified is False
    assert report.status in {
        ManifestIntegrityStatus.CHECKSUM_MISMATCH,
        ManifestIntegrityStatus.SIGNATURE_INVALID,
    }


def test_unknown_signature_key_is_invalid() -> None:
    signer = integrity_validator()
    value = entry()

    assert value.tool is not None

    value.tool.checksum = (
        signer.compute_checksum(value)
    )
    value.tool.signature = (
        signer.compute_signature(
            value,
            key_id="release",
        )
    )

    verifier = ManifestIntegrityValidator(
        signature_keys={
            "different-key": "other-secret",
        }
    )

    report = verifier.validate(
        value,
        require_checksum=True,
        require_signature=True,
    )

    assert report.verified is False
    assert report.checksum_verified is True
    assert report.signature_verified is False
    assert report.status is (
        ManifestIntegrityStatus.SIGNATURE_INVALID
    )
    assert any(
        "Unknown signature key" in reason
        for reason in report.reasons
    )


def test_trust_governor_accepts_signed_first_party() -> None:
    validator = integrity_validator()
    value = sign(
        entry(),
        validator,
    )

    compatibility = ToolCompatibilityValidator(
        af_core_version="1.5.0",
        python_version="3.11.2",
        operating_system="linux",
        architecture="x86_64",
    ).validate(value)

    integrity = validator.validate(
        value,
        require_checksum=True,
        require_signature=True,
    )

    report = ToolTrustGovernor().evaluate(
        value,
        compatibility=compatibility,
        integrity=integrity,
    )

    assert report.trusted is True
    assert report.effective_trust is (
        ToolTrustLevel.FIRST_PARTY
    )


def test_trust_governor_downgrades_unsigned_tool() -> None:
    validator = integrity_validator()
    value = entry(
        trust=ToolTrustLevel.VERIFIED,
    )

    compatibility = ToolCompatibilityValidator(
        af_core_version="1.5.0",
        python_version="3.11.2",
        operating_system="linux",
        architecture="x86_64",
    ).validate(value)

    integrity = validator.validate(
        value,
        require_checksum=True,
        require_signature=True,
    )

    report = ToolTrustGovernor().evaluate(
        value,
        compatibility=compatibility,
        integrity=integrity,
        allow_unsigned_first_party=False,
    )

    assert report.trusted is False
    assert report.effective_trust is (
        ToolTrustLevel.COMMUNITY
    )


def test_installation_policy_allows_valid_tool() -> None:
    validator = integrity_validator()
    value = sign(
        entry(tags={"core", "verified"}),
        validator,
    )

    evaluator = policy_evaluator(validator)

    result = evaluator.evaluate(
        value,
        ToolInstallationPolicy(
            minimum_trust_level=(
                ToolTrustLevel.VERIFIED
            ),
            maximum_risk=(
                ExternalToolRisk.READ_ONLY
            ),
            require_checksum=True,
            require_signature=True,
            required_tags={"core"},
        ),
    )

    assert result.allowed is True
    assert result.decision is (
        ToolInstallationDecision.ALLOW
    )
    assert result.reasons == []

    evaluator.enforce(result)

    assert evaluator.latest_audit() is not None
    assert evaluator.latest_audit().allowed is True


def test_installation_policy_blocks_risk_trust_and_tags() -> None:
    validator = integrity_validator()

    value = sign(
        entry(
            risk=ExternalToolRisk.PRIVILEGED,
            trust=ToolTrustLevel.COMMUNITY,
            tags={"blocked"},
        ),
        validator,
    )

    evaluator = policy_evaluator(validator)

    result = evaluator.evaluate(
        value,
        ToolInstallationPolicy(
            minimum_trust_level=(
                ToolTrustLevel.VERIFIED
            ),
            maximum_risk=(
                ExternalToolRisk.READ_ONLY
            ),
            require_checksum=True,
            require_signature=True,
            required_tags={"core"},
            blocked_tags={"blocked"},
        ),
    )

    assert result.allowed is False
    assert result.decision is (
        ToolInstallationDecision.BLOCK
    )

    assert any(
        "Effective Trust level" in reason
        for reason in result.reasons
    )
    assert any(
        "exceeds maximum allowed risk" in reason
        for reason in result.reasons
    )
    assert any(
        "Required tags are missing" in reason
        for reason in result.reasons
    )
    assert any(
        "Blocked tags are present" in reason
        for reason in result.reasons
    )

    with pytest.raises(
        PermissionError,
        match="Tool installation blocked",
    ):
        evaluator.enforce(result)
