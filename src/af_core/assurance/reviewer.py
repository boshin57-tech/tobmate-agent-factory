from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class ReviewDecision(StrEnum):
    APPROVED = "APPROVED"
    CHANGES_REQUIRED = "CHANGES_REQUIRED"
    REJECTED = "REJECTED"


class ReviewFindingSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ReviewFinding(BaseModel):
    code: str
    severity: ReviewFindingSeverity
    message: str
    file_path: str | None = None


class ReviewInput(BaseModel):
    diff_text: str
    changed_files: list[str]
    allowed_paths: list[str] = Field(default_factory=list)
    validation_passed: bool
    acceptance_criteria: list[str] = Field(default_factory=list)


class ReviewResult(BaseModel):
    decision: ReviewDecision
    findings: list[ReviewFinding] = Field(default_factory=list)
    summary: str


class ReviewEngine:
    BINARY_MARKER = "GIT binary patch"
    SECRET_PATTERNS = (
        "OPENAI_API_KEY=",
        "AWS_SECRET_ACCESS_KEY=",
        "PRIVATE_KEY=",
        "BEGIN PRIVATE KEY",
        "password=",
    )

    def review(self, review_input: ReviewInput) -> ReviewResult:
        findings: list[ReviewFinding] = []

        if not review_input.changed_files:
            findings.append(
                ReviewFinding(
                    code="NO_CHANGES",
                    severity=ReviewFindingSeverity.ERROR,
                    message="No changed files were detected.",
                )
            )

        if not review_input.validation_passed:
            findings.append(
                ReviewFinding(
                    code="VALIDATION_FAILED",
                    severity=ReviewFindingSeverity.ERROR,
                    message="Required validation checks did not pass.",
                )
            )

        findings.extend(
            self._review_paths(
                review_input.changed_files,
                review_input.allowed_paths,
            )
        )
        findings.extend(
            self._review_diff(review_input.diff_text)
        )

        decision = self._decision(findings)

        summary = (
            f"Review {decision.value}; "
            f"{len(findings)} finding(s); "
            f"{len(review_input.changed_files)} changed file(s)."
        )

        return ReviewResult(
            decision=decision,
            findings=findings,
            summary=summary,
        )

    def _review_paths(
        self,
        changed_files: list[str],
        allowed_paths: list[str],
    ) -> list[ReviewFinding]:
        if not allowed_paths:
            return []

        findings: list[ReviewFinding] = []

        for value in changed_files:
            path = Path(value)

            if self._is_allowed(path, allowed_paths):
                continue

            findings.append(
                ReviewFinding(
                    code="OUT_OF_SCOPE_FILE",
                    severity=ReviewFindingSeverity.ERROR,
                    message="Changed file is outside the allowed scope.",
                    file_path=value,
                )
            )

        return findings

    def _is_allowed(
        self,
        path: Path,
        allowed_paths: list[str],
    ) -> bool:
        path_text = path.as_posix()

        for allowed in allowed_paths:
            normalized = Path(allowed).as_posix().rstrip("/")

            if (
                path_text == normalized
                or path_text.startswith(normalized + "/")
            ):
                return True

        return False

    def _review_diff(
        self,
        diff_text: str,
    ) -> list[ReviewFinding]:
        findings: list[ReviewFinding] = []

        if not diff_text.strip():
            findings.append(
                ReviewFinding(
                    code="EMPTY_DIFF",
                    severity=ReviewFindingSeverity.WARNING,
                    message="The diff is empty.",
                )
            )
            return findings

        if self.BINARY_MARKER in diff_text:
            findings.append(
                ReviewFinding(
                    code="BINARY_CHANGE",
                    severity=ReviewFindingSeverity.WARNING,
                    message="Binary content was changed.",
                )
            )

        lowered = diff_text.lower()

        for pattern in self.SECRET_PATTERNS:
            if pattern.lower() in lowered:
                findings.append(
                    ReviewFinding(
                        code="POTENTIAL_SECRET",
                        severity=ReviewFindingSeverity.CRITICAL,
                        message=(
                            "Potential secret material appears in the diff: "
                            f"{pattern}"
                        ),
                    )
                )

        if "+<<<<<<<" in diff_text or "+=======" in diff_text:
            findings.append(
                ReviewFinding(
                    code="CONFLICT_MARKER",
                    severity=ReviewFindingSeverity.CRITICAL,
                    message="Merge conflict markers appear in added lines.",
                )
            )

        return findings

    def _decision(
        self,
        findings: list[ReviewFinding],
    ) -> ReviewDecision:
        severities = {
            finding.severity
            for finding in findings
        }

        if ReviewFindingSeverity.CRITICAL in severities:
            return ReviewDecision.REJECTED

        if ReviewFindingSeverity.ERROR in severities:
            return ReviewDecision.CHANGES_REQUIRED

        return ReviewDecision.APPROVED
