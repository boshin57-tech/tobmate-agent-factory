from __future__ import annotations

import asyncio

import pytest

from af_core.tools.ecosystem_models import (
    CompatibilityStatus,
    ToolCompatibility,
    ToolHealthRecord,
    ToolHealthState,
    ToolInstallationRecord,
    ToolInstallationState,
    ToolManifest,
    ToolTrustLevel,
    ToolVersionConstraint,
)
from af_core.tools.ecosystem_registry import (
    ToolEcosystemRegistry,
)
from af_core.tools.models import (
    ExternalToolRisk,
)
from af_core.tools.tool_installation_lifecycle import (
    ToolApprovalDecision,
    ToolApprovalRequiredError,
    ToolInstallationAdapter,
    ToolInstallationLifecycleManager,
    ToolInstallationOrchestrator,
    ToolInstallationRequest,
    ToolLifecycleState,
    ToolLifecycleTransitionError,
)
from af_core.tools.tool_installation_policy import (
    ManifestIntegrityValidator,
    ToolCompatibilityValidator,
    ToolInstallationDecision,
    ToolInstallationPolicy,
    ToolInstallationPolicyEvaluator,
    ToolTrustGovernor,
)


class FakeInstallationBackend:
    def __init__(self) -> None:
        self.installed: list[
            tuple[str, str | None]
        ] = []
        self.rolled_back: list[
            tuple[str, str | None]
        ] = []
        self.removed: list[str] = []

        self.fail_install = False
        self.fail_rollback = False
        self.fail_remove = False

    async def install(
        self,
        entry,
        requested_version: str | None,
    ) -> str:
        self.installed.append(
            (
                entry.ecosystem_id,
                requested_version,
            )
        )

        if self.fail_install:
            raise RuntimeError(
                "simulated installation failure"
            )

        return requested_version or "1.0.0"

    async def rollback(
        self,
        entry,
        previous_version: str | None,
    ) -> None:
        self.rolled_back.append(
            (
                entry.ecosystem_id,
                previous_version,
            )
        )

        if self.fail_rollback:
            raise RuntimeError(
                "simulated rollback failure"
            )

    async def remove(
        self,
        entry,
    ) -> None:
        self.removed.append(
            entry.ecosystem_id
        )

        if self.fail_remove:
            raise RuntimeError(
                "simulated removal failure"
            )

    def adapter(
        self,
    ) -> ToolInstallationAdapter:
        return ToolInstallationAdapter(
            install=self.install,
            rollback=self.rollback,
            remove=self.remove,
        )


def secure_entry(
    *,
    installed_version: str | None = None,
):
    integrity = ManifestIntegrityValidator(
        signature_keys={
            "release": "secret",
        }
    )

    manifest = ToolManifest(
        tool_id="tool.secure",
        name="Secure Tool",
        version="2.0.0",
        risk=ExternalToolRisk.READ_ONLY,
        trust_level=ToolTrustLevel.FIRST_PARTY,
        tags={"core", "verified"},
        compatibility=ToolCompatibility(
            status=CompatibilityStatus.COMPATIBLE,
            af_core_version=ToolVersionConstraint(
                minimum_version="1.0.0",
                maximum_version="2.0.0",
            ),
        ),
    )

    ecosystem = ToolEcosystemRegistry()

    ecosystem.register_tool(
        manifest,
        installation=ToolInstallationRecord(
            ecosystem_id="tool.secure",
            state=(
                ToolInstallationState.INSTALLED
                if installed_version
                else ToolInstallationState
                .NOT_INSTALLED
            ),
            installed_version=installed_version,
        ),
        health=ToolHealthRecord(
            ecosystem_id="tool.secure",
            state=(
                ToolHealthState.HEALTHY
                if installed_version
                else ToolHealthState.UNKNOWN
            ),
        ),
    )

    entry = ecosystem.get("tool.secure")

    assert entry.tool is not None

    entry.tool.checksum = (
        integrity.compute_checksum(entry)
    )
    entry.tool.signature = (
        integrity.compute_signature(
            entry,
            key_id="release",
        )
    )

    ecosystem.upsert_tool(entry.tool)

    return ecosystem, integrity


