from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from af_core.production.deployment_models import (
    ReleaseIdentity,
)
from af_core.production.release_models import (
    ReleaseCommand,
    ReleaseCommandOutcome,
    ReleaseDrillStatus,
    ReleaseMode,
    ReleasePhase,
    ReleaseRunbookPlan,
)
from af_core.production.release_runbook import (
    ReleaseRunbookService,
)


NOW = datetime(
    2026,
    8,
    4,
    9,
    0,
    tzinfo=timezone.utc,
)

RELEASE_ID = (
    "release-"
    "11223344556677889900aabbccddeeff"
)


def make_identity() -> ReleaseIdentity:
    return ReleaseIdentity(
        release_id=RELEASE_ID,
        application_name="af-core",
        version="1.0.0",
        git_commit="e3b0f1b",
    )


def make_command(
    working_directory: Path,
    step_id: str,
    phase: ReleasePhase,
    *,
    required: bool = True,
    timeout_seconds: float = 30.0,
) -> ReleaseCommand:
    return ReleaseCommand(
        step_id=step_id,
        phase=phase,
        argv=(
            "python",
            "-c",
            "pass",
        ),
        working_directory=working_directory,
        timeout_seconds=timeout_seconds,
        required=required,
    )


def make_install_plan(
    tmp_path: Path,
    *,
    report_name: str = "release-report.json",
) -> ReleaseRunbookPlan:
    steps = (
        make_command(
            tmp_path,
            "preflight",
            ReleasePhase.PREFLIGHT,
        ),
        make_command(
            tmp_path,
            "verify-package",
            ReleasePhase.VERIFY_PACKAGE,
        ),
        make_command(
            tmp_path,
            "install",
            ReleasePhase.INSTALL,
        ),
        make_command(
            tmp_path,
            "configure",
            ReleasePhase.CONFIGURE,
        ),
        make_command(
            tmp_path,
            "start",
            ReleasePhase.START,
        ),
        make_command(
            tmp_path,
            "health",
            ReleasePhase.HEALTH,
        ),
        make_command(
            tmp_path,
            "evidence",
            ReleasePhase.EVIDENCE,
        ),
    )

    return ReleaseRunbookPlan(
        identity=make_identity(),
        mode=ReleaseMode.INSTALL,
        steps=steps,
        report_path=(
            tmp_path
            / "reports"
            / report_name
        ),
        rollback_on_failure=False,
    )


class RecordingRunner:
    def __init__(
        self,
        outcomes: dict[
            str,
            ReleaseCommandOutcome,
        ] | None = None,
    ) -> None:
        self.outcomes = outcomes or {}
        self.calls: list[str] = []

    async def __call__(
        self,
        command: ReleaseCommand,
    ) -> ReleaseCommandOutcome:
        self.calls.append(
            command.step_id
        )

        return self.outcomes.get(
            command.step_id,
            ReleaseCommandOutcome(
                exit_code=0,
                duration_seconds=0.01,
            ),
        )


def test_release_command_normalizes_values(
    tmp_path: Path,
) -> None:
    command = ReleaseCommand(
        step_id="  Preflight  ",
        phase=ReleasePhase.PREFLIGHT,
        argv=(
            " python ",
            " -c ",
            " pass ",
        ),
        working_directory=tmp_path,
        expected_exit_codes=(
            2,
            0,
        ),
    )

    assert command.step_id == "preflight"
    assert command.argv == (
        "python",
        "-c",
        "pass",
    )
    assert command.expected_exit_codes == (
        0,
        2,
    )


def test_release_command_rejects_relative_directory() -> None:
    with pytest.raises(
        ValidationError,
        match="absolute",
    ):
        ReleaseCommand(
            step_id="preflight",
            phase=ReleasePhase.PREFLIGHT,
            argv=("true",),
            working_directory=Path(
                "relative-directory"
            ),
        )


def test_release_plan_rejects_out_of_order_phases(
    tmp_path: Path,
) -> None:
    steps = (
        make_command(
            tmp_path,
            "preflight",
            ReleasePhase.PREFLIGHT,
        ),
        make_command(
            tmp_path,
            "start",
            ReleasePhase.START,
        ),
        make_command(
            tmp_path,
            "install",
            ReleasePhase.INSTALL,
        ),
        make_command(
            tmp_path,
            "verify-package",
            ReleasePhase.VERIFY_PACKAGE,
        ),
        make_command(
            tmp_path,
            "configure",
            ReleasePhase.CONFIGURE,
        ),
        make_command(
            tmp_path,
            "health",
            ReleasePhase.HEALTH,
        ),
        make_command(
            tmp_path,
            "evidence",
            ReleasePhase.EVIDENCE,
        ),
    )

    with pytest.raises(
        ValidationError,
        match="must be ordered",
    ):
        ReleaseRunbookPlan(
            identity=make_identity(),
            mode=ReleaseMode.INSTALL,
            steps=steps,
            report_path=(
                tmp_path / "report.json"
            ),
            rollback_on_failure=False,
        )


