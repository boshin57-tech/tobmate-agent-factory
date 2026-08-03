import pytest

from af_core.production import (
    SecretReference,
    SecretResolutionError,
    redact_structure,
    redact_text,
    sanitized_environment,
)


def test_secret_reference_resolves_external_value():
    reference = SecretReference(
        environment_key="OPENAI_API_KEY"
    )

    assert (
        reference.resolve(
            {"OPENAI_API_KEY": "external-secret"}
        )
        == "external-secret"
    )


def test_required_secret_reference_rejects_missing_value():
    reference = SecretReference(
        environment_key="GITHUB_TOKEN"
    )

    with pytest.raises(
        SecretResolutionError,
        match="GITHUB_TOKEN",
    ):
        reference.resolve({})


def test_optional_secret_reference_allows_missing_value():
    reference = SecretReference(
        environment_key="OPTIONAL_TOKEN",
        required=False,
    )

    assert reference.resolve({}) is None


def test_recursive_redaction_hides_sensitive_mapping_keys():
    payload = {
        "service": "af-core",
        "nested": {
            "api_key": "abc-123",
            "password": "do-not-log",
        },
        "safe": ["one", "two"],
    }

    redacted = redact_structure(payload)

    assert redacted["service"] == "af-core"
    assert (
        redacted["nested"]["api_key"]
        == "[REDACTED]"
    )
    assert (
        redacted["nested"]["password"]
        == "[REDACTED]"
    )


def test_text_redaction_hides_known_bearer_and_url_secrets():
    text = (
        "token=my-token "
        "Authorization:Bearer abc.def "
        "postgresql://user:db-password@db/afcore "
        "value=known-value"
    )

    redacted = redact_text(
        text,
        known_secrets=("known-value",),
    )

    assert "my-token" not in redacted
    assert "abc.def" not in redacted
    assert "db-password" not in redacted
    assert "known-value" not in redacted


def test_sanitized_environment_uses_explicit_allowlist():
    source = {
        "PATH": "/usr/bin",
        "HOME": "/home/afcore",
        "LANG": "C.UTF-8",
        "OPENAI_API_KEY": "secret",
        "UNRELATED_VALUE": "discard",
    }

    sanitized = sanitized_environment(
        source,
        allowed_keys=(
            "PATH",
            "HOME",
            "LANG",
            "OPENAI_API_KEY",
        ),
        secret_keys=("OPENAI_API_KEY",),
    )

    assert sanitized == {
        "PATH": "/usr/bin",
        "HOME": "/home/afcore",
        "LANG": "C.UTF-8",
    }
