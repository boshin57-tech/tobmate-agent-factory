from pathlib import Path

import pytest

from af_core.production import (
    DeploymentEnvironment,
    ProductionConfigurationError,
    ProductionSettings,
)


def valid_production_environment() -> dict[str, str]:
    return {
        "AF_CORE_ENVIRONMENT": "production",
        "AF_CORE_SERVICE_NAME": "af-core",
        "AF_CORE_INSTANCE_ID": "af-core-node-01",
        "AF_CORE_DATA_DIR": "/var/lib/af-core",
        "AF_CORE_ARTIFACT_DIR": (
            "/var/lib/af-core/artifacts"
        ),
        "AF_CORE_DATABASE_URL": (
            "postgresql://afcore:secret@db/afcore"
        ),
        "AF_CORE_INHERIT_PARENT_ENVIRONMENT": (
            "false"
        ),
    }


def test_default_settings_are_development_safe():
    settings = ProductionSettings()

    assert (
        settings.environment
        is DeploymentEnvironment.DEVELOPMENT
    )
    assert settings.inherit_parent_environment is False
    assert settings.max_concurrency == 4


def test_environment_loader_parses_typed_values():
    settings = ProductionSettings.from_environment(
        {
            "AF_CORE_ENVIRONMENT": "staging",
            "AF_CORE_INSTANCE_ID": "stage-node-01",
            "AF_CORE_COMMAND_TIMEOUT_SECONDS": "90",
            "AF_CORE_MCP_TIMEOUT_SECONDS": "45.5",
            "AF_CORE_MAX_CONCURRENCY": "12",
            "AF_CORE_ALLOWED_ENVIRONMENT_KEYS": (
                "PATH,HOME,LANG"
            ),
            "AF_CORE_SECRET_ENVIRONMENT_KEYS": (
                "OPENAI_API_KEY,GITHUB_TOKEN"
            ),
        }
    )

    assert (
        settings.environment
        is DeploymentEnvironment.STAGING
    )
    assert settings.command_timeout_seconds == 90
    assert settings.mcp_timeout_seconds == 45.5
    assert settings.max_concurrency == 12
    assert settings.allowed_environment_keys == (
        "PATH",
        "HOME",
        "LANG",
    )
    assert settings.secret_environment_keys == (
        "OPENAI_API_KEY",
        "GITHUB_TOKEN",
    )


def test_unknown_prefixed_variable_is_rejected():
    with pytest.raises(
        ProductionConfigurationError,
        match="unknown AF-Core",
    ):
        ProductionSettings.from_environment(
            {
                "AF_CORE_UNDECLARED_OPTION": "unsafe",
            }
        )


def test_invalid_boolean_is_rejected():
    with pytest.raises(
        ProductionConfigurationError,
        match="must be a boolean",
    ):
        ProductionSettings.from_environment(
            {
                "AF_CORE_INHERIT_PARENT_ENVIRONMENT": (
                    "sometimes"
                ),
            }
        )


def test_production_rejects_relative_data_path():
    environment = valid_production_environment()
    environment["AF_CORE_DATA_DIR"] = "relative/data"

    with pytest.raises(
        ProductionConfigurationError,
        match="data_dir must be absolute",
    ):
        ProductionSettings.from_environment(
            environment
        )


def test_production_rejects_sqlite_database():
    environment = valid_production_environment()
    environment["AF_CORE_DATABASE_URL"] = (
        "sqlite:////var/lib/af-core/af-core.db"
    )

    with pytest.raises(
        ProductionConfigurationError,
        match="external durable database",
    ):
        ProductionSettings.from_environment(
            environment
        )


def test_production_rejects_parent_environment_inheritance():
    environment = valid_production_environment()
    environment[
        "AF_CORE_INHERIT_PARENT_ENVIRONMENT"
    ] = "true"

    with pytest.raises(
        ProductionConfigurationError,
        match="must not inherit",
    ):
        ProductionSettings.from_environment(
            environment
        )


def test_valid_production_configuration():
    settings = ProductionSettings.from_environment(
        valid_production_environment()
    )

    assert (
        settings.environment
        is DeploymentEnvironment.PRODUCTION
    )
    assert settings.data_dir == Path(
        "/var/lib/af-core"
    )
    assert settings.artifact_dir == Path(
        "/var/lib/af-core/artifacts"
    )


def test_allowed_and_secret_keys_must_not_overlap():
    with pytest.raises(
        ProductionConfigurationError,
        match="must not overlap",
    ):
        ProductionSettings.from_environment(
            {
                "AF_CORE_ALLOWED_ENVIRONMENT_KEYS": (
                    "PATH,GITHUB_TOKEN"
                ),
                "AF_CORE_SECRET_ENVIRONMENT_KEYS": (
                    "GITHUB_TOKEN"
                ),
            }
        )


def test_public_snapshot_redacts_database_password():
    settings = ProductionSettings.from_environment(
        valid_production_environment()
    )

    snapshot = settings.public_snapshot()
    serialized = str(snapshot)

    assert "postgresql://afcore:" in serialized
    assert "secret@db" not in serialized
    assert "[REDACTED]" in serialized