def test_release_plan_rejects_duplicate_step_ids(
    tmp_path: Path,
) -> None:
    plan = make_install_plan(
        tmp_path
    )

    duplicated = (
        plan.steps[:-1]
        + (
            plan.steps[-1].model_copy(
                update={
                    "step_id": "preflight",
                }
            ),
        )
    )

    with pytest.raises(
        ValidationError,
        match="must be unique",
    ):
        ReleaseRunbookPlan(
            identity=plan.identity,
            mode=plan.mode,
            steps=duplicated,
            report_path=plan.report_path,
            rollback_on_failure=False,
        )


@pytest.mark.asyncio
async def test_successful_install_drill_publishes_report(
    tmp_path: Path,
) -> None:
    runner = RecordingRunner()
    plan = make_install_plan(
        tmp_path
    )

    result = await ReleaseRunbookService(
        runner=runner,
        clock=lambda: NOW,
    ).execute(plan)

    assert (
        result.report.status
        is ReleaseDrillStatus.PASSED
    )
    assert result.report.total_steps == 7
    assert result.report.passed_steps == 7
    assert result.report.failed_steps == 0
    assert result.report.skipped_steps == 0
    assert (
        result.report.rollback_triggered
        is False
    )

    assert runner.calls == [
        "preflight",
        "verify-package",
        "install",
        "configure",
        "start",
        "health",
        "evidence",
    ]

    assert result.report_path.is_file()

    payload = json.loads(
        result.report_path.read_text(
            encoding="utf-8"
        )
    )

    assert payload["status"] == "passed"
    assert payload["passed_steps"] == 7

    serialized = (
        result.report_path.read_text(
            encoding="utf-8"
        )
    )

    assert "argv" not in serialized
    assert "working_directory" not in serialized

from af_core.production.release_models import (
    ReleaseStepStatus,
)


def make_upgrade_plan(
    tmp_path: Path,
) -> ReleaseRunbookPlan:
    steps = (
        make_command(
            tmp_path,
            "upgrade-preflight",
            ReleasePhase.PREFLIGHT,
        ),
        make_command(
            tmp_path,
            "backup",
            ReleasePhase.BACKUP,
        ),
        make_command(
            tmp_path,
            "verify-upgrade",
            ReleasePhase.VERIFY_PACKAGE,
        ),
        make_command(
            tmp_path,
            "stop-current",
            ReleasePhase.STOP,
        ),
        make_command(
            tmp_path,
            "install-upgrade",
            ReleasePhase.INSTALL,
        ),
        make_command(
            tmp_path,
            "configure-upgrade",
            ReleasePhase.CONFIGURE,
        ),
        make_command(
            tmp_path,
            "start-upgrade",
            ReleasePhase.START,
        ),
        make_command(
            tmp_path,
            "health-upgrade",
            ReleasePhase.HEALTH,
        ),
        make_command(
            tmp_path,
            "upgrade-evidence",
            ReleasePhase.EVIDENCE,
        ),
    )

    rollback_steps = (
        make_command(
            tmp_path,
            "rollback-stop",
            ReleasePhase.STOP,
        ),
        make_command(
            tmp_path,
            "restore-release",
            ReleasePhase.ROLLBACK,
        ),
        make_command(
            tmp_path,
            "rollback-start",
            ReleasePhase.START,
        ),
        make_command(
            tmp_path,
            "rollback-health",
            ReleasePhase.HEALTH,
        ),
        make_command(
            tmp_path,
            "rollback-evidence",
            ReleasePhase.EVIDENCE,
        ),
    )

    return ReleaseRunbookPlan(
        identity=make_identity(),
        mode=ReleaseMode.UPGRADE,
        steps=steps,
        rollback_steps=rollback_steps,
        report_path=(
            tmp_path
            / "reports"
            / "upgrade-report.json"
        ),
        rollback_on_failure=True,
    )


@pytest.mark.asyncio
async def test_required_upgrade_failure_triggers_rollback(
    tmp_path: Path,
) -> None:
    runner = RecordingRunner(
        {
            "install-upgrade": (
                ReleaseCommandOutcome(
                    exit_code=7,
                    duration_seconds=0.02,
                )
            )
        }
    )

    result = await ReleaseRunbookService(
        runner=runner,
        clock=lambda: NOW,
    ).execute(
        make_upgrade_plan(tmp_path)
    )

    assert (
        result.report.status
        is ReleaseDrillStatus.ROLLED_BACK
    )
    assert (
        result.report.rollback_triggered
        is True
    )
    assert (
        result.report.failure_step_id
        == "install-upgrade"
    )
    assert result.report.failed_steps == 1
    assert result.report.skipped_steps == 4
    assert result.report.passed_steps == 9

    assert runner.calls == [
        "upgrade-preflight",
        "backup",
        "verify-upgrade",
        "stop-current",
        "install-upgrade",
        "rollback-stop",
        "restore-release",
        "rollback-start",
        "rollback-health",
        "rollback-evidence",
    ]


