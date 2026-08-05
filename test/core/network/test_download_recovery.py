from __future__ import annotations

from pathlib import Path

from src.core.fs.paths import Paths
from src.core.network.download_journal import DownloadJournal
from src.core.network.download_models import DownloadRequest, DownloadState
from src.core.network.download_recovery import DownloadRecoveryManager
from src.models.network.download_recovery import DownloadRecoveryState


def _request(root: Path, request_id: str, expected_size: int = 10) -> DownloadRequest:
    return DownloadRequest(
        urls=("https://example.com/file.jar",),
        destination=root / f"{request_id}.jar",
        expected_size=expected_size,
        hashes={"sha1": "a" * 40},
        display_name=f"{request_id}.jar",
        request_id=request_id,
    )


def test_reconcile_keeps_resumable_and_ready_partial_files(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path)
    journal = DownloadJournal(tmp_path / "journal.json")
    resumable = _request(tmp_path, "resumable")
    ready = _request(tmp_path, "ready")
    resumable.temporary_path.write_bytes(b"1234")
    ready.temporary_path.write_bytes(b"1234567890")
    journal.update(resumable, DownloadState.FAILED, downloaded_bytes=4)
    journal.update(ready, DownloadState.PAUSED, downloaded_bytes=10)

    report = DownloadRecoveryManager(journal).reconcile()

    assert report.resumable_count == 2
    assert report.count(DownloadRecoveryState.RESUMABLE) == 1
    assert report.count(DownloadRecoveryState.READY_TO_VERIFY) == 1
    assert report.removed_journal_entries == 0
    assert resumable.temporary_path.read_bytes() == b"1234"
    assert ready.temporary_path.read_bytes() == b"1234567890"
    assert len(journal.snapshot()) == 2


def test_reconcile_removes_completed_and_stale_entries(tmp_path: Path) -> None:
    journal = DownloadJournal(tmp_path / "journal.json")
    completed = _request(tmp_path, "completed")
    stale = _request(tmp_path, "stale")
    completed.destination.write_bytes(b"1234567890")
    journal.update(completed, DownloadState.DOWNLOADING, downloaded_bytes=10)
    journal.update(stale, DownloadState.CANCELLED, downloaded_bytes=0)

    report = DownloadRecoveryManager(journal).reconcile()

    assert report.count(DownloadRecoveryState.COMPLETED) == 1
    assert report.count(DownloadRecoveryState.STALE) == 1
    assert report.removed_journal_entries == 2
    assert journal.snapshot() == ()


def test_reconcile_deletes_only_safe_oversized_partial(monkeypatch, tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"
    outside = tmp_path / "outside"
    cache_root.mkdir()
    outside.mkdir()
    monkeypatch.setattr(Paths, "CACHE_ROOT", cache_root)
    monkeypatch.setattr(Paths, "INSTANCES_ROOT", tmp_path / "instances")
    journal = DownloadJournal(tmp_path / "journal.json")
    safe = _request(cache_root, "safe", expected_size=3)
    unsafe = _request(outside, "unsafe", expected_size=3)
    safe.temporary_path.write_bytes(b"1234")
    unsafe.temporary_path.write_bytes(b"1234")
    journal.update(safe, DownloadState.FAILED, downloaded_bytes=4)
    journal.update(unsafe, DownloadState.FAILED, downloaded_bytes=4)

    report = DownloadRecoveryManager(journal).reconcile(delete_invalid_parts=True)

    assert report.removed_journal_entries == 2
    assert report.deleted_partial_files == 1
    assert report.deleted_partial_bytes == 4
    assert not safe.temporary_path.exists()
    assert unsafe.temporary_path.exists()


def test_unexpected_partial_path_is_never_deleted(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path)
    journal = DownloadJournal(tmp_path / "journal.json")
    request = _request(tmp_path, "entry")
    protected = tmp_path / "protected.part"
    protected.write_bytes(b"keep")
    journal.update(request, DownloadState.FAILED, downloaded_bytes=4)
    payload = journal._read()
    payload["entries"]["entry"]["temporary_path"] = str(protected)
    journal._write(payload)

    report = DownloadRecoveryManager(journal).reconcile(delete_invalid_parts=True)

    assert report.count(DownloadRecoveryState.INVALID) == 1
    assert report.deleted_partial_files == 0
    assert protected.read_bytes() == b"keep"


def test_remove_orphan_parts_keeps_fresh_and_journal_referenced_files(monkeypatch, tmp_path: Path) -> None:
    import os
    import time

    cache = tmp_path / "cache"
    instances = tmp_path / "instances"
    cache.mkdir()
    instances.mkdir()
    monkeypatch.setattr(Paths, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(Paths, "CACHE_ROOT", cache)
    monkeypatch.setattr(Paths, "INSTANCES_ROOT", instances)
    journal = DownloadJournal(tmp_path / "journal.json")
    manager = DownloadRecoveryManager(journal)

    old_orphan = cache / "old.jar.part"
    fresh_orphan = cache / "fresh.jar.part"
    unknown = cache / "notes.txt.part"
    referenced_request = _request(cache, "referenced")
    for path in (old_orphan, fresh_orphan, unknown, referenced_request.temporary_path):
        path.write_bytes(b"partial")
    old_time = time.time() - 1000
    os.utime(old_orphan, (old_time, old_time))
    os.utime(unknown, (old_time, old_time))
    os.utime(referenced_request.temporary_path, (old_time, old_time))
    journal.update(referenced_request, DownloadState.PAUSED, downloaded_bytes=7)

    removed = manager.remove_orphan_parts(max_age_seconds=100)

    assert removed == ("cache/old.jar.part",)
    assert not old_orphan.exists()
    assert fresh_orphan.exists()
    assert unknown.exists()
    assert referenced_request.temporary_path.exists()
