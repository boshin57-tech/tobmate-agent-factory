from __future__ import annotations

import stat
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from af_core.production.process_identity import (
    ProcessIdentityManager,
)
from af_core.production.process_models import (
    ProcessOwnershipError,
    ProcessSpecification,
    RestartMode,
    RestartPolicy,
)


NOW = datetime(
    2026,
    8,
    4,
    8,
    0,
    tzinfo=timezone.utc,
)


def make_specification(
    tmp_path: Path,
    *,
    restart_policy: RestartPolicy | None = None,
) -> ProcessSpecification:
    working_directory = (
        tmp_path / "application"
    )
    working_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    return ProcessSpecification(
        name="af-core-service",
        command=(
            "python",
            "-m",
            "af_core",
        ),
        working_directory=working_directory,
        pid_file=(
            tmp_path
            / "runtime"
            / "af-core.pid"
        ),
        environment_keys=(
            "AF_CORE_PORT",
            "AF_CORE_ENVIRONMENT",
        ),
        readiness_timeout_seconds=5.0,
        shutdown_timeout_seconds=10.0,
        restart_policy=(
            restart_policy
            or RestartPolicy()
        ),
    )


def test_process_specification_normalizes_policy(
    tmp_path: Path,
) -> None:
    specification = make_specification(
        tmp_path
    )

    assert (
        specification.name
        == "af-core-service"
    )
    assert specification.command == (
        "python",
        "-m",
        "af_core",
    )
    assert specification.environment_keys == (
        "AF_CORE_ENVIRONMENT",
        "AF_CORE_PORT",
    )
    assert (
        specification.restart_policy.mode
        is RestartMode.ON_FAILURE
    )


def test_process_specification_rejects_relative_paths() -> None:
    with pytest.raises(
        ValidationError,
        match="absolute",
    ):
        ProcessSpecification(
            name="af-core-service",
            command=("python",),
            working_directory=Path(
                "relative/application"
            ),
            pid_file=Path(
                "relative/service.pid"
            ),
        )


def test_restart_mode_never_requires_zero_limit() -> None:
    with pytest.raises(
        ValidationError,
        match="maximum_restarts=0",
    ):
        RestartPolicy(
            mode=RestartMode.NEVER,
            maximum_restarts=1,
        )

    policy = RestartPolicy(
        mode=RestartMode.NEVER,
        maximum_restarts=0,
    )

    assert policy.maximum_restarts == 0


def test_pid_acquire_verify_and_release(
    tmp_path: Path,
) -> None:
    specification = make_specification(
        tmp_path
    )

    manager = ProcessIdentityManager(
        clock=lambda: NOW,
        pid_provider=lambda: 4242,
        token_factory=lambda: (
            "00112233445566778899aabbccddeeff"
        ),
        process_exists=lambda pid: False,
    )

    record = manager.acquire(
        specification
    )

    assert record.pid == 4242
    assert manager.is_owned(
        specification,
        record,
    )
    assert manager.verify(
        specification,
        record,
    ) == record

    mode = stat.S_IMODE(
        specification.pid_file.stat().st_mode
    )

    assert mode == 0o640

    manager.release(
        specification,
        record,
    )

    assert not specification.pid_file.exists()


def test_pid_duplicate_running_process_is_rejected(
    tmp_path: Path,
) -> None:
    specification = make_specification(
        tmp_path
    )

    first = ProcessIdentityManager(
        clock=lambda: NOW,
        pid_provider=lambda: 1001,
        token_factory=lambda: (
            "11112222333344445555666677778888"
        ),
        process_exists=lambda pid: True,
    )

    first.acquire(specification)

    second = ProcessIdentityManager(
        clock=lambda: NOW,
        pid_provider=lambda: 2002,
        token_factory=lambda: (
            "88887777666655554444333322221111"
        ),
        process_exists=lambda pid: True,
    )

    with pytest.raises(
        ProcessOwnershipError,
        match="already owned",
    ):
        second.acquire(
            specification
        )


