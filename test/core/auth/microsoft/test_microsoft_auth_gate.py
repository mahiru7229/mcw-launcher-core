from __future__ import annotations

import pytest

from src.core.auth.microsoft import microsoft_auth_gate
from src.core.auth.microsoft.microsoft_account_authenticator import MicrosoftAccountAuthenticator
from src.core.auth.microsoft.microsoft_auth_gate import MicrosoftAuthenticationGate, MicrosoftAuthenticationLockedError
from src.core.auth.microsoft.microsoft_oauth import MicrosoftOAuth


def test_microsoft_auth_is_locked_without_opening_oauth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(microsoft_auth_gate, "MICROSOFT_AUTH_ENABLED", False)
    monkeypatch.setattr(microsoft_auth_gate, "MICROSOFT_AUTH_STATUS", "pending_mojang_approval")
    called = {"oauth": False}
    monkeypatch.setattr(MicrosoftOAuth, "authenticate", lambda: called.__setitem__("oauth", True))

    with pytest.raises(MicrosoftAuthenticationLockedError, match="approval"):
        MicrosoftAccountAuthenticator.authenticate()

    assert called["oauth"] is False
    availability = MicrosoftAuthenticationGate.availability()
    assert availability.enabled is False
    assert availability.status == "pending_mojang_approval"


def test_microsoft_auth_is_available_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(microsoft_auth_gate, "MICROSOFT_AUTH_ENABLED", True)
    monkeypatch.setattr(microsoft_auth_gate, "MICROSOFT_AUTH_STATUS", "available")

    availability = MicrosoftAuthenticationGate.availability()

    assert availability.enabled is True
    assert availability.status == "available"
    assert "available" in availability.message.lower()