@pytest.mark.asyncio
async def test_failed_rollback_reports_final_failure(
    tmp_path: Path,
) -> None:
    runner = RecordingRunner(
        {
            "install-upgrade": (
                ReleaseCommandOutcome(
                    exit_code=1,
                    duration_seconds=0.01,
                )
            ),
            "restore-release": (
                ReleaseCommandOutcome(
                    exit_code=2,
                    duration_seconds=0.01,
                )
            ),
        }
    )

    result = await ReleaseRunbookService(
        runner=runner,
        clock=lambda: NOW,
    ).execute(
        make_upgrade_plan(tmp_path)
    )

    assert (
        result.report.status
        is ReleaseDrillStatus.FAILED
    )
    assert (
        result.report.rollback_triggered
        is True
    )
    assert result.report.failed_steps == 2

    by_id = {
        item.step_id: item
        for item in result.report.results
    }

    assert (
        by_id["restore-release"].status
        is ReleaseStepStatus.FAILED
    )
    assert (
        by_id["rollback-start"].status
        is ReleaseStepStatus.SKIPPED
    )
    assert (
        by_id["rollback-health"].status
        is ReleaseStepStatus.SKIPPED
    )


@pytest.mark.asyncio
async def test_optional_failure_continues_without_rollback(
    tmp_path: Path,
) -> None:
    plan = make_install_plan(tmp_path)

    steps = tuple(
        step.model_copy(
            update={"required": False}
        )
        if step.step_id == "configure"
        else step
        for step in plan.steps
    )

    plan = plan.model_copy(
        update={"steps": steps}
    )

    runner = RecordingRunner(
        {
            "configure": (
                ReleaseCommandOutcome(
                    exit_code=3,
                    duration_seconds=0.01,
                )
            )
        }
    )

    result = await ReleaseRunbookService(
        runner=runner,
        clock=lambda: NOW,
    ).execute(plan)

    assert (
        result.report.status
        is ReleaseDrillStatus.FAILED
    )
    assert (
        result.report.failure_step_id
        == "configure"
    )
    assert (
        result.report.rollback_triggered
        is False
    )
    assert result.report.failed_steps == 1
    assert result.report.skipped_steps == 0

    assert runner.calls == [
        "preflight",
        "verify-package",
        "install",
        "configure",
        "start",
        "health",
        "evidence",
    ]


@pytest.mark.asyncio
async def test_timed_out_upgrade_step_triggers_rollback(
    tmp_path: Path,
) -> None:
    runner = RecordingRunner(
        {
            "install-upgrade": (
                ReleaseCommandOutcome(
                    exit_code=None,
                    duration_seconds=30.0,
                    timed_out=True,
                )
            )
        }
    )

    result = await ReleaseRunbookService(
        runner=runner,
        clock=lambda: NOW,
    ).execute(
        make_upgrade_plan(tmp_path)
    )

    assert (
        result.report.status
        is ReleaseDrillStatus.ROLLED_BACK
    )

    failed = next(
        item
        for item in result.report.results
        if item.step_id
        == "install-upgrade"
    )

    assert (
        failed.status
        is ReleaseStepStatus.TIMED_OUT
    )
    assert failed.exit_code is None


def test_upgrade_requires_rollback_steps(
    tmp_path: Path,
) -> None:
    valid = make_upgrade_plan(tmp_path)

    with pytest.raises(
        ValidationError,
        match="requires rollback steps",
    ):
        ReleaseRunbookPlan(
            identity=valid.identity,
            mode=valid.mode,
            steps=valid.steps,
            rollback_steps=(),
            report_path=valid.report_path,
            rollback_on_failure=True,
        )

import stat
import sys

from af_core.production.release_models import (
    ReleaseRunbookPolicyError,
)


