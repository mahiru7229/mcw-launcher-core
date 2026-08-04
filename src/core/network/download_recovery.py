from __future__ import annotations

from pathlib import Path
import time

from src.core.fs.paths import Paths
from src.core.network.download_journal import DownloadJournal, download_journal
from src.models.network.download_recovery import (
    DownloadRecoveryItem,
    DownloadRecoveryReport,
    DownloadRecoveryState,
)


class DownloadRecoveryManager:
    """Reconcile interrupted-download metadata without discarding valid partial files."""

    ORPHAN_PART_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
    ORPHAN_PART_BASE_SUFFIXES = {".jar", ".zip", ".json", ".png", ".jpg", ".jpeg", ".webp", ".mrpack", ".mcwpack"}

    def __init__(self, journal: DownloadJournal | None = None) -> None:
        self.journal = journal or download_journal

    def inspect(self) -> DownloadRecoveryReport:
        items = tuple(self._inspect_entry(entry) for entry in self.journal.snapshot())
        return DownloadRecoveryReport(items=items)

    def reconcile(self, delete_invalid_parts: bool = True) -> DownloadRecoveryReport:
        inspected = self.inspect()
        removable_ids: list[str] = []
        deleted_files = 0
        deleted_bytes = 0

        for item in inspected.items:
            if item.keeps_partial:
                continue
            removable_ids.append(item.request_id)
            if (
                delete_invalid_parts
                and item.state is DownloadRecoveryState.INVALID
                and item.reason == "oversized_partial"
                and self._is_safe_partial(item.destination, item.temporary_path)
            ):
                try:
                    size = item.temporary_path.stat().st_size
                    item.temporary_path.unlink()
                except (FileNotFoundError, IsADirectoryError, OSError):
                    continue
                deleted_files += 1
                deleted_bytes += max(0, int(size))

        removed = self.journal.remove_many(removable_ids)
        return DownloadRecoveryReport(
            items=inspected.items,
            removed_journal_entries=removed,
            deleted_partial_files=deleted_files,
            deleted_partial_bytes=deleted_bytes,
        )

    def remove_orphan_parts(self, max_age_seconds: float | None = None) -> tuple[str, ...]:
        max_age = self.ORPHAN_PART_MAX_AGE_SECONDS if max_age_seconds is None else max(0.0, float(max_age_seconds))
        now = time.time()
        referenced = {Path(str(entry.get("temporary_path") or "")).resolve(strict=False) for entry in self.journal.snapshot() if entry.get("temporary_path")}
        removed: list[str] = []
        roots = (Paths.CACHE_ROOT, Paths.INSTANCES_ROOT)
        for root in roots:
            try:
                candidates = tuple(root.rglob("*.part"))
            except OSError:
                continue
            for path in candidates:
                try:
                    if not path.is_file() or path.is_symlink():
                        continue
                    resolved = path.resolve(strict=False)
                    if resolved in referenced:
                        continue
                    base = path.with_suffix("")
                    if base.suffix.casefold() not in self.ORPHAN_PART_BASE_SUFFIXES:
                        continue
                    if now - path.stat().st_mtime < max_age:
                        continue
                    path.unlink()
                    removed.append(self._safe_relative(path))
                except (OSError, ValueError):
                    continue
        return tuple(sorted(removed, key=str.casefold))

    @staticmethod
    def _safe_relative(path: Path) -> str:
        try:
            return path.resolve(strict=False).relative_to(Paths.root().resolve(strict=False)).as_posix()
        except (OSError, ValueError):
            return path.name

    @classmethod
    def _inspect_entry(cls, entry: dict) -> DownloadRecoveryItem:
        request_id = str(entry.get("request_id") or "").strip()
        display_name = str(entry.get("display_name") or "").strip()
        destination = Path(str(entry.get("destination") or ""))
        temporary_path = Path(str(entry.get("temporary_path") or ""))
        try:
            expected_size = max(0, int(entry.get("expected_size", 0) or 0))
        except (TypeError, ValueError):
            expected_size = 0

        common = {
            "request_id": request_id,
            "display_name": display_name or destination.name or request_id,
            "destination": destination,
            "temporary_path": temporary_path,
            "expected_size": expected_size,
        }
        if not request_id or not str(destination) or not str(temporary_path):
            return DownloadRecoveryItem(
                **common,
                state=DownloadRecoveryState.INVALID,
                downloaded_bytes=0,
                reason="invalid_journal_entry",
            )

        expected_partial = destination.with_name(f"{destination.name}.part")
        if temporary_path != expected_partial:
            return DownloadRecoveryItem(
                **common,
                state=DownloadRecoveryState.INVALID,
                downloaded_bytes=cls._safe_size(temporary_path),
                reason="unexpected_partial_path",
            )

        if destination.exists():
            if not destination.is_file():
                return DownloadRecoveryItem(
                    **common,
                    state=DownloadRecoveryState.INVALID,
                    downloaded_bytes=cls._safe_size(temporary_path),
                    reason="destination_is_not_file",
                )
            destination_size = cls._safe_size(destination)
            if expected_size <= 0 or destination_size == expected_size:
                return DownloadRecoveryItem(
                    **common,
                    state=DownloadRecoveryState.COMPLETED,
                    downloaded_bytes=destination_size,
                    reason="destination_exists",
                )

        if not temporary_path.exists():
            return DownloadRecoveryItem(
                **common,
                state=DownloadRecoveryState.STALE,
                downloaded_bytes=0,
                reason="partial_missing",
            )
        if not temporary_path.is_file():
            return DownloadRecoveryItem(
                **common,
                state=DownloadRecoveryState.INVALID,
                downloaded_bytes=0,
                reason="partial_is_not_file",
            )

        partial_size = cls._safe_size(temporary_path)
        if expected_size > 0 and partial_size > expected_size:
            return DownloadRecoveryItem(
                **common,
                state=DownloadRecoveryState.INVALID,
                downloaded_bytes=partial_size,
                reason="oversized_partial",
            )
        if expected_size > 0 and partial_size == expected_size:
            return DownloadRecoveryItem(
                **common,
                state=DownloadRecoveryState.READY_TO_VERIFY,
                downloaded_bytes=partial_size,
                reason="download_complete_verification_pending",
            )
        return DownloadRecoveryItem(
            **common,
            state=DownloadRecoveryState.RESUMABLE,
            downloaded_bytes=partial_size,
            reason="partial_available",
        )

    @staticmethod
    def _safe_size(path: Path) -> int:
        try:
            return max(0, int(path.stat().st_size)) if path.is_file() else 0
        except OSError:
            return 0

    @staticmethod
    def _is_safe_partial(destination: Path, temporary_path: Path) -> bool:
        if temporary_path != destination.with_name(f"{destination.name}.part"):
            return False
        try:
            candidate = temporary_path.resolve(strict=False)
            allowed_roots = (
                Paths.CACHE_ROOT.resolve(strict=False),
                Paths.INSTANCES_ROOT.resolve(strict=False),
            )
        except OSError:
            return False
        return any(candidate.is_relative_to(root) for root in allowed_roots)


download_recovery_manager = DownloadRecoveryManager()