def test_pid_stale_record_is_atomically_replaced(
    tmp_path: Path,
) -> None:
    specification = make_specification(
        tmp_path
    )

    first = ProcessIdentityManager(
        clock=lambda: NOW,
        pid_provider=lambda: 3003,
        token_factory=lambda: (
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        ),
        process_exists=lambda pid: False,
    )

    stale = first.acquire(
        specification
    )

    assert stale.pid == 3003

    second = ProcessIdentityManager(
        clock=lambda: NOW,
        pid_provider=lambda: 4004,
        token_factory=lambda: (
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        ),
        process_exists=lambda pid: False,
    )

    current = second.acquire(
        specification
    )

    assert current.pid == 4004
    assert current.owner_token == (
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    )
    assert second.load(
        specification.pid_file
    ) == current

    second.release(
        specification,
        current,
    )

from af_core.production.process_models import (
    ProcessIdentityRecord,
    ProcessSupervisorPolicyError,
)


def test_pid_release_rejects_foreign_owner(
    tmp_path: Path,
) -> None:
    specification = make_specification(
        tmp_path
    )

    manager = ProcessIdentityManager(
        clock=lambda: NOW,
        pid_provider=lambda: 5005,
        token_factory=lambda: (
            "1234567890abcdef1234567890abcdef"
        ),
        process_exists=lambda pid: False,
    )

    record = manager.acquire(
        specification
    )

    foreign = record.model_copy(
        update={
            "owner_token": (
                "fedcba0987654321fedcba0987654321"
            )
        }
    )

    with pytest.raises(
        ProcessOwnershipError,
        match="does not match",
    ):
        manager.release(
            specification,
            foreign,
        )

    assert specification.pid_file.exists()

    manager.release(
        specification,
        record,
    )


def test_pid_invalid_record_is_rejected(
    tmp_path: Path,
) -> None:
    specification = make_specification(
        tmp_path
    )

    specification.pid_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    specification.pid_file.write_text(
        '{"invalid":true}\n',
        encoding="utf-8",
    )

    manager = ProcessIdentityManager(
        process_exists=lambda pid: False
    )

    with pytest.raises(
        ProcessOwnershipError,
        match="PID file is invalid",
    ):
        manager.load(
            specification.pid_file
        )


def test_pid_symlink_component_is_rejected(
    tmp_path: Path,
) -> None:
    specification = make_specification(
        tmp_path
    )

    real_runtime = tmp_path / "real-runtime"
    real_runtime.mkdir()

    linked_runtime = tmp_path / "linked-runtime"
    linked_runtime.symlink_to(
        real_runtime,
        target_is_directory=True,
    )

    unsafe_specification = (
        specification.model_copy(
            update={
                "pid_file": (
                    linked_runtime
                    / "af-core.pid"
                )
            }
        )
    )

    manager = ProcessIdentityManager(
        clock=lambda: NOW,
        pid_provider=lambda: 6006,
        token_factory=lambda: (
            "aaaaaaaa11111111bbbbbbbb22222222"
        ),
        process_exists=lambda pid: False,
    )

    with pytest.raises(
        ProcessSupervisorPolicyError,
        match="symlink",
    ):
        manager.acquire(
            unsafe_specification
        )


def test_command_identity_preserves_argument_boundaries() -> None:
    first = (
        ProcessIdentityManager
        .command_sha256(
            ("ab", "c")
        )
    )
    second = (
        ProcessIdentityManager
        .command_sha256(
            ("a", "bc")
        )
    )
    repeated = (
        ProcessIdentityManager
        .command_sha256(
            ("ab", "c")
        )
    )

    assert first != second
    assert first == repeated
    assert len(first) == 64


