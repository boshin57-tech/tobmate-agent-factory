"""Final delivery lifecycle for autonomous project execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping
from uuid import uuid4

from af_core.orchestrator.project_completion_audit import (
    ProjectCompletionAudit,
    ProjectCompletionAuditEngine,
    ProjectCompletionDecision,
    ProjectValidationResult,
)
from af_core.orchestrator.project_execution_models import (
    ProjectRunEventKind,
    ProjectRunSnapshot,
    ProjectRunState,
    ProjectRunStatus,
)
from af_core.orchestrator.project_execution_repository import (
    ProjectRunRepository,
)


class ProjectDeliveryError(ValueError):
    """Raised when final project delivery is invalid."""


@dataclass(frozen=True, slots=True)
class ProjectDeliveryArtifact:
    """One task output included in final delivery."""

    task_id: str
    reference: str

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise ProjectDeliveryError(
                "artifact task_id must not be empty"
            )

        if not self.reference.strip():
            raise ProjectDeliveryError(
                "artifact reference must not be empty"
            )


@dataclass(frozen=True, slots=True)
class ProjectDeliveryManifest:
    """Immutable manifest for one finalized project run."""

    delivery_id: str
    run_id: str
    project_id: str
    repository_path: str
    decision: ProjectCompletionDecision
    created_at: float
    artifacts: tuple[ProjectDeliveryArtifact, ...]
    task_statuses: Mapping[str, str]
    reasons: tuple[str, ...]
    metadata: Mapping[str, object] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        identifiers = (
            self.delivery_id,
            self.run_id,
            self.project_id,
            self.repository_path,
        )

        if any(
            not value.strip()
            for value in identifiers
        ):
            raise ProjectDeliveryError(
                "delivery identifiers must not be empty"
            )


@dataclass(frozen=True, slots=True)
class ProjectDeliveryPackage:
    """Final state, audit and manifest delivered together."""

    state: ProjectRunState
    audit: ProjectCompletionAudit
    manifest: ProjectDeliveryManifest


@dataclass(frozen=True, slots=True)
class ProjectDeliveryFiles:
    """Locations of materialized delivery files."""

    manifest_path: Path
    audit_path: Path
    report_path: Path


class ProjectDeliveryLifecycleService:
    """Audit and finalize autonomous project runs."""

    def __init__(
        self,
        repository: ProjectRunRepository,
        audit_engine: ProjectCompletionAuditEngine | None = None,
    ) -> None:
        self._repository = repository
        self._audit = (
            audit_engine
            or ProjectCompletionAuditEngine()
        )

    @property
    def repository(
        self,
    ) -> ProjectRunRepository:
        return self._repository

    def begin_validation(
        self,
        run_id: str,
        *,
        now: float,
    ) -> ProjectRunSnapshot:
        """Move a running project into final validation."""

        current = self._repository.get(run_id)

        if (
            current.state.status
            is not ProjectRunStatus.RUNNING
        ):
            raise ProjectDeliveryError(
                "only running runs may enter validation"
            )

        validating = current.state.transition(
            ProjectRunStatus.VALIDATING,
            now=now,
        )

        return self._repository.save(
            validating,
            expected_version=current.state.version,
            occurred_at=now,
            event_kind=(
                ProjectRunEventKind.RUN_TRANSITIONED
            ),
            detail={
                "previous_status": (
                    current.state.status.value
                ),
                "status": validating.status.value,
            },
        )

    def finalize(
        self,
        run_id: str,
        *,
        validations: Iterable[
            ProjectValidationResult
        ] = (),
        now: float,
        metadata: Mapping[str, object] | None = None,
    ) -> ProjectDeliveryPackage:
        """Audit, finalize and package a validated run."""

        current = self._repository.get(run_id)

        if (
            current.state.status
            is not ProjectRunStatus.VALIDATING
        ):
            raise ProjectDeliveryError(
                "run must be validating before delivery"
            )

        audit = self._audit.audit(
            current.state,
            validations=validations,
            now=now,
            metadata=metadata,
        )

        target_status = {
            ProjectCompletionDecision.COMPLETED: (
                ProjectRunStatus.COMPLETED
            ),
            ProjectCompletionDecision.PARTIAL: (
                ProjectRunStatus.PARTIAL
            ),
            ProjectCompletionDecision.FAILED: (
                ProjectRunStatus.FAILED
            ),
        }[audit.decision]

        finalized = current.state.transition(
            target_status,
            now=now,
        )

        saved = self._repository.save(
            finalized,
            expected_version=current.state.version,
            occurred_at=now,
            event_kind=(
                ProjectRunEventKind.DELIVERY_CREATED
            ),
            detail={
                "decision": audit.decision.value,
                "total_tasks": audit.total_tasks,
                "succeeded_tasks": (
                    audit.succeeded_tasks
                ),
                "failed_tasks": audit.failed_tasks,
                "validation_passed": (
                    audit.validation_passed
                ),
                "validation_failed": (
                    audit.validation_failed
                ),
            },
        )

        manifest = self._build_manifest(
            saved.state,
            audit,
            now=now,
            metadata=metadata,
        )

        return ProjectDeliveryPackage(
            state=saved.state,
            audit=audit,
            manifest=manifest,
        )

    @staticmethod
    def _build_manifest(
        state: ProjectRunState,
        audit: ProjectCompletionAudit,
        *,
        now: float,
        metadata: Mapping[str, object] | None,
    ) -> ProjectDeliveryManifest:
        artifacts = tuple(
            ProjectDeliveryArtifact(
                task_id=task_id,
                reference=task.output_reference,
            )
            for task_id, task in sorted(
                state.tasks.items()
            )
            if task.output_reference is not None
        )

        return ProjectDeliveryManifest(
            delivery_id=(
                f"delivery-{uuid4().hex}"
            ),
            run_id=state.run_id,
            project_id=state.project_id,
            repository_path=state.repository_path,
            decision=audit.decision,
            created_at=now,
            artifacts=artifacts,
            task_statuses=dict(
                audit.task_statuses
            ),
            reasons=audit.reasons,
            metadata=dict(metadata or {}),
        )


import json
import os
import tempfile


class JsonProjectDeliveryWriter:
    """Atomically materialize final project delivery files."""

    def write(
        self,
        package: ProjectDeliveryPackage,
        destination: str | Path,
    ) -> ProjectDeliveryFiles:
        """Write manifest, audit and human-readable report."""

        root = Path(destination) / package.state.run_id
        root.mkdir(
            parents=True,
            exist_ok=True,
        )

        manifest_path = (
            root / "delivery-manifest.json"
        )
        audit_path = (
            root / "completion-audit.json"
        )
        report_path = (
            root / "delivery-report.txt"
        )

        self._atomic_write(
            manifest_path,
            json.dumps(
                self._manifest_payload(
                    package.manifest
                ),
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )

        self._atomic_write(
            audit_path,
            json.dumps(
                self._audit_payload(
                    package.audit
                ),
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )

        self._atomic_write(
            report_path,
            self._report(package),
        )

        return ProjectDeliveryFiles(
            manifest_path=manifest_path,
            audit_path=audit_path,
            report_path=report_path,
        )

    @staticmethod
    def _manifest_payload(
        manifest: ProjectDeliveryManifest,
    ) -> dict[str, object]:
        return {
            "delivery_id": manifest.delivery_id,
            "run_id": manifest.run_id,
            "project_id": manifest.project_id,
            "repository_path": (
                manifest.repository_path
            ),
            "decision": manifest.decision.value,
            "created_at": manifest.created_at,
            "artifacts": [
                {
                    "task_id": artifact.task_id,
                    "reference": artifact.reference,
                }
                for artifact in manifest.artifacts
            ],
            "task_statuses": dict(
                manifest.task_statuses
            ),
            "reasons": list(manifest.reasons),
            "metadata": dict(manifest.metadata),
        }

    @staticmethod
    def _audit_payload(
        audit: ProjectCompletionAudit,
    ) -> dict[str, object]:
        return {
            "run_id": audit.run_id,
            "project_id": audit.project_id,
            "decision": audit.decision.value,
            "audited_at": audit.audited_at,
            "total_tasks": audit.total_tasks,
            "succeeded_tasks": (
                audit.succeeded_tasks
            ),
            "failed_tasks": audit.failed_tasks,
            "skipped_tasks": audit.skipped_tasks,
            "cancelled_tasks": (
                audit.cancelled_tasks
            ),
            "validation_passed": (
                audit.validation_passed
            ),
            "validation_failed": (
                audit.validation_failed
            ),
            "validation_partial": (
                audit.validation_partial
            ),
            "validation_not_run": (
                audit.validation_not_run
            ),
            "output_references": list(
                audit.output_references
            ),
            "reasons": list(audit.reasons),
            "task_statuses": dict(
                audit.task_statuses
            ),
            "metadata": dict(audit.metadata),
        }

    @staticmethod
    def _report(
        package: ProjectDeliveryPackage,
    ) -> str:
        manifest = package.manifest
        audit = package.audit

        lines = [
            "TOBMATE AGENT FACTORY PROJECT DELIVERY",
            "=" * 42,
            f"Delivery ID: {manifest.delivery_id}",
            f"Run ID: {manifest.run_id}",
            f"Project ID: {manifest.project_id}",
            f"Decision: {manifest.decision.value}",
            (
                "Repository: "
                f"{manifest.repository_path}"
            ),
            "",
            "Execution Summary",
            "-----------------",
            f"Total tasks: {audit.total_tasks}",
            (
                "Succeeded: "
                f"{audit.succeeded_tasks}"
            ),
            f"Failed: {audit.failed_tasks}",
            f"Skipped: {audit.skipped_tasks}",
            (
                "Cancelled: "
                f"{audit.cancelled_tasks}"
            ),
            "",
            "Validation Summary",
            "------------------",
            (
                "Passed: "
                f"{audit.validation_passed}"
            ),
            (
                "Failed: "
                f"{audit.validation_failed}"
            ),
            (
                "Partial: "
                f"{audit.validation_partial}"
            ),
            (
                "Not run: "
                f"{audit.validation_not_run}"
            ),
            "",
            "Artifacts",
            "---------",
        ]

        if manifest.artifacts:
            lines.extend(
                (
                    f"- {artifact.task_id}: "
                    f"{artifact.reference}"
                )
                for artifact in manifest.artifacts
            )
        else:
            lines.append("- None")

        lines.extend(
            [
                "",
                "Audit Reasons",
                "-------------",
            ]
        )

        if audit.reasons:
            lines.extend(
                f"- {reason}"
                for reason in audit.reasons
            )
        else:
            lines.append("- None")

        return "\n".join(lines) + "\n"

    @staticmethod
    def _atomic_write(
        path: Path,
        content: str,
    ) -> None:
        descriptor, temporary_name = (
            tempfile.mkstemp(
                prefix=f".{path.name}.",
                suffix=".tmp",
                dir=path.parent,
            )
        )

        temporary_path = Path(
            temporary_name
        )

        try:
            with os.fdopen(
                descriptor,
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())

            os.replace(
                temporary_path,
                path,
            )
        finally:
            temporary_path.unlink(
                missing_ok=True
            )
