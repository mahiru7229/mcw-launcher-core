from src.core.security.sensitive_data_redactor import SensitiveDataRedactor


def test_redacts_tokens_from_text() -> None:
    text = "Authorization: Bearer abc.def.ghi refresh_token=super-secret&code=oauth-code"

    result = SensitiveDataRedactor.redact_text(text)

    assert "super-secret" not in result
    assert "oauth-code" not in result
    assert "abc.def.ghi" not in result
    assert result.count("<redacted>") >= 3


def test_redacts_nested_secret_fields() -> None:
    payload = {"profile": {"name": "Player"}, "access_token": "secret", "nested": [{"refresh_token": "refresh"}]}

    result = SensitiveDataRedactor.redact_value(payload)

    assert result["profile"]["name"] == "Player"
    assert result["access_token"] == "<redacted>"
    assert result["nested"][0]["refresh_token"] == "<redacted>"


def test_redacts_standalone_oauth_code_assignment() -> None:
    result = SensitiveDataRedactor.redact_text("callback failed: code=oauth-secret")

    assert "oauth-secret" not in result
    assert "code=<redacted>" in result