def test_pid_naive_clock_is_rejected(
    tmp_path: Path,
) -> None:
    specification = make_specification(
        tmp_path
    )

    manager = ProcessIdentityManager(
        clock=lambda: datetime(
            2026,
            8,
            4,
            8,
            0,
        ),
        pid_provider=lambda: 7007,
        token_factory=lambda: (
            "00110011001100110011001100110011"
        ),
        process_exists=lambda pid: False,
    )

    with pytest.raises(
        ProcessSupervisorPolicyError,
        match="timezone-aware",
    ):
        manager.acquire(
            specification
        )


def test_pid_invalid_owner_token_is_rejected(
    tmp_path: Path,
) -> None:
    specification = make_specification(
        tmp_path
    )

    manager = ProcessIdentityManager(
        clock=lambda: NOW,
        pid_provider=lambda: 8008,
        token_factory=lambda: "invalid-token",
        process_exists=lambda pid: False,
    )

    with pytest.raises(
        ValidationError,
        match="owner token",
    ):
        manager.acquire(
            specification
        )

    assert not specification.pid_file.exists()


def test_identity_record_rejects_naive_timestamp() -> None:
    with pytest.raises(
        ValidationError,
        match="timezone-aware",
    ):
        ProcessIdentityRecord(
            process_name="af-core-service",
            pid=9009,
            owner_token=(
                "0123456789abcdef0123456789abcdef"
            ),
            command_sha256="0" * 64,
            acquired_at=datetime(
                2026,
                8,
                4,
                8,
                0,
            ),
        )

from types import SimpleNamespace

from af_core.production import (
    HealthStatus,
)
from af_core.production.process_models import (
    ProcessExitKind,
    ProcessReadinessError,
    ProcessSupervisorState,
)
from af_core.production.process_supervisor import (
    ProcessSupervisor,
)


class FakeRuntime:
    def __init__(
        self,
        *,
        shutdown_reason: str = "test-shutdown",
    ) -> None:
        self.started = False
        self.stopped = False
        self.shutdown_requested = False
        self.shutdown_reason = shutdown_reason
        self.stop_reason: str | None = None
        self.stop_timeout: float | None = None

    async def start(self):
        self.started = True
        return SimpleNamespace()

    async def stop(
        self,
        *,
        reason: str = "requested",
        timeout_seconds: float | None = None,
    ):
        self.stopped = True
        self.stop_reason = reason
        self.stop_timeout = timeout_seconds
        return SimpleNamespace()

    def request_shutdown(
        self,
        reason: str = "requested",
    ) -> None:
        self.shutdown_requested = True
        self.shutdown_reason = reason

    async def wait_for_shutdown(self) -> str:
        return self.shutdown_reason


class FakeHealthRegistry:
    def __init__(
        self,
        statuses: list[HealthStatus],
    ) -> None:
        self.statuses = list(statuses)
        self.scopes = []

    async def evaluate(self, scope):
        self.scopes.append(scope)

        if not self.statuses:
            raise AssertionError(
                "No health status configured"
            )

        status = self.statuses.pop(0)

        return SimpleNamespace(
            status=status
        )


class FakeIdentityManager:
    def __init__(self) -> None:
        self.owned = False
        self.released = False

    def acquire(
        self,
        specification,
    ) -> ProcessIdentityRecord:
        self.owned = True

        return ProcessIdentityRecord(
            process_name=specification.name,
            pid=12345,
            owner_token=(
                "abcdefabcdefabcdefabcdefabcdefab"
            ),
            command_sha256=(
                ProcessIdentityManager
                .command_sha256(
                    specification.command
                )
            ),
            acquired_at=NOW,
        )

    def verify(
        self,
        specification,
        record,
    ):
        if not self.owned:
            raise ProcessOwnershipError(
                "not owned"
            )

        return record

    def is_owned(
        self,
        specification,
        record,
    ) -> bool:
        return self.owned

    def release(
        self,
        specification,
        record,
    ) -> None:
        if not self.owned:
            raise ProcessOwnershipError(
                "not owned"
            )

        self.owned = False
        self.released = True


