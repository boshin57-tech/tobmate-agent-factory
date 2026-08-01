from af_core.assurance.reviewer import (
    ReviewDecision,
    ReviewEngine,
    ReviewInput,
)


def test_review_approves_valid_change() -> None:
    result = ReviewEngine().review(
        ReviewInput(
            diff_text=(
                "diff --git a/src/app.py b/src/app.py\n"
                "+VALUE = 2\n"
            ),
            changed_files=["src/app.py"],
            allowed_paths=["src"],
            validation_passed=True,
            acceptance_criteria=["Value updated"],
        )
    )

    assert result.decision is ReviewDecision.APPROVED
    assert result.findings == []


def test_review_requires_changes_for_out_of_scope_file() -> None:
    result = ReviewEngine().review(
        ReviewInput(
            diff_text=(
                "diff --git a/config.env b/config.env\n"
                "+SETTING=true\n"
            ),
            changed_files=["config.env"],
            allowed_paths=["src", "tests"],
            validation_passed=True,
        )
    )

    assert result.decision is ReviewDecision.CHANGES_REQUIRED
    assert any(
        finding.code == "OUT_OF_SCOPE_FILE"
        for finding in result.findings
    )


def test_review_requires_changes_when_validation_failed() -> None:
    result = ReviewEngine().review(
        ReviewInput(
            diff_text="+VALUE = 2\n",
            changed_files=["src/app.py"],
            allowed_paths=["src"],
            validation_passed=False,
        )
    )

    assert result.decision is ReviewDecision.CHANGES_REQUIRED
    assert any(
        finding.code == "VALIDATION_FAILED"
        for finding in result.findings
    )


def test_review_rejects_potential_secret() -> None:
    result = ReviewEngine().review(
        ReviewInput(
            diff_text="+OPENAI_API_KEY=secret-value\n",
            changed_files=["src/config.py"],
            allowed_paths=["src"],
            validation_passed=True,
        )
    )

    assert result.decision is ReviewDecision.REJECTED
    assert any(
        finding.code == "POTENTIAL_SECRET"
        for finding in result.findings
    )


def test_review_rejects_conflict_markers() -> None:
    result = ReviewEngine().review(
        ReviewInput(
            diff_text=(
                "+<<<<<<< HEAD\n"
                "+VALUE = 1\n"
                "+=======\n"
            ),
            changed_files=["src/app.py"],
            allowed_paths=["src"],
            validation_passed=True,
        )
    )

    assert result.decision is ReviewDecision.REJECTED
    assert any(
        finding.code == "CONFLICT_MARKER"
        for finding in result.findings
    )