def installation_policy() -> ToolInstallationPolicy:
    return ToolInstallationPolicy(
        minimum_trust_level=(
            ToolTrustLevel.VERIFIED
        ),
        maximum_risk=(
            ExternalToolRisk.READ_ONLY
        ),
        require_compatible=True,
        require_checksum=True,
        require_signature=True,
        required_tags={"core"},
    )


def setup_orchestrator(
    *,
    installed_version: str | None = None,
):
    ecosystem, integrity = secure_entry(
        installed_version=installed_version
    )

    lifecycle = (
        ToolInstallationLifecycleManager()
    )
    backend = FakeInstallationBackend()

    evaluator = ToolInstallationPolicyEvaluator(
        compatibility_validator=(
            ToolCompatibilityValidator(
                af_core_version="1.5.0",
                python_version="3.11.2",
                operating_system="linux",
                architecture="x86_64",
            )
        ),
        integrity_validator=integrity,
        trust_governor=ToolTrustGovernor(),
    )

    orchestrator = ToolInstallationOrchestrator(
        lifecycle=lifecycle,
        ecosystem=ecosystem,
        policy_evaluator=evaluator,
        adapter=backend.adapter(),
    )

    return (
        ecosystem,
        lifecycle,
        backend,
        evaluator,
        orchestrator,
    )


def request_install(
    lifecycle: ToolInstallationLifecycleManager,
    *,
    request_id: str = "request-1",
    require_approval: bool = True,
    requested_version: str = "2.0.0",
):
    return lifecycle.request_install(
        ToolInstallationRequest(
            request_id=request_id,
            ecosystem_id="tool.secure",
            requested_by="operator",
            requested_version=requested_version,
            require_approval=require_approval,
        )
    )


def test_approval_workflow_records_decision() -> None:
    (
        ecosystem,
        lifecycle,
        backend,
        evaluator,
        orchestrator,
    ) = setup_orchestrator()

    del ecosystem, backend, evaluator, orchestrator

    pending = request_install(
        lifecycle,
        request_id="request-approval",
        require_approval=True,
    )

    assert pending.state is (
        ToolLifecycleState.PENDING_APPROVAL
    )

    approved = lifecycle.approve(
        request_id="request-approval",
        decided_by="admin",
        reason="Security review passed.",
    )

    assert approved.state is (
        ToolLifecycleState.APPROVED
    )
    assert approved.approval is not None
    assert approved.approval.decision is (
        ToolApprovalDecision.APPROVE
    )
    assert approved.approval.decided_by == "admin"
    assert approved.records[-1].message == (
        "Security review passed."
    )


def test_install_without_approval_is_blocked() -> None:
    (
        ecosystem,
        lifecycle,
        backend,
        evaluator,
        orchestrator,
    ) = setup_orchestrator()

    del ecosystem, backend, evaluator

    request_install(
        lifecycle,
        request_id="request-pending",
        require_approval=True,
    )

    with pytest.raises(
        ToolApprovalRequiredError,
        match="requires approval",
    ):
        asyncio.run(
            orchestrator.install(
                request_id="request-pending",
                actor="installer",
                policy=installation_policy(),
            )
        )

    case = lifecycle.get("request-pending")

    assert case.state is (
        ToolLifecycleState.PENDING_APPROVAL
    )


def test_policy_evaluation_is_attached_to_install_case() -> None:
    (
        ecosystem,
        lifecycle,
        backend,
        evaluator,
        orchestrator,
    ) = setup_orchestrator()

    del ecosystem, backend

    request_install(
        lifecycle,
        request_id="request-policy",
        require_approval=True,
    )

    lifecycle.approve(
        request_id="request-policy",
        decided_by="admin",
    )

    installed = asyncio.run(
        orchestrator.install(
            request_id="request-policy",
            actor="installer",
            policy=installation_policy(),
        )
    )

    assert installed.policy_evaluation is not None
    assert installed.policy_evaluation.allowed is True
    assert installed.policy_evaluation.decision is (
        ToolInstallationDecision.ALLOW
    )
    assert len(evaluator.audit_records()) == 1