class FakeSignalController:
    def __init__(self) -> None:
        self.installed = False
        self.install_count = 0
        self.uninstall_count = 0

    def install(self) -> None:
        self.installed = True
        self.install_count += 1

    def uninstall(self) -> None:
        self.installed = False
        self.uninstall_count += 1


@pytest.mark.asyncio
async def test_supervisor_start_passes_health_gates(
    tmp_path: Path,
) -> None:
    runtime = FakeRuntime()
    health = FakeHealthRegistry(
        [
            HealthStatus.HEALTHY,
            HealthStatus.HEALTHY,
        ]
    )
    identity = FakeIdentityManager()
    signals = FakeSignalController()

    supervisor = ProcessSupervisor(
        make_specification(tmp_path),
        runtime,
        health,
        identity_manager=identity,
        signal_controller=signals,
        clock=lambda: NOW,
    )

    snapshot = await supervisor.start()

    assert runtime.started is True
    assert identity.owned is True
    assert signals.installed is True
    assert (
        snapshot.state
        is ProcessSupervisorState.RUNNING
    )
    assert snapshot.pid == 12345
    assert snapshot.pid_owned is True
    assert snapshot.readiness_passed is True


@pytest.mark.asyncio
async def test_supervisor_stop_releases_all_ownership(
    tmp_path: Path,
) -> None:
    runtime = FakeRuntime()
    identity = FakeIdentityManager()
    signals = FakeSignalController()

    supervisor = ProcessSupervisor(
        make_specification(tmp_path),
        runtime,
        FakeHealthRegistry(
            [
                HealthStatus.HEALTHY,
                HealthStatus.HEALTHY,
            ]
        ),
        identity_manager=identity,
        signal_controller=signals,
        clock=lambda: NOW,
    )

    await supervisor.start()

    snapshot = await supervisor.stop(
        reason="maintenance"
    )

    assert runtime.stopped is True
    assert runtime.stop_reason == "maintenance"
    assert runtime.stop_timeout == 10.0
    assert identity.released is True
    assert signals.installed is False
    assert (
        snapshot.state
        is ProcessSupervisorState.STOPPED
    )
    assert snapshot.pid is None
    assert snapshot.pid_owned is False
    assert (
        snapshot.last_exit_kind
        is ProcessExitKind.CLEAN
    )


@pytest.mark.asyncio
async def test_supervisor_retries_degraded_readiness(
    tmp_path: Path,
) -> None:
    sleeps: list[float] = []

    async def sleeper(
        seconds: float,
    ) -> None:
        sleeps.append(seconds)

    supervisor = ProcessSupervisor(
        make_specification(tmp_path),
        FakeRuntime(),
        FakeHealthRegistry(
            [
                HealthStatus.HEALTHY,
                HealthStatus.DEGRADED,
                HealthStatus.HEALTHY,
            ]
        ),
        identity_manager=(
            FakeIdentityManager()
        ),
        signal_controller=(
            FakeSignalController()
        ),
        clock=lambda: NOW,
        monotonic=iter(
            [
                0.0,
                0.5,
                0.6,
            ]
        ).__next__,
        sleeper=sleeper,
        readiness_poll_seconds=0.1,
    )

    snapshot = await supervisor.start()

    assert (
        snapshot.state
        is ProcessSupervisorState.RUNNING
    )
    assert sleeps == [0.1]


@pytest.mark.asyncio
async def test_supervisor_readiness_timeout_cleans_up(
    tmp_path: Path,
) -> None:
    runtime = FakeRuntime()
    identity = FakeIdentityManager()
    signals = FakeSignalController()

    supervisor = ProcessSupervisor(
        make_specification(tmp_path),
        runtime,
        FakeHealthRegistry(
            [
                HealthStatus.HEALTHY,
                HealthStatus.UNHEALTHY,
            ]
        ),
        identity_manager=identity,
        signal_controller=signals,
        clock=lambda: NOW,
        monotonic=iter(
            [
                0.0,
                0.0,
                10.0,
            ]
        ).__next__,
    )

    with pytest.raises(
        ProcessReadinessError,
        match="before timeout",
    ):
        await supervisor.start()

    snapshot = supervisor.snapshot()

    assert runtime.stopped is True
    assert identity.owned is False
    assert signals.installed is False
    assert (
        snapshot.state
        is ProcessSupervisorState.FAILED
    )
    assert snapshot.pid is None
    assert (
        snapshot.last_exit_kind
        is ProcessExitKind.READINESS_TIMEOUT
    )


