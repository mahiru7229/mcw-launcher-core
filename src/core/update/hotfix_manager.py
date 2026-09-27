from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import logging
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Callable
import uuid
import zipfile

import httpx

from src.core.update.versioning import LauncherVersion

logger = logging.getLogger(__name__)

DEFAULT_HOTFIX_MANIFEST_URL = "https://mcw-download.pages.dev/hotfixes/manifest.json"


class HotfixMetaPathFinder(importlib.abc.MetaPathFinder):
    """Custom meta-path finder that intercepts module imports for files present in hotfixes/live."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def find_spec(
        self,
        fullname: str,
        path: object = None,
        target: object = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if not self.root.is_dir():
            return None
        parts = fullname.split(".")
        candidate = self.root.joinpath(*parts)
        candidate_file = candidate.with_suffix(".py")
        if candidate_file.is_file():
            return importlib.util.spec_from_file_location(fullname, candidate_file)
        init_file = candidate / "__init__.py"
        if init_file.is_file():
            return importlib.util.spec_from_file_location(
                fullname,
                init_file,
                submodule_search_locations=[str(candidate)],
            )
        return None


class HotfixError(Exception):
    """Base exception for all hotfix-related operations."""


class HotfixVerificationError(HotfixError):
    """Raised when checksum or signature verification fails (Fail-closed)."""


class HotfixSecurityError(HotfixError):
    """Raised when archive contains malicious contents (e.g. Zip Slip traversal)."""


class HotfixNetworkError(HotfixError):
    """Raised when network transport or CDN distribution fails."""


@dataclass(frozen=True, slots=True)
class HotfixEntry:
    """Represents an active hotfix patch descriptor from the manifest."""

    base_version: str
    target_version: str
    hotfix_id: int
    release_tag: str
    description: str
    enabled: bool
    download_url: str
    sha256: str
    size_bytes: int
    clean_on_upgrade: bool = True
    target_modules: list[str] = field(default_factory=list)

    @property
    def target_launcher_version(self) -> LauncherVersion:
        return LauncherVersion.parse(self.target_version)

    @property
    def base_launcher_version(self) -> LauncherVersion:
        return LauncherVersion.parse(self.base_version)


@dataclass(frozen=True, slots=True)
class HotfixState:
    """Represents the currently installed hotfix state on disk."""

    applied_hotfix_id: int
    base_version: str
    target_version: str
    installed_at: str
    sha256: str
    modules: list[str] = field(default_factory=list)
    clean_on_upgrade: bool = True


class HotfixManager:
    """Core distribution and lifecycle engine for dynamic hotfix patches.

    Operates in conjunction with the Cloudflare Edge CDN (mcw-download.pages.dev)
    to distribute verified python-level runtime patches without requiring a full
    multi-megabyte launcher binary reinstall.
    """

    MAX_ARCHIVE_BYTES: int = 50 * 1024 * 1024  # 50 MB
    MAX_EXTRACTED_BYTES: int = 100 * 1024 * 1024  # 100 MB
    MAX_ARCHIVE_ENTRIES: int = 1_000

    def __init__(
        self,
        root_directory: Path | None = None,
        manifest_url: str = DEFAULT_HOTFIX_MANIFEST_URL,
        client: httpx.Client | None = None,
    ) -> None:
        self.root_directory = self._resolve_project_root(root_directory)
        self.hotfix_root = self.root_directory / "hotfixes"
        self.live_dir = self.hotfix_root / "live"
        self.state_file = self.hotfix_root / "state.json"
        self.manifest_url = manifest_url
        self._client = client

    @staticmethod
    def _resolve_project_root(explicit: Path | None = None) -> Path:
        if explicit is not None:
            return explicit.resolve()
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parents[3]

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=httpx.Timeout(15.0, connect=10.0),
                follow_redirects=True,
                headers={"User-Agent": "MCW-Launcher/HotfixEngine"},
            )
        return self._client

    # -------------------------------------------------------------------------
    # State Management & Sys.Path Injection
    # -------------------------------------------------------------------------

    def load_state(self) -> HotfixState | None:
        if not self.state_file.is_file():
            return None
        try:
            payload = json.loads(self.state_file.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return None
            return HotfixState(
                applied_hotfix_id=int(payload["applied_hotfix_id"]),
                base_version=str(payload["base_version"]),
                target_version=str(payload["target_version"]),
                installed_at=str(payload.get("installed_at", "")),
                sha256=str(payload.get("sha256", "")).casefold(),
                modules=list(payload.get("modules", [])),
                clean_on_upgrade=bool(payload.get("clean_on_upgrade", True)),
            )
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("Failed to parse hotfix state.json: %s", exc)
            return None

    def save_state(self, state: HotfixState) -> None:
        self.hotfix_root.mkdir(parents=True, exist_ok=True)
        temp_path = self.hotfix_root / f"state.json.{uuid.uuid4().hex}.tmp"
        temp_path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")
        temp_path.replace(self.state_file)

    @staticmethod
    def _matches_base_version(candidate_base: str, current_base: str) -> bool:
        """Check if candidate base version matches current launcher base version.

        Supports both exact string matching and 3-part major.minor.patch equivalence
        (e.g., matching '1.7.0' against '1.7.0-alpha.1').
        """
        if str(candidate_base).strip() == str(current_base).strip():
            return True
        try:
            cand_v = LauncherVersion.parse(candidate_base)
            curr_v = LauncherVersion.parse(current_base)
            return (cand_v.major, cand_v.minor, cand_v.patch) == (curr_v.major, curr_v.minor, curr_v.patch)
        except ValueError:
            return False

    def get_effective_version(self, base_version: str) -> str:
        state = self.load_state()
        if state is not None and self._matches_base_version(state.base_version, base_version):
            return state.target_version
        return base_version

    def cleanup_on_upgrade(self, current_base_version: str) -> bool:
        """Purge obsolete hotfixes when the launcher's base version changes."""
        state = self.load_state()
        if state is None:
            return False
        if state.clean_on_upgrade and not self._matches_base_version(state.base_version, current_base_version):
            logger.info(
                "Upgraded base version from %s to %s; purging obsolete hotfix %s",
                state.base_version,
                current_base_version,
                state.target_version,
            )
            self.rollback()
            return True
        return False

    @classmethod
    def _install_meta_path_finder(cls, live_dir: Path) -> None:
        cls._remove_meta_path_finder()
        sys.meta_path.insert(0, HotfixMetaPathFinder(live_dir))

    @classmethod
    def _remove_meta_path_finder(cls) -> None:
        sys.meta_path[:] = [
            f for f in sys.meta_path if not isinstance(f, HotfixMetaPathFinder)
        ]

    @classmethod
    def bootstrap_sys_path(
        cls,
        root_directory: Path | None = None,
        current_base_version: str | None = None,
        auto_sync: bool = False,
    ) -> bool:
        """Inject hotfixes/live directory to the front of sys.path and sys.meta_path if active.

        Called at the earliest stage of launcher startup (before major module imports).
        If auto_sync is True and current_base_version is provided, attempts a fast fail-open
        sync against the Cloudflare Edge CDN before bootstrapping.
        """
        manager = cls(root_directory=root_directory)
        if current_base_version is not None:
            manager.cleanup_on_upgrade(current_base_version)
            if auto_sync:
                manager.sync_active_hotfix(current_base_version)

        state = manager.load_state()
        if state is None:
            return False

        if current_base_version is not None and not cls._matches_base_version(state.base_version, current_base_version):
            return False

        if not manager.live_dir.is_dir():
            return False

        live_str = str(manager.live_dir.resolve())
        if live_str not in sys.path:
            sys.path.insert(0, live_str)
        cls._install_meta_path_finder(manager.live_dir)
        logger.info("Hotfix %s injected into sys.path[0] and sys.meta_path: %s", state.target_version, live_str)
        return True

    # -------------------------------------------------------------------------
    # Manifest & Discovery
    # -------------------------------------------------------------------------

    def fetch_manifest(self, manifest_url: str | None = None, timeout: float | None = None) -> list[HotfixEntry]:
        url = manifest_url or self.manifest_url
        try:
            req_timeout = timeout if timeout is not None else 10.0
            response = self.client.get(url, timeout=req_timeout)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise HotfixNetworkError(f"Failed to fetch hotfix manifest from {url}: {exc}") from exc
        except (json.JSONDecodeError, ValueError) as exc:
            raise HotfixError(f"Malformed hotfix manifest JSON from {url}: {exc}") from exc

        if not isinstance(payload, dict):
            raise HotfixError("Manifest root must be a JSON object.")
        if int(payload.get("schema_version", 0) or 0) != 1:
            raise HotfixError(f"Unsupported manifest schema_version: {payload.get('schema_version')}")

        entries: list[HotfixEntry] = []
        raw_entries = payload.get("active_hotfixes", [])
        if not isinstance(raw_entries, list):
            return entries

        for item in raw_entries:
            if not isinstance(item, dict):
                continue
            try:
                entry = HotfixEntry(
                    base_version=str(item["base_version"]).strip(),
                    target_version=str(item["target_version"]).strip(),
                    hotfix_id=int(item["hotfix_id"]),
                    release_tag=str(item.get("release_tag", f"v{item['target_version']}")),
                    description=str(item.get("description", "")),
                    enabled=bool(item.get("enabled", False)),
                    download_url=str(item["download_url"]),
                    sha256=str(item["sha256"]).strip().casefold(),
                    size_bytes=int(item.get("size_bytes", 0)),
                    clean_on_upgrade=bool(item.get("clean_on_upgrade", True)),
                    target_modules=list(item.get("target_modules", [])),
                )
                entries.append(entry)
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("Skipping invalid hotfix entry %s: %s", item, exc)
        return entries

    def check_for_hotfix(
        self,
        current_base_version: str,
        current_hotfix_id: int | None = None,
        manifest_url: str | None = None,
        timeout: float | None = None,
    ) -> HotfixEntry | None:
        """Find the newest enabled hotfix applicable to the current base version."""
        if current_hotfix_id is None:
            state = self.load_state()
            if state is not None and self._matches_base_version(state.base_version, current_base_version):
                current_hotfix_id = state.applied_hotfix_id
            else:
                current_hotfix_id = 0

        entries = self.fetch_manifest(manifest_url, timeout=timeout)
        eligible = [
            e
            for e in entries
            if e.enabled
            and self._matches_base_version(e.base_version, current_base_version)
            and e.hotfix_id > current_hotfix_id
        ]
        if not eligible:
            return None

        # Sort descending by hotfix_id to select the latest patch
        eligible.sort(key=lambda e: e.hotfix_id, reverse=True)
        return eligible[0]

    def sync_active_hotfix(
        self,
        current_base_version: str,
        timeout: float = 3.0,
    ) -> HotfixState | None:
        """Check Cloudflare Edge CDN and automatically apply latest eligible hotfix if newer.

        Designed to be fail-open: any network timeout or transport failure is logged,
        allowing the launcher to proceed with existing state without crashing or freezing.
        """
        try:
            current_state = self.load_state()
            current_id = current_state.applied_hotfix_id if current_state else 0
            eligible = self.check_for_hotfix(current_base_version, current_hotfix_id=current_id, timeout=timeout)
            if eligible is not None:
                logger.info(
                    "Newer hotfix %s (ID %d) discovered on CDN. Downloading and applying...",
                    eligible.target_version,
                    eligible.hotfix_id,
                )
                return self.apply_hotfix(eligible)
            return current_state
        except Exception as exc:
            logger.debug("Automatic hotfix sync skipped due to network/CDN condition: %s", exc)
            return self.load_state()

    # -------------------------------------------------------------------------
    # Verification, Extraction & Application
    # -------------------------------------------------------------------------

    def _verify_checksum(self, file_path: Path, expected_sha256: str) -> None:
        digest = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(64 * 1024):
                digest.update(chunk)
        actual = digest.hexdigest().casefold()
        if actual != expected_sha256.casefold():
            raise HotfixVerificationError(
                f"Checksum mismatch for hotfix archive {file_path.name}: "
                f"expected {expected_sha256}, got {actual}"
            )

    def _extract_archive_safely(self, archive_path: Path, destination: Path) -> None:
        """Extract zip archive with strict Zip Slip traversal and quota defenses."""
        destination_resolved = destination.resolve()
        total_extracted_size = 0
        entry_count = 0

        with zipfile.ZipFile(archive_path, "r") as archive:
            entries = archive.infolist()
            if len(entries) > self.MAX_ARCHIVE_ENTRIES:
                raise HotfixSecurityError(
                    f"Archive exceeds maximum entries quota ({len(entries)} > {self.MAX_ARCHIVE_ENTRIES})"
                )

            # Pre-flight check: validate every path before writing anything
            for member in entries:
                entry_count += 1
                total_extracted_size += member.file_size
                if total_extracted_size > self.MAX_EXTRACTED_BYTES:
                    raise HotfixSecurityError(
                        f"Archive uncompressed size exceeds limit ({total_extracted_size} > {self.MAX_EXTRACTED_BYTES})"
                    )

                # Path traversal check
                member_path = member.filename
                if os.path.isabs(member_path) or member_path.startswith(("/", "\\")):
                    raise HotfixSecurityError(f"Absolute path in hotfix archive: {member_path}")

                target = (destination / member_path).resolve()
                if not (target == destination_resolved or destination_resolved in target.parents):
                    raise HotfixSecurityError(f"Zip Slip directory traversal detected: {member_path}")

            # Safe extraction
            archive.extractall(destination)

    def apply_hotfix(
        self,
        entry: HotfixEntry,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> HotfixState:
        """Download, verify, and atomically install a hotfix."""
        self.hotfix_root.mkdir(parents=True, exist_ok=True)
        staging_dir = self.hotfix_root / f"staging_{uuid.uuid4().hex}"
        archive_path = self.hotfix_root / f"download_{uuid.uuid4().hex}.zip"

        try:
            if progress_callback:
                progress_callback(10, f"Downloading Hotfix {entry.target_version}...")

            # 1. Download
            with self.client.stream("GET", entry.download_url) as response:
                response.raise_for_status()
                with open(archive_path, "wb") as f:
                    downloaded = 0
                    for chunk in response.iter_bytes(chunk_size=32 * 1024):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if downloaded > self.MAX_ARCHIVE_BYTES:
                            raise HotfixSecurityError(
                                f"Downloaded size exceeds maximum limit ({downloaded} > {self.MAX_ARCHIVE_BYTES})"
                            )

            if progress_callback:
                progress_callback(50, "Verifying patch cryptographic checksum...")

            # 2. Checksum (Fail-closed)
            self._verify_checksum(archive_path, entry.sha256)

            if progress_callback:
                progress_callback(70, "Unpacking patch modules...")

            # 3. Extract to staging
            staging_dir.mkdir(parents=True, exist_ok=False)
            self._extract_archive_safely(archive_path, staging_dir)

            # 4. Atomic directory swap
            if progress_callback:
                progress_callback(90, "Applying patch atomically...")

            backup_dir = self.hotfix_root / f"backup_{uuid.uuid4().hex}"
            if self.live_dir.is_dir():
                self.live_dir.rename(backup_dir)

            try:
                staging_dir.rename(self.live_dir)
            except Exception:
                if backup_dir.is_dir() and not self.live_dir.is_dir():
                    backup_dir.rename(self.live_dir)
                raise
            else:
                if backup_dir.is_dir():
                    shutil.rmtree(backup_dir, ignore_errors=True)

            # 5. Persist state
            state = HotfixState(
                applied_hotfix_id=entry.hotfix_id,
                base_version=entry.base_version,
                target_version=entry.target_version,
                installed_at=datetime.now(timezone.utc).isoformat(),
                sha256=entry.sha256,
                modules=list(entry.target_modules),
                clean_on_upgrade=entry.clean_on_upgrade,
            )
            self.save_state(state)

            live_str = str(self.live_dir.resolve())
            if live_str not in sys.path:
                sys.path.insert(0, live_str)
            self._install_meta_path_finder(self.live_dir)

            if progress_callback:
                progress_callback(100, f"Hotfix {entry.target_version} successfully applied.")

            return state
        finally:
            archive_path.unlink(missing_ok=True)
            if staging_dir.is_dir():
                shutil.rmtree(staging_dir, ignore_errors=True)

    def rollback(self) -> bool:
        """Roll back active hotfix, returning launcher to clean base state."""
        changed = False
        self._remove_meta_path_finder()
        live_str = str(self.live_dir.resolve())
        while live_str in sys.path:
            sys.path.remove(live_str)
            changed = True
        if self.live_dir.is_dir():
            shutil.rmtree(self.live_dir, ignore_errors=True)
            changed = True
        if self.state_file.is_file():
            self.state_file.unlink(missing_ok=True)
            changed = True
        return changed