def test_successful_install_updates_lifecycle_and_registry() -> None:
    (
        ecosystem,
        lifecycle,
        backend,
        evaluator,
        orchestrator,
    ) = setup_orchestrator()

    del evaluator

    request_install(
        lifecycle,
        request_id="request-success",
        require_approval=True,
        requested_version="2.0.0",
    )

    lifecycle.approve(
        request_id="request-success",
        decided_by="admin",
    )

    result = asyncio.run(
        orchestrator.install(
            request_id="request-success",
            actor="installer",
            policy=installation_policy(),
        )
    )

    assert result.state is (
        ToolLifecycleState.INSTALLED
    )
    assert result.installed_version == "2.0.0"
    assert result.error is None

    assert backend.installed == [
        (
            "tool.secure",
            "2.0.0",
        )
    ]

    entry = ecosystem.get("tool.secure")

    assert entry.installation.state is (
        ToolInstallationState.INSTALLED
    )
    assert entry.installation.installed_version == (
        "2.0.0"
    )
    assert entry.health.state is (
        ToolHealthState.HEALTHY
    )

    actions = [
        record.action.value
        for record in result.records
    ]

    assert actions == [
        "REQUEST_INSTALL",
        "APPROVE_INSTALL",
        "START_INSTALL",
        "COMPLETE_INSTALL",
    ]


def test_failed_install_updates_registry_failure_state() -> None:
    (
        ecosystem,
        lifecycle,
        backend,
        evaluator,
        orchestrator,
    ) = setup_orchestrator(
        installed_version="1.0.0"
    )

    del evaluator

    backend.fail_install = True

    request_install(
        lifecycle,
        request_id="request-fail",
        require_approval=True,
        requested_version="2.0.0",
    )

    lifecycle.approve(
        request_id="request-fail",
        decided_by="admin",
    )

    with pytest.raises(
        RuntimeError,
        match="simulated installation failure",
    ):
        asyncio.run(
            orchestrator.install(
                request_id="request-fail",
                actor="installer",
                policy=installation_policy(),
            )
        )

    case = lifecycle.get("request-fail")

    assert case.state is (
        ToolLifecycleState.FAILED
    )
    assert case.error == (
        "simulated installation failure"
    )
    assert case.previous_version == "1.0.0"

    entry = ecosystem.get("tool.secure")

    assert entry.installation.state is (
        ToolInstallationState.FAILED
    )
    assert entry.installation.installed_version == (
        "1.0.0"
    )
    assert entry.health.state is (
        ToolHealthState.DEGRADED
    )


def test_successful_rollback_restores_previous_version() -> None:
    (
        ecosystem,
        lifecycle,
        backend,
        evaluator,
        orchestrator,
    ) = setup_orchestrator(
        installed_version="1.0.0"
    )

    del evaluator

    backend.fail_install = True

    request_install(
        lifecycle,
        request_id="request-rollback",
        require_approval=True,
        requested_version="2.0.0",
    )

    lifecycle.approve(
        request_id="request-rollback",
        decided_by="admin",
    )

    with pytest.raises(RuntimeError):
        asyncio.run(
            orchestrator.install(
                request_id="request-rollback",
                actor="installer",
                policy=installation_policy(),
            )
        )

    rolled_back = asyncio.run(
        orchestrator.rollback(
            request_id="request-rollback",
            actor="installer",
            reason="Restore stable version.",
        )
    )

    assert rolled_back.state is (
        ToolLifecycleState.ROLLED_BACK
    )
    assert rolled_back.installed_version == (
        "1.0.0"
    )

    assert backend.rolled_back == [
        (
            "tool.secure",
            "1.0.0",
        )
    ]

    entry = ecosystem.get("tool.secure")

    assert entry.installation.state is (
        ToolInstallationState.INSTALLED
    )
    assert entry.installation.installed_version == (
        "1.0.0"
    )
    assert entry.health.state is (
        ToolHealthState.HEALTHY
    )