def test_supervisor_shutdown_request_is_forwarded(
    tmp_path: Path,
) -> None:
    runtime = FakeRuntime()

    supervisor = ProcessSupervisor(
        make_specification(tmp_path),
        runtime,
        FakeHealthRegistry(
            [
                HealthStatus.HEALTHY,
                HealthStatus.HEALTHY,
            ]
        ),
        identity_manager=(
            FakeIdentityManager()
        ),
        signal_controller=(
            FakeSignalController()
        ),
        clock=lambda: NOW,
    )

    supervisor.request_shutdown(
        "operator-request"
    )

    assert runtime.shutdown_requested is True
    assert (
        runtime.shutdown_reason
        == "operator-request"
    )


@pytest.mark.asyncio
async def test_supervisor_run_until_shutdown(
    tmp_path: Path,
) -> None:
    runtime = FakeRuntime(
        shutdown_reason="sigterm"
    )

    supervisor = ProcessSupervisor(
        make_specification(tmp_path),
        runtime,
        FakeHealthRegistry(
            [
                HealthStatus.HEALTHY,
                HealthStatus.HEALTHY,
            ]
        ),
        identity_manager=(
            FakeIdentityManager()
        ),
        signal_controller=(
            FakeSignalController()
        ),
        clock=lambda: NOW,
    )

    snapshot = await (
        supervisor.run_until_shutdown()
    )

    assert runtime.started is True
    assert runtime.stopped is True
    assert runtime.stop_reason == "sigterm"
    assert (
        snapshot.state
        is ProcessSupervisorState.STOPPED
    )

from af_core.production.process_models import (
    ProcessRestartLimitError,
)


def make_supervisor(
    tmp_path: Path,
    *,
    restart_policy: RestartPolicy | None = None,
    monotonic=lambda: 0.0,
    sleeper=None,
) -> ProcessSupervisor:
    kwargs = {}

    if sleeper is not None:
        kwargs["sleeper"] = sleeper

    return ProcessSupervisor(
        make_specification(
            tmp_path,
            restart_policy=restart_policy,
        ),
        FakeRuntime(),
        FakeHealthRegistry(
            [
                HealthStatus.HEALTHY,
                HealthStatus.HEALTHY,
            ]
        ),
        identity_manager=(
            FakeIdentityManager()
        ),
        signal_controller=(
            FakeSignalController()
        ),
        clock=lambda: NOW,
        monotonic=monotonic,
        **kwargs,
    )


def test_supervisor_classifies_exit_codes(
    tmp_path: Path,
) -> None:
    supervisor = make_supervisor(
        tmp_path
    )

    assert (
        supervisor.classify_exit(0)
        is ProcessExitKind.CLEAN
    )
    assert (
        supervisor.classify_exit(1)
        is ProcessExitKind.FAILURE
    )
    assert (
        supervisor.classify_exit(-15)
        is ProcessExitKind.SIGNAL
    )


def test_restart_policy_decides_by_exit_kind(
    tmp_path: Path,
) -> None:
    supervisor = make_supervisor(
        tmp_path
    )

    assert not supervisor.restart_required(
        ProcessExitKind.CLEAN,
        exit_code=0,
    )
    assert supervisor.restart_required(
        ProcessExitKind.FAILURE,
        exit_code=1,
    )
    assert supervisor.restart_required(
        ProcessExitKind.SIGNAL,
        exit_code=-15,
    )

    supervisor.request_shutdown(
        "operator-stop"
    )

    assert not supervisor.restart_required(
        ProcessExitKind.FAILURE,
        exit_code=1,
    )


