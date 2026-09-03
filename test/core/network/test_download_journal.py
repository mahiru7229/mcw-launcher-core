from __future__ import annotations

import json
from pathlib import Path

from src.core.network.download_journal import DownloadJournal
from src.core.network.download_models import DownloadRequest, DownloadState


def _request(tmp_path: Path) -> DownloadRequest:
    return DownloadRequest(
        urls=("https://secret.example.com/files/mod.jar?token=do-not-store",),
        destination=tmp_path / "mod.jar",
        expected_size=10,
        hashes={"sha1": "a" * 40},
        source="test",
        display_name="mod.jar",
        operation_id="install-pack",
        request_id="request-1",
    )


def test_journal_is_atomic_sanitized_and_recoverable(tmp_path: Path) -> None:
    journal_path = tmp_path / "download-journal.json"
    journal = DownloadJournal(journal_path)
    request = _request(tmp_path)

    journal.start(request, downloaded_bytes=4)
    payload = json.loads(journal_path.read_text(encoding="utf-8"))
    entry = payload["entries"]["request-1"]

    assert entry["host"] == "secret.example.com"
    assert "url" not in entry
    assert "token" not in journal_path.read_text(encoding="utf-8")
    assert journal.recoverable_entries()[0]["state"] == DownloadState.DOWNLOADING.value
    assert journal_path.with_name("download-journal.json.tmp").exists() is False

    journal.update(request, DownloadState.CANCELLED, downloaded_bytes=4)
    assert journal.recoverable_entries()[0]["state"] == DownloadState.CANCELLED.value

    journal.complete(request, size=10)
    assert journal.recoverable_entries() == []
    assert json.loads(journal_path.read_text(encoding="utf-8"))["entries"] == {}

    journal.clear_completed()
    assert json.loads(journal_path.read_text(encoding="utf-8"))["entries"] == {}


def test_locked_journal_replace_is_best_effort(monkeypatch, tmp_path: Path) -> None:
    journal_path = tmp_path / "download-journal.json"
    journal = DownloadJournal(journal_path)
    request = _request(tmp_path)

    monkeypatch.setattr(journal, "_replace_with_retry", lambda *_args: False)

    journal.start(request, downloaded_bytes=4)

    assert journal_path.exists() is False
    assert tuple(tmp_path.glob("*.tmp")) == ()


def test_downloading_progress_is_batched_until_critical_state(tmp_path: Path, monkeypatch) -> None:
    journal_path = tmp_path / "download-journal.json"
    journal = DownloadJournal(journal_path)
    request = _request(tmp_path)
    journal.start(request, downloaded_bytes=1)

    writes = 0
    real_write = journal._write

    def counted_write(payload):
        nonlocal writes
        writes += 1
        return real_write(payload)

    monkeypatch.setattr(journal, "_write", counted_write)
    journal._last_progress_flush_at = __import__("time").monotonic()

    journal.update(request, DownloadState.DOWNLOADING, downloaded_bytes=5)
    journal.update(request, DownloadState.DOWNLOADING, downloaded_bytes=6)

    assert writes == 0
    assert journal.snapshot()[0]["downloaded_bytes"] == 6

    journal.update(request, DownloadState.CANCELLED, downloaded_bytes=6)

    assert writes == 1
    assert json.loads(journal_path.read_text(encoding="utf-8"))["entries"]["request-1"]["state"] == DownloadState.CANCELLED.value
