from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_doc(relative: str) -> str:
    path = ROOT / relative
    assert path.is_file(), path
    return path.read_text(encoding="utf-8")


def test_agent_operation_prompt_manual_contract() -> None:
    text = read_doc(
        "docs/manuals/"
        "AF_CORE_AGENT_OPERATION_PROMPT_MANUAL.md"
    )

    for number in range(1, 13):
        assert f"## {number}." in text

    assert "ROLLBACK AND RECOVERY:" in text
    assert "## 12. Completion Declaration" in text
    assert "Remaining risks:ns::" not in text


def test_agent_execution_guide_contract() -> None:
    text = read_doc(
        "docs/guides/"
        "AF_CORE_AGENT_EXECUTION_GUIDE.md"
    )

    for number in range(1, 13):
        assert f"## {number}." in text

    assert "## 9. Failure, Retry, and Recovery" in text
    assert "## 12. Final Delivery" in text


def test_prompt_template_catalog_contract() -> None:
    text = read_doc(
        "docs/templates/"
        "AF_CORE_PROMPT_TEMPLATE_CATALOG.md"
    )

    assert "## 3. Repository Implementation Template" in text
    assert "## 4. Defect Remediation Template" in text
    assert (
        "## 5. Production Release and Deployment Template"
        in text
    )
    assert text.count("```") == 6


def test_final_production_acceptance_contract() -> None:
    text = read_doc(
        "docs/operations/"
        "AF_CORE_FINAL_PRODUCTION_ACCEPTANCE.md"
    )

    for number in range(1, 11):
        assert f"## {number}." in text

    assert "Candidate package version: `1.1.0`" in text
    assert "Status: `ACCEPTED`" in text
    assert "rollback to `1.0.0` passes" in text
    assert "recovery promotion to `1.1.0` passes" in text


def test_final_closure_report_contract() -> None:
    text = read_doc(
        "docs/final/"
        "AF_CORE_FINAL_CLOSURE_REPORT.md"
    )

    for number in range(1, 10):
        assert f"## {number}." in text

    assert "Final package version: `1.1.0`" in text
    assert "1031 of 1031 passed" in text
    assert "checkpoint-19-af-core-final-closure-v1" in text
    assert "Status: `FINAL CLOSURE AUTHORIZED`" in text
    assert "final-release/SHA256SUMS" in text
    assert "avoids embedding" in text