def test_rollback_without_previous_version_removes_tool() -> None:
    (
        ecosystem,
        lifecycle,
        backend,
        evaluator,
        orchestrator,
    ) = setup_orchestrator()

    del evaluator

    backend.fail_install = True

    request_install(
        lifecycle,
        request_id="request-rollback-remove",
        require_approval=True,
        requested_version="2.0.0",
    )

    lifecycle.approve(
        request_id="request-rollback-remove",
        decided_by="admin",
    )

    with pytest.raises(RuntimeError):
        asyncio.run(
            orchestrator.install(
                request_id=(
                    "request-rollback-remove"
                ),
                actor="installer",
                policy=installation_policy(),
            )
        )

    result = asyncio.run(
        orchestrator.rollback(
            request_id=(
                "request-rollback-remove"
            ),
            actor="installer",
        )
    )

    assert result.state is (
        ToolLifecycleState.ROLLED_BACK
    )
    assert result.installed_version is None

    entry = ecosystem.get("tool.secure")

    assert entry.installation.state is (
        ToolInstallationState.REMOVED
    )
    assert entry.health.state is (
        ToolHealthState.UNKNOWN
    )


def test_failed_rollback_sets_registry_unavailable() -> None:
    (
        ecosystem,
        lifecycle,
        backend,
        evaluator,
        orchestrator,
    ) = setup_orchestrator(
        installed_version="1.0.0"
    )

    del evaluator

    backend.fail_install = True
    backend.fail_rollback = True

    request_install(
        lifecycle,
        request_id="request-rollback-fail",
        require_approval=True,
        requested_version="2.0.0",
    )

    lifecycle.approve(
        request_id="request-rollback-fail",
        decided_by="admin",
    )

    with pytest.raises(RuntimeError):
        asyncio.run(
            orchestrator.install(
                request_id=(
                    "request-rollback-fail"
                ),
                actor="installer",
                policy=installation_policy(),
            )
        )

    with pytest.raises(
        RuntimeError,
        match="simulated rollback failure",
    ):
        asyncio.run(
            orchestrator.rollback(
                request_id=(
                    "request-rollback-fail"
                ),
                actor="installer",
            )
        )

    entry = ecosystem.get("tool.secure")

    assert entry.installation.state is (
        ToolInstallationState.FAILED
    )
    assert entry.health.state is (
        ToolHealthState.UNAVAILABLE
    )

    case = lifecycle.get(
        "request-rollback-fail"
    )

    assert case.state is (
        ToolLifecycleState.ROLLING_BACK
    )


def test_quarantine_and_release_update_registry() -> None:
    (
        ecosystem,
        lifecycle,
        backend,
        evaluator,
        orchestrator,
    ) = setup_orchestrator(
        installed_version="1.0.0"
    )

    del backend, evaluator

    request_install(
        lifecycle,
        request_id="request-quarantine",
        require_approval=False,
        requested_version="1.0.0",
    )

    installed = asyncio.run(
        orchestrator.install(
            request_id="request-quarantine",
            actor="installer",
            policy=installation_policy(),
        )
    )

    assert installed.state is (
        ToolLifecycleState.INSTALLED
    )
    assert installed.installed_version == "1.0.0"

    quarantined = orchestrator.quarantine(
        request_id="request-quarantine",
        actor="security",
        reason="Suspicious behavior detected.",
    )

    assert quarantined.state is (
        ToolLifecycleState.QUARANTINED
    )
    assert quarantined.quarantined_reason == (
        "Suspicious behavior detected."
    )

    entry = ecosystem.get("tool.secure")

    assert entry.installation.state is (
        ToolInstallationState.DISABLED
    )
    assert entry.health.state is (
        ToolHealthState.UNAVAILABLE
    )

    released = orchestrator.release_quarantine(
        request_id="request-quarantine",
        actor="security",
        reason="Investigation completed.",
    )

    assert released.state is (
        ToolLifecycleState.INSTALLED
    )
    assert released.quarantined_reason is None

    entry = ecosystem.get("tool.secure")

    assert entry.installation.state is (
        ToolInstallationState.INSTALLED
    )
    assert entry.health.state is (
        ToolHealthState.HEALTHY
    )