def test_restart_record_tracks_backoff_and_history(
    tmp_path: Path,
) -> None:
    supervisor = make_supervisor(
        tmp_path,
        restart_policy=RestartPolicy(
            mode=RestartMode.ON_FAILURE,
            maximum_restarts=3,
            window_seconds=60.0,
            backoff_seconds=2.5,
        ),
        monotonic=lambda: 10.0,
    )

    record = supervisor.record_restart(
        ProcessExitKind.FAILURE,
        exit_code=7,
    )

    assert record.sequence == 1
    assert record.delay_seconds == 2.5
    assert record.exit_code == 7
    assert supervisor.restart_history == (
        record,
    )

    snapshot = supervisor.snapshot()

    assert snapshot.restart_count == 1
    assert (
        snapshot.last_exit_kind
        is ProcessExitKind.FAILURE
    )
    assert snapshot.last_exit_code == 7


@pytest.mark.asyncio
async def test_wait_for_restart_applies_backoff(
    tmp_path: Path,
) -> None:
    sleeps: list[float] = []

    async def sleeper(
        seconds: float,
    ) -> None:
        sleeps.append(seconds)

    supervisor = make_supervisor(
        tmp_path,
        restart_policy=RestartPolicy(
            mode=RestartMode.ALWAYS,
            maximum_restarts=2,
            window_seconds=30.0,
            backoff_seconds=0.25,
        ),
        monotonic=lambda: 5.0,
        sleeper=sleeper,
    )

    record = await supervisor.wait_for_restart(
        ProcessExitKind.CLEAN,
        exit_code=0,
    )

    assert record.sequence == 1
    assert sleeps == [0.25]


def test_restart_limit_transitions_to_failed(
    tmp_path: Path,
) -> None:
    clock_values = iter(
        [
            0.0,
            1.0,
            2.0,
        ]
    )

    supervisor = make_supervisor(
        tmp_path,
        restart_policy=RestartPolicy(
            mode=RestartMode.ON_FAILURE,
            maximum_restarts=2,
            window_seconds=30.0,
            backoff_seconds=0.0,
        ),
        monotonic=clock_values.__next__,
    )

    supervisor.record_restart(
        ProcessExitKind.FAILURE,
        exit_code=1,
    )
    supervisor.record_restart(
        ProcessExitKind.FAILURE,
        exit_code=2,
    )

    with pytest.raises(
        ProcessRestartLimitError,
        match="limit exhausted",
    ):
        supervisor.record_restart(
            ProcessExitKind.FAILURE,
            exit_code=3,
        )

    assert (
        supervisor.state
        is ProcessSupervisorState.FAILED
    )
    assert len(
        supervisor.restart_history
    ) == 2

from af_core.production.process_models import (
    SystemdUnitSpecification,
)
from af_core.production.systemd_renderer import (
    SystemdUnitRenderer,
)


def make_systemd_unit(
    *,
    environment_file: Path | None = None,
) -> SystemdUnitSpecification:
    return SystemdUnitSpecification(
        description=(
            "TOBMATE AF-Core Production Service"
        ),
        user="afcore",
        group="afcore",
        environment_file=environment_file,
    )


