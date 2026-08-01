from __future__ import annotations

import json
from pathlib import Path

from af_core.assurance.completion import CompletionDecision
from af_core.assurance.reviewer import ReviewResult
from af_core.assurance.validator import ValidationResult

from .manifest import (
    DeliveryArtifact,
    DeliveryManifest,
    sha256_file,
)
from .report import DeliveryReportRenderer


class DeliveryService:
    def __init__(self, output_root: str | Path) -> None:
        self.output_root = Path(
            output_root
        ).expanduser().resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        *,
        project_id: str,
        run_id: str,
        repository_path: str,
        base_revision: str,
        branch: str,
        changed_files: list[str],
        diff_text: str,
        validation: ValidationResult,
        review: ReviewResult,
        completion: CompletionDecision,
        change_summary: str,
        known_risks: list[str] | None = None,
        recommended_commit_message: str | None = None,
    ) -> DeliveryManifest:
        target = self.output_root / project_id / run_id
        target.mkdir(parents=True, exist_ok=True)

        diff_path = target / "changes.diff"
        validation_path = target / "validation.json"
        review_path = target / "review.json"
        completion_path = target / "completion.json"
        manifest_path = target / "manifest.json"
        report_path = target / "summary.md"

        self._write_text(diff_path, diff_text)
        self._write_json(
            validation_path,
            validation.model_dump(mode="json"),
        )
        self._write_json(
            review_path,
            review.model_dump(mode="json"),
        )
        self._write_json(
            completion_path,
            completion.model_dump(mode="json"),
        )

        manifest = DeliveryManifest(
            project_id=project_id,
            run_id=run_id,
            repository_path=repository_path,
            base_revision=base_revision,
            branch=branch,
            changed_files=sorted(set(changed_files)),
            validation_passed=validation.passed,
            review_decision=review.decision.value,
            completion_status=completion.status.value,
            known_risks=list(known_risks or []),
            recommended_commit_message=recommended_commit_message,
        )

        manifest.artifacts = self._artifacts(
            target,
            [
                diff_path,
                validation_path,
                review_path,
                completion_path,
            ],
        )

        self._write_json(
            manifest_path,
            manifest.model_dump(mode="json"),
        )

        report_text = DeliveryReportRenderer().render(
            manifest=manifest,
            validation=validation,
            review=review,
            completion=completion,
            change_summary=change_summary,
        )
        self._write_text(report_path, report_text)

        manifest.artifacts = self._artifacts(
            target,
            [
                diff_path,
                validation_path,
                review_path,
                completion_path,
                report_path,
            ],
        )

        self._write_json(
            manifest_path,
            manifest.model_dump(mode="json"),
        )

        return manifest

    def verify(
        self,
        *,
        project_id: str,
        run_id: str,
    ) -> bool:
        target = self.output_root / project_id / run_id
        manifest_path = target / "manifest.json"

        if not manifest_path.is_file():
            return False

        manifest = DeliveryManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )

        for artifact in manifest.artifacts:
            path = target / artifact.relative_path

            if not path.is_file():
                return False

            if path.stat().st_size != artifact.size_bytes:
                return False

            if sha256_file(path) != artifact.sha256:
                return False

        return True

    def _artifacts(
        self,
        root: Path,
        paths: list[Path],
    ) -> list[DeliveryArtifact]:
        return [
            DeliveryArtifact(
                name=path.name,
                relative_path=str(path.relative_to(root)),
                sha256=sha256_file(path),
                size_bytes=path.stat().st_size,
            )
            for path in paths
        ]

    def _write_json(
        self,
        path: Path,
        payload: dict,
    ) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    def _write_text(
        self,
        path: Path,
        content: str,
    ) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
