from __future__ import annotations

from threading import Event

import pytest

from src.core.auth.microsoft import oauth_callback_server
from src.core.auth.microsoft.oauth_callback_server import MicrosoftAuthorizationCancelledError, OAuthCallbackServer


class FakeServer:
    def __init__(self, *_args, **_kwargs) -> None:
        self.timeout = None
        self.closed = False

    def handle_request(self) -> None:
        raise AssertionError("A cancelled callback must not wait for another HTTP request.")

    def server_close(self) -> None:
        self.closed = True


def test_wait_for_callback_can_be_cancelled_before_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[FakeServer] = []

    def create_server(*args, **kwargs) -> FakeServer:
        server = FakeServer(*args, **kwargs)
        created.append(server)
        return server

    monkeypatch.setattr(oauth_callback_server, "ReusableOAuthHTTPServer", create_server)
    cancel_event = Event()
    cancel_event.set()

    with pytest.raises(MicrosoftAuthorizationCancelledError, match="cancelled"):
        OAuthCallbackServer.wait_for_callback(cancel_event=cancel_event)

    assert created and created[0].closed is True
