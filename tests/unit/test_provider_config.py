from pathlib import Path

import pytest

from af_core.runtime.provider_config import (
    ProviderEndpointConfig,
    ProviderRuntimeConfig,
)


def test_endpoint_resolves_api_key_from_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "TEST_PROVIDER_API_KEY",
        "secret-value",
    )

    config = ProviderEndpointConfig(
        provider_id="provider-a",
        base_url="https://example.invalid",
        api_key_environment="TEST_PROVIDER_API_KEY",
    )

    assert config.api_key() == "secret-value"
    assert config.resolved_headers() == {
        "Authorization": "Bearer secret-value",
    }


def test_explicit_authorization_header_is_preserved(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "TEST_PROVIDER_API_KEY",
        "environment-key",
    )

    config = ProviderEndpointConfig(
        provider_id="provider-a",
        base_url="https://example.invalid",
        api_key_environment="TEST_PROVIDER_API_KEY",
        headers={
            "Authorization": "Custom credential",
            "X-Test": "enabled",
        },
    )

    assert config.resolved_headers() == {
        "Authorization": "Custom credential",
        "X-Test": "enabled",
    }


def test_runtime_config_round_trip(
    tmp_path: Path,
) -> None:
    runtime = ProviderRuntimeConfig(
        providers={
            "ollama-local": ProviderEndpointConfig(
                provider_id="ollama-local",
                base_url="http://127.0.0.1:11434",
                options={
                    "generation_options": {
                        "temperature": 0,
                    }
                },
            )
        }
    )

    target = runtime.write_template(
        tmp_path / "providers.json"
    )
    restored = ProviderRuntimeConfig.from_json_file(
        target
    )

    config = restored.get("ollama-local")

    assert config.provider_id == "ollama-local"
    assert config.base_url == "http://127.0.0.1:11434"
    assert config.options["generation_options"] == {
        "temperature": 0,
    }


def test_runtime_config_rejects_missing_or_disabled_provider() -> None:
    runtime = ProviderRuntimeConfig(
        providers={
            "disabled": ProviderEndpointConfig(
                provider_id="disabled",
                base_url="http://127.0.0.1:11434",
                enabled=False,
            )
        }
    )

    with pytest.raises(
        ValueError,
        match="not found",
    ):
        runtime.get("missing")

    with pytest.raises(
        ValueError,
        match="disabled",
    ):
        runtime.get("disabled")
