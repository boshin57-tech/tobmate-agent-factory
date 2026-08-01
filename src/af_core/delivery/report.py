from __future__ import annotations

from af_core.assurance.completion import CompletionDecision
from af_core.assurance.reviewer import ReviewResult
from af_core.assurance.validator import ValidationResult

from .manifest import DeliveryManifest


class DeliveryReportRenderer:
    def render(
        self,
        *,
        manifest: DeliveryManifest,
        validation: ValidationResult,
        review: ReviewResult,
        completion: CompletionDecision,
        change_summary: str,
    ) -> str:
        changed_files = (
            "\n".join(
                f"- `{path}`"
                for path in manifest.changed_files
            )
            or "- None"
        )

        validation_checks = (
            "\n".join(
                f"- **{check.name}**: {check.status.value}"
                for check in validation.checks
            )
            or "- No validation checks"
        )

        review_findings = (
            "\n".join(
                (
                    f"- **{finding.severity.value} "
                    f"{finding.code}**: {finding.message}"
                )
                for finding in review.findings
            )
            or "- No findings"
        )

        missing = (
            "\n".join(
                f"- {item}"
                for item in completion.missing_requirements
            )
            or "- None"
        )

        risks = (
            "\n".join(
                f"- {item}"
                for item in manifest.known_risks
            )
            or "- None"
        )

        artifacts = (
            "\n".join(
                (
                    f"- `{artifact.relative_path}` "
                    f"({artifact.size_bytes} bytes, "
                    f"SHA-256 `{artifact.sha256}`)"
                )
                for artifact in manifest.artifacts
            )
            or "- None"
        )

        return f"""# AF-Core Delivery Report

## Identity

- Delivery ID: `{manifest.delivery_id}`
- Project ID: `{manifest.project_id}`
- Run ID: `{manifest.run_id}`
- Repository: `{manifest.repository_path}`
- Base revision: `{manifest.base_revision}`
- Branch: `{manifest.branch}`

## Change summary

{change_summary}

## Changed files

{changed_files}

## Validation

- Overall passed: `{validation.passed}`
- Summary: {validation.evidence_summary}

{validation_checks}

## Review

- Decision: `{review.decision.value}`
- Summary: {review.summary}

{review_findings}

## Completion

- Status: `{completion.status.value}`
- Recommended action: {completion.recommended_action}

### Missing requirements

{missing}

## Known risks

{risks}

## Recommended commit message

`{manifest.recommended_commit_message or "Not provided"}`

## Artifacts

{artifacts}
"""
