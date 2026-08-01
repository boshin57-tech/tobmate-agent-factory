from pathlib import Path
import asyncio
import subprocess
import sys

from af_core.assurance.validator import (
    ValidationCheck,
    ValidationEngine,
    ValidationPlan,
    ValidationStatus,
)


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def create_repo(path: Path) -> Path:
    path.mkdir()
    git(path, "init")
    git(path, "config", "user.name", "AF Test")
    git(path, "config", "user.email", "af@example.com")

    (path / "app.py").write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )

    git(path, "add", ".")
    git(path, "commit", "-m", "initial")
    return path


def run(coro):
    return asyncio.run(coro)


def test_validation_engine_passes_required_checks(
    tmp_path: Path,
) -> None:
    repo = create_repo(tmp_path / "repo")
    engine = ValidationEngine(repo)

    plan = ValidationPlan(
        checks=[
            ValidationCheck(
                name="python-success",
                command=[
                    sys.executable,
                    "-c",
                    "print('ok')",
                ],
            ),
            ValidationCheck(
                name="git-diff-check",
                command=["git", "diff", "--check"],
            ),
        ]
    )

    result = run(engine.validate(plan))

    assert result.passed is True
    assert all(
        check.status is ValidationStatus.PASSED
        for check in result.checks
    )
    assert result.failures == []


def test_validation_engine_fails_required_check(
    tmp_path: Path,
) -> None:
    repo = create_repo(tmp_path / "repo")
    engine = ValidationEngine(repo)

    plan = ValidationPlan(
        checks=[
            ValidationCheck(
                name="failing-check",
                command=[
                    sys.executable,
                    "-c",
                    "raise SystemExit(3)",
                ],
            )
        ]
    )

    result = run(engine.validate(plan))

    assert result.passed is False
    assert result.checks[0].status is ValidationStatus.FAILED
    assert result.failures


def test_optional_failure_does_not_fail_plan(
    tmp_path: Path,
) -> None:
    repo = create_repo(tmp_path / "repo")
    engine = ValidationEngine(repo)

    plan = ValidationPlan(
        checks=[
            ValidationCheck(
                name="optional-failure",
                command=[
                    sys.executable,
                    "-c",
                    "raise SystemExit(2)",
                ],
                required=False,
            )
        ]
    )

    result = run(engine.validate(plan))

    assert result.passed is True
    assert result.checks[0].status is ValidationStatus.FAILED
