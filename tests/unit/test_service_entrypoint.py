from __future__ import annotations

import json

import pytest

from af_core.production import service_entrypoint
from af_core.production.service_entrypoint import (
    build_parser,
    load_settings,
    main,
    public_configuration,
)


def clear_af_core_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os

    for key in tuple(os.environ):
        if key.startswith("AF_CORE_"):
            monkeypatch.delenv(
                key,
                raising=False,
            )


def test_build_parser_contract() -> None:
    parser = build_parser()

    arguments = parser.parse_args(
        [
            "--check",
            "--print-config",
        ]
    )

    assert parser.prog == "af-core-service"
    assert arguments.check is True
    assert arguments.print_config is True


def test_load_settings_separates_namespaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_af_core_environment(monkeypatch)

    monkeypatch.setenv(
        "AF_CORE_SERVICE_NAME",
        "checkpoint-19-service",
    )
    monkeypatch.setenv(
        "AF_CORE_INSTANCE_ID",
        "checkpoint-19-instance",
    )
    monkeypatch.setenv(
        "AF_CORE_HOST_PROBE_PORT",
        "48119",
    )

    production, host = load_settings()

    assert (
        production.service_name
        == "checkpoint-19-service"
    )
    assert (
        production.instance_id
        == "checkpoint-19-instance"
    )
    assert host.probe_port == 48119


def test_public_configuration_excludes_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_af_core_environment(monkeypatch)

    secret = (
        "postgresql://user:"
        "checkpoint19-secret@example/db"
    )

    monkeypatch.setenv(
        "AF_CORE_DATABASE_URL",
        secret,
    )

    production, host = load_settings()

    configuration = public_configuration(
        production,
        host,
    )

    serialized = json.dumps(
        configuration,
        sort_keys=True,
    )

    assert set(configuration) == {
        "production",
        "service_host",
    }
    assert secret not in serialized
    assert "checkpoint19-secret" not in serialized


def test_main_check_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clear_af_core_environment(monkeypatch)

    result = main(["--check"])

    captured = capsys.readouterr()

    assert result == 0
    assert (
        "AF-Core production configuration: PASS"
        in captured.out
    )
    assert captured.err == ""


def test_main_print_config_is_safe_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clear_af_core_environment(monkeypatch)

    secret = (
        "postgresql://user:"
        "entrypoint-secret@example/db"
    )

    monkeypatch.setenv(
        "AF_CORE_DATABASE_URL",
        secret,
    )

    result = main(["--print-config"])
    captured = capsys.readouterr()

    configuration = json.loads(captured.out)

    assert result == 0
    assert set(configuration) == {
        "production",
        "service_host",
    }
    assert secret not in captured.out
    assert "entrypoint-secret" not in captured.out
    assert captured.err == ""


def test_main_configuration_error_returns_two(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clear_af_core_environment(monkeypatch)

    monkeypatch.setenv(
        "AF_CORE_HOST_UNKNOWN_SETTING",
        "invalid",
    )

    result = main(["--check"])
    captured = capsys.readouterr()

    assert result == 2
    assert captured.out == ""
    assert (
        "AF-Core configuration error:"
        in captured.err
    )


def test_main_service_failure_returns_one(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clear_af_core_environment(monkeypatch)

    def fail_run(coroutine: object) -> None:
        close = getattr(
            coroutine,
            "close",
            None,
        )

        if close is not None:
            close()

        raise RuntimeError(
            "deliberate service failure"
        )

    monkeypatch.setattr(
        service_entrypoint.asyncio,
        "run",
        fail_run,
    )

    result = main([])
    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert (
        "AF-Core service failure: "
        "deliberate service failure"
        in captured.err
    )
