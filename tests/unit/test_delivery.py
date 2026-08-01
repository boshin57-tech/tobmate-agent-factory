from pathlib import Path

from af_core.assurance.completion import (
    CompletionDecision,
    CompletionStatus,
)
from af_core.assurance.reviewer import (
    ReviewDecision,
    ReviewResult,
)
from af_core.assurance.validator import (
    ValidationCheck,
    ValidationResult,
    ValidationStatus,
)
from af_core.delivery.service import DeliveryService


def make_validation() -> ValidationResult:
    return ValidationResult(
        passed=True,
        checks=[
            ValidationCheck(
                name="pytest",
                command=["pytest"],
                status=ValidationStatus.PASSED,
                returncode=0,
            )
        ],
        failures=[],
        evidence_summary="1 check passed",
    )


def make_review() -> ReviewResult:
    return ReviewResult(
        decision=ReviewDecision.APPROVED,
        findings=[],
        summary="Review approved",
    )


def make_completion() -> CompletionDecision:
    return CompletionDecision(
        status=CompletionStatus.COMPLETE,
        satisfied_requirements=[
            "All tasks complete",
        ],
        missing_requirements=[],
        risks=[],
        recommended_action=(
            "Prepare delivery artifacts."
        ),
    )


def test_delivery_service_generates_artifacts(
    tmp_path: Path,
) -> None:
    service = DeliveryService(tmp_path / "reports")

    manifest = service.create(
        project_id="project-1",
        run_id="run-1",
        repository_path="/tmp/repository",
        base_revision="abc123",
        branch="af/project-1/run-1",
        changed_files=[
            "src/app.py",
            "tests/test_app.py",
        ],
        diff_text=(
            "diff --git a/src/app.py b/src/app.py\n"
            "+VALUE = 2\n"
        ),
        validation=make_validation(),
        review=make_review(),
        completion=make_completion(),
        change_summary="Updated the application value.",
        known_risks=[],
        recommended_commit_message=(
            "feat: update application value"
        ),
    )

    target = (
        tmp_path
        / "reports"
        / "project-1"
        / "run-1"
    )

    assert manifest.validation_passed is True
    assert (target / "changes.diff").is_file()
    assert (target / "validation.json").is_file()
    assert (target / "review.json").is_file()
    assert (target / "completion.json").is_file()
    assert (target / "manifest.json").is_file()
    assert (target / "summary.md").is_file()

    report = (
        target / "summary.md"
    ).read_text(encoding="utf-8")

    assert "AF-Core Delivery Report" in report
    assert "feat: update application value" in report
    assert service.verify(
        project_id="project-1",
        run_id="run-1",
    )


def test_delivery_verification_detects_tampering(
    tmp_path: Path,
) -> None:
    service = DeliveryService(tmp_path / "reports")

    service.create(
        project_id="project-1",
        run_id="run-1",
        repository_path="/tmp/repository",
        base_revision="abc123",
        branch="af/project-1/run-1",
        changed_files=["src/app.py"],
        diff_text="+VALUE = 2\n",
        validation=make_validation(),
        review=make_review(),
        completion=make_completion(),
        change_summary="Updated value.",
    )

    diff_path = (
        tmp_path
        / "reports"
        / "project-1"
        / "run-1"
        / "changes.diff"
    )

    diff_path.write_text(
        "tampered",
        encoding="utf-8",
    )

    assert not service.verify(
        project_id="project-1",
        run_id="run-1",
    )