def test_systemd_renderer_produces_hardened_unit(
    tmp_path: Path,
) -> None:
    process = make_specification(
        tmp_path,
        restart_policy=RestartPolicy(
            mode=RestartMode.ON_FAILURE,
            maximum_restarts=3,
            window_seconds=60.0,
            backoff_seconds=2.0,
        ),
    )

    rendered = SystemdUnitRenderer().render(
        process,
        make_systemd_unit(),
    )

    assert rendered.startswith(
        "[Unit]\n"
    )
    assert (
        "Description=TOBMATE AF-Core "
        "Production Service"
        in rendered
    )
    assert (
        "StartLimitIntervalSec=60s"
        in rendered
    )
    assert "StartLimitBurst=3" in rendered
    assert "[Service]" in rendered
    assert (
        'ExecStart="python" "-m" "af_core"'
        in rendered
    )
    assert "Restart=on-failure" in rendered
    assert "RestartSec=2s" in rendered
    assert "KillSignal=SIGTERM" in rendered
    assert "KillMode=mixed" in rendered
    assert "TimeoutStopSec=10s" in rendered
    assert "NoNewPrivileges=yes" in rendered
    assert "ProtectSystem=strict" in rendered
    assert "ProtectHome=yes" in rendered
    assert "PrivateDevices=yes" in rendered
    assert "CapabilityBoundingSet=" in rendered
    assert (
        "WantedBy=multi-user.target"
        in rendered
    )

    assert rendered.index(
        "StartLimitIntervalSec"
    ) < rendered.index("[Service]")


def test_systemd_renderer_escapes_command_arguments(
    tmp_path: Path,
) -> None:
    process = make_specification(
        tmp_path
    ).model_copy(
        update={
            "command": (
                "python",
                "-c",
                '"$HOME" "%i" "ready"',
            )
        }
    )

    rendered = SystemdUnitRenderer().render(
        process,
        make_systemd_unit(),
    )

    assert "$$HOME" in rendered
    assert "%%i" in rendered
    assert '\\"ready\\"' in rendered


def test_systemd_renderer_rejects_environment_mismatch(
    tmp_path: Path,
) -> None:
    process_environment = (
        tmp_path / "config" / "process.env"
    )
    unit_environment = (
        tmp_path / "config" / "unit.env"
    )

    process = make_specification(
        tmp_path
    ).model_copy(
        update={
            "environment_file": (
                process_environment
            )
        }
    )

    with pytest.raises(
        ProcessSupervisorPolicyError,
        match="must match",
    ):
        SystemdUnitRenderer().render(
            process,
            make_systemd_unit(
                environment_file=(
                    unit_environment
                )
            ),
        )


def test_systemd_write_is_atomic_and_restrictive(
    tmp_path: Path,
) -> None:
    process = make_specification(
        tmp_path
    )

    destination = (
        tmp_path
        / "systemd"
        / "af-core.service"
    )

    renderer = SystemdUnitRenderer()

    published = renderer.write(
        process,
        make_systemd_unit(),
        destination,
    )

    assert published == destination
    assert destination.is_file()
    assert stat.S_IMODE(
        destination.stat().st_mode
    ) == 0o644

    expected = renderer.render(
        process,
        make_systemd_unit(),
    )

    assert destination.read_text(
        encoding="utf-8"
    ) == expected

    assert tuple(
        destination.parent.iterdir()
    ) == (
        destination,
    )


def test_systemd_write_rejects_symlink_component(
    tmp_path: Path,
) -> None:
    real_directory = (
        tmp_path / "real-systemd"
    )
    real_directory.mkdir()

    linked_directory = (
        tmp_path / "linked-systemd"
    )
    linked_directory.symlink_to(
        real_directory,
        target_is_directory=True,
    )

    destination = (
        linked_directory
        / "af-core.service"
    )

    with pytest.raises(
        ProcessSupervisorPolicyError,
        match="symlink",
    ):
        SystemdUnitRenderer().write(
            make_specification(tmp_path),
            make_systemd_unit(),
            destination,
        )


def test_systemd_write_requires_service_suffix(
    tmp_path: Path,
) -> None:
    destination = (
        tmp_path
        / "systemd"
        / "af-core.conf"
    )

    with pytest.raises(
        ProcessSupervisorPolicyError,
        match=r"\.service suffix",
    ):
        SystemdUnitRenderer().write(
            make_specification(tmp_path),
            make_systemd_unit(),
            destination,
        )
