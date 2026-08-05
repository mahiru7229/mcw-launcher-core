from __future__ import annotations

from src.core.network.network_session import DEFAULT_MAX_CONCURRENT_DOWNLOADS, NetworkSession


def test_network_session_reuses_client_and_recreates_after_configuration_change() -> None:
    session = NetworkSession()
    first = session.get_client()

    assert session.max_concurrent_downloads == DEFAULT_MAX_CONCURRENT_DOWNLOADS
    assert session.get_client() is first
    assert session.configure(12) == 12
    assert first.is_closed is True

    second = session.get_client()
    assert second is not first
    assert session.max_concurrent_downloads == 12

    session.close()
    assert second.is_closed is True


def test_network_session_clamps_concurrency() -> None:
    session = NetworkSession()

    assert session.configure(0) == 1
    assert session.configure(100) == 16

    session.close()
