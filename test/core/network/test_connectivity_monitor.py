from __future__ import annotations

import socket

import pytest

from src.core.network.connectivity_monitor import ConnectivityMonitor


class _Connection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_probe_reports_online_and_closes_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _Connection()
    received: list[tuple[tuple[str, int], float]] = []

    def connect(target: tuple[str, int], timeout: float):
        received.append((target, timeout))
        return connection

    monkeypatch.setattr(socket, "create_connection", connect)
    monitor = ConnectivityMonitor(targets=(("203.0.113.1", 443),))

    snapshot = monitor.probe(timeout=0.25, force=True)

    assert snapshot.online is True
    assert snapshot.detail == ""
    assert received == [(('203.0.113.1', 443), 0.25)]
    assert connection.closed is True


def test_probe_reports_offline_after_all_targets_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    targets = (("203.0.113.1", 443), ("198.51.100.2", 443))
    received: list[tuple[str, int]] = []

    def fail(target: tuple[str, int], timeout: float):
        received.append(target)
        raise TimeoutError("offline")

    monkeypatch.setattr(socket, "create_connection", fail)
    monitor = ConnectivityMonitor(targets=targets)

    snapshot = monitor.probe(timeout=0.05, force=True)

    assert snapshot.online is False
    assert snapshot.detail == "TimeoutError"
    assert received == list(targets)


def test_probe_reuses_recent_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _Connection()
    monkeypatch.setattr(socket, "create_connection", lambda *_args, **_kwargs: connection)
    monitor = ConnectivityMonitor(targets=(("203.0.113.1", 443),))
    first = monitor.probe(force=True)

    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected probe")),
    )

    assert monitor.probe(max_age_seconds=60.0) is first
