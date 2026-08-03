import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from af_core.production import (
    DeploymentEnvironment,
    ProductionSettings,
    SecretReference,
)
from af_core.runtime.command_runner import (
    CommandPolicyError,
    RestrictedCommandRunner,
)
from af_core.runtime.provider_config import (
    ProviderEndpointConfig,
    ProviderRuntimeConfig,
)
from af_core.tools.mcp_models import MCPServerConfig
from af_core.tools.mcp_stdio_client import (
    MCPClientError,
    MCPStdioClient,
)
from af_core.tools.models import ExternalToolTransport


def run(coroutine):
    return asyncio.run(coroutine)


def settings() -> ProductionSettings:
    return ProductionSettings(
        environment=DeploymentEnvironment.STAGING,
        instance_id="stage-node-01",
        allowed_environment_keys=(
            "PATH",
            "HOME",
            "LANG",
            "PYTHONPATH",
        ),
        secret_environment_keys=(
            "OPENAI_API_KEY",
        ),
        command_timeout_seconds=15,
    )


def test_command_runner_injects_and_redacts_secret(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    source = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_path),
        "LANG": "C.UTF-8",
        "OPENAI_API_KEY": "runtime-secret-value",
        "UNRELATED_SECRET": "must-not-leak",
    }

    runner = RestrictedCommandRunner(
        workspace,
        settings=settings(),
        environment_source=source,
    )

    script = (
        "import os;"
        "print(os.getenv('OPENAI_API_KEY'));"
        "print(os.getenv('UNRELATED_SECRET'))"
    )

    result = run(
        runner.run(
            [sys.executable, "-c", script],
            secret_environment={
                "OPENAI_API_KEY": SecretReference(
                    environment_key="OPENAI_API_KEY"
                )
            },
        )
    )

    assert result.returncode == 0
    assert "runtime-secret-value" not in result.stdout
    assert "must-not-leak" not in result.stdout
    assert "[REDACTED]" in result.stdout
    assert "None" in result.stdout


def test_command_runner_rejects_direct_secret_injection(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    runner = RestrictedCommandRunner(
        workspace,
        settings=settings(),
        environment_source={
            "PATH": os.environ.get("PATH", ""),
        },
    )

    with pytest.raises(
        CommandPolicyError,
        match="SecretReference",
    ):
        run(
            runner.run(
                [sys.executable, "-c", "print('x')"],
                environment={
                    "OPENAI_API_KEY": "unsafe",
                },
            )
        )


def test_command_runner_rejects_unapproved_environment(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    runner = RestrictedCommandRunner(
        workspace,
        settings=settings(),
    )

    with pytest.raises(
        CommandPolicyError,
        match="not allowed",
    ):
        run(
            runner.run(
                [sys.executable, "-c", "print('x')"],
                environment={
                    "UNAPPROVED_VALUE": "unsafe",
                },
            )
        )


def mcp_config(
    environment: dict[str, str] | None = None,
) -> MCPServerConfig:
    return MCPServerConfig(
        server_id="production-boundary",
        transport=ExternalToolTransport.MCP_STDIO,
        command="python",
        arguments=["server.py"],
        environment=environment or {},
    )


def test_mcp_environment_excludes_parent_process_values():
    client = MCPStdioClient(
        mcp_config(
            {
                "PYTHONPATH": "/srv/af-core",
            }
        ),
        settings=settings(),
        environment_source={
            "PATH": "/usr/bin",
            "HOME": "/home/afcore",
            "OPENAI_API_KEY": "mcp-secret",
            "UNRELATED_SECRET": "must-not-leak",
        },
        secret_environment={
            "OPENAI_API_KEY": SecretReference(
                environment_key="OPENAI_API_KEY"
            )
        },
    )

    environment, secrets = client._build_environment()

    assert environment["PATH"] == "/usr/bin"
    assert environment["PYTHONPATH"] == "/srv/af-core"
    assert environment["OPENAI_API_KEY"] == "mcp-secret"
    assert "UNRELATED_SECRET" not in environment
    assert secrets == ("mcp-secret",)


def test_mcp_rejects_direct_declared_secret():
    client = MCPStdioClient(
        mcp_config(
            {
                "OPENAI_API_KEY": "unsafe",
            }
        ),
        settings=settings(),
        environment_source={
            "PATH": "/usr/bin",
        },
    )

    with pytest.raises(
        MCPClientError,
        match="SecretReference",
    ):
        client._build_environment()


def test_mcp_default_boundary_does_not_copy_full_parent():
    client = MCPStdioClient(
        mcp_config(),
        environment_source={
            "PATH": "/usr/bin",
            "HOME": "/home/afcore",
            "DATABASE_PASSWORD": "must-not-leak",
        },
    )

    environment, secrets = client._build_environment()

    assert environment == {
        "PATH": "/usr/bin",
        "HOME": "/home/afcore",
    }
    assert secrets == ()


def test_provider_resolves_secret_from_explicit_source():
    config = ProviderEndpointConfig(
        provider_id="provider-a",
        base_url="https://example.invalid",
        api_key_environment="provider_api_key",
    )

    assert config.api_key_environment == "PROVIDER_API_KEY"
    assert (
        config.api_key(
            {
                "PROVIDER_API_KEY": "provider-secret",
            }
        )
        == "provider-secret"
    )


def test_provider_public_snapshot_redacts_credentials():
    config = ProviderEndpointConfig(
        provider_id="provider-a",
        base_url=(
            "https://user:url-password@example.invalid"
        ),
        headers={
            "Authorization": "Bearer header-secret",
            "X-Test": "enabled",
        },
        options={
            "api_token": "option-secret",
        },
    )

    snapshot = json.dumps(
        config.public_snapshot(),
        sort_keys=True,
    )

    assert "url-password" not in snapshot
    assert "header-secret" not in snapshot
    assert "option-secret" not in snapshot
    assert "[REDACTED]" in snapshot
    assert "enabled" in snapshot


def test_provider_template_never_persists_credentials(
    tmp_path: Path,
) -> None:
    runtime = ProviderRuntimeConfig(
        providers={
            "provider-a": ProviderEndpointConfig(
                provider_id="provider-a",
                base_url="https://example.invalid",
                headers={
                    "Authorization": (
                        "Bearer persistent-secret"
                    ),
                },
            )
        }
    )

    target = runtime.write_template(
        tmp_path / "providers.json"
    )

    content = target.read_text(encoding="utf-8")

    assert "persistent-secret" not in content
    assert "[REDACTED]" in content