def make_restore_plan(
    tmp_path: Path,
    *,
    mode: ReleaseMode,
) -> ReleaseRunbookPlan:
    restore_phase = (
        ReleasePhase.ROLLBACK
        if mode is ReleaseMode.ROLLBACK
        else ReleasePhase.RECOVERY
    )

    prefix = mode.value

    return ReleaseRunbookPlan(
        identity=make_identity(),
        mode=mode,
        steps=(
            make_command(
                tmp_path,
                f"{prefix}-preflight",
                ReleasePhase.PREFLIGHT,
            ),
            make_command(
                tmp_path,
                f"{prefix}-stop",
                ReleasePhase.STOP,
            ),
            make_command(
                tmp_path,
                f"{prefix}-apply",
                restore_phase,
            ),
            make_command(
                tmp_path,
                f"{prefix}-start",
                ReleasePhase.START,
            ),
            make_command(
                tmp_path,
                f"{prefix}-health",
                ReleasePhase.HEALTH,
            ),
            make_command(
                tmp_path,
                f"{prefix}-evidence",
                ReleasePhase.EVIDENCE,
            ),
        ),
        report_path=(
            tmp_path
            / "reports"
            / f"{prefix}-report.json"
        ),
        rollback_on_failure=False,
    )


@pytest.mark.asyncio
async def test_standalone_rollback_drill_passes(
    tmp_path: Path,
) -> None:
    runner = RecordingRunner()

    result = await ReleaseRunbookService(
        runner=runner,
        clock=lambda: NOW,
    ).execute(
        make_restore_plan(
            tmp_path,
            mode=ReleaseMode.ROLLBACK,
        )
    )

    assert (
        result.report.status
        is ReleaseDrillStatus.PASSED
    )
    assert result.report.passed_steps == 6
    assert runner.calls[2] == "rollback-apply"


@pytest.mark.asyncio
async def test_standalone_recovery_drill_passes(
    tmp_path: Path,
) -> None:
    runner = RecordingRunner()

    result = await ReleaseRunbookService(
        runner=runner,
        clock=lambda: NOW,
    ).execute(
        make_restore_plan(
            tmp_path,
            mode=ReleaseMode.RECOVERY,
        )
    )

    assert (
        result.report.status
        is ReleaseDrillStatus.PASSED
    )
    assert result.report.passed_steps == 6
    assert runner.calls[2] == "recovery-apply"


@pytest.mark.asyncio
async def test_subprocess_runner_does_not_use_shell(
    tmp_path: Path,
) -> None:
    output = tmp_path / "argv-output.txt"
    injected = tmp_path / "shell-injected.txt"

    payload = (
        "safe-value; touch "
        + str(injected)
    )

    command = ReleaseCommand(
        step_id="argv-check",
        phase=ReleasePhase.PREFLIGHT,
        argv=(
            sys.executable,
            "-c",
            (
                "from pathlib import Path;"
                "import sys;"
                "Path(sys.argv[1]).write_text("
                "sys.argv[2], encoding='utf-8')"
            ),
            str(output),
            payload,
        ),
        working_directory=tmp_path,
        timeout_seconds=5.0,
    )

    outcome = await ReleaseRunbookService(
        clock=lambda: NOW,
    )._run_subprocess(command)

    assert outcome.exit_code == 0
    assert outcome.timed_out is False
    assert output.read_text(
        encoding="utf-8"
    ) == payload
    assert not injected.exists()


@pytest.mark.asyncio
async def test_report_replacement_is_atomic_and_restrictive(
    tmp_path: Path,
) -> None:
    plan = make_install_plan(
        tmp_path,
        report_name="atomic-report.json",
    )

    service = ReleaseRunbookService(
        runner=RecordingRunner(),
        clock=lambda: NOW,
    )

    first = await service.execute(plan)

    first_payload = (
        first.report_path.read_bytes()
    )

    failing_runner = RecordingRunner(
        {
            "preflight": (
                ReleaseCommandOutcome(
                    exit_code=9,
                    duration_seconds=0.01,
                )
            )
        }
    )

    second = await ReleaseRunbookService(
        runner=failing_runner,
        clock=lambda: NOW,
    ).execute(plan)

    second_payload = (
        second.report_path.read_bytes()
    )

    assert (
        first.report.status
        is ReleaseDrillStatus.PASSED
    )
    assert (
        second.report.status
        is ReleaseDrillStatus.FAILED
    )
    assert first_payload != second_payload

    assert stat.S_IMODE(
        second.report_path.stat().st_mode
    ) == 0o640

    assert tuple(
        second.report_path.parent.iterdir()
    ) == (
        second.report_path,
    )


@pytest.mark.asyncio
async def test_report_symlink_destination_is_rejected(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()

    protected = (
        tmp_path / "protected-report.json"
    )
    protected.write_text(
        '{"protected":true}\n',
        encoding="utf-8",
    )

    linked_report = (
        reports / "linked-report.json"
    )
    linked_report.symlink_to(
        protected
    )

    plan = make_install_plan(
        tmp_path,
        report_name="linked-report.json",
    )

    with pytest.raises(
        ReleaseRunbookPolicyError,
        match="symlink",
    ):
        await ReleaseRunbookService(
            runner=RecordingRunner(),
            clock=lambda: NOW,
        ).execute(plan)

    assert protected.read_text(
        encoding="utf-8"
    ) == '{"protected":true}\n'