def test_revocation_disables_tool_and_records_reason() -> None:
    (
        ecosystem,
        lifecycle,
        backend,
        evaluator,
        orchestrator,
    ) = setup_orchestrator(
        installed_version="1.0.0"
    )

    del backend, evaluator

    request_install(
        lifecycle,
        request_id="request-revoke",
        require_approval=False,
    )

    revoked = orchestrator.revoke(
        request_id="request-revoke",
        actor="security",
        reason="Signing key revoked.",
    )

    assert revoked.state is (
        ToolLifecycleState.REVOKED
    )
    assert revoked.revoked_reason == (
        "Signing key revoked."
    )

    entry = ecosystem.get("tool.secure")

    assert entry.installation.state is (
        ToolInstallationState.DISABLED
    )
    assert entry.health.state is (
        ToolHealthState.UNAVAILABLE
    )


def test_remove_invokes_backend_and_updates_registry() -> None:
    (
        ecosystem,
        lifecycle,
        backend,
        evaluator,
        orchestrator,
    ) = setup_orchestrator(
        installed_version="1.0.0"
    )

    del evaluator

    request_install(
        lifecycle,
        request_id="request-remove",
        require_approval=False,
    )

    removed = asyncio.run(
        orchestrator.remove(
            request_id="request-remove",
            actor="admin",
            reason="Tool retired.",
        )
    )

    assert removed.state is (
        ToolLifecycleState.REMOVED
    )
    assert removed.installed_version is None

    assert backend.removed == [
        "tool.secure",
    ]

    entry = ecosystem.get("tool.secure")

    assert entry.installation.state is (
        ToolInstallationState.REMOVED
    )
    assert entry.health.state is (
        ToolHealthState.UNAVAILABLE
    )


def test_rejected_request_cannot_start_installation() -> None:
    (
        ecosystem,
        lifecycle,
        backend,
        evaluator,
        orchestrator,
    ) = setup_orchestrator()

    del ecosystem, backend, evaluator

    request_install(
        lifecycle,
        request_id="request-rejected",
        require_approval=True,
    )

    lifecycle.reject(
        request_id="request-rejected",
        decided_by="admin",
        reason="Policy exception denied.",
    )

    with pytest.raises(
        ToolLifecycleTransitionError,
        match="APPROVED state",
    ):
        asyncio.run(
            orchestrator.install(
                request_id="request-rejected",
                actor="installer",
                policy=installation_policy(),
            )
        )

    assert lifecycle.get(
        "request-rejected"
    ).state is ToolLifecycleState.REJECTED


def test_invalid_lifecycle_transitions_are_blocked() -> None:
    (
        ecosystem,
        lifecycle,
        backend,
        evaluator,
        orchestrator,
    ) = setup_orchestrator()

    del ecosystem, backend, evaluator, orchestrator

    request_install(
        lifecycle,
        request_id="request-invalid",
        require_approval=True,
    )

    with pytest.raises(
        ToolLifecycleTransitionError,
        match="INSTALLING state",
    ):
        lifecycle.complete_install(
            request_id="request-invalid",
            actor="installer",
            installed_version="2.0.0",
        )

    with pytest.raises(
        ToolLifecycleTransitionError,
        match="FAILED or INSTALLED",
    ):
        lifecycle.start_rollback(
            request_id="request-invalid",
            actor="installer",
        )

    with pytest.raises(
        ToolLifecycleTransitionError,
        match="Only quarantined",
    ):
        lifecycle.release_quarantine(
            request_id="request-invalid",
            actor="security",
        )
