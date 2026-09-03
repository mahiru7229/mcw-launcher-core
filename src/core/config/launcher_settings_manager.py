from __future__ import annotations

import base64
import copy
import json
import math
import os
import threading
from pathlib import Path
from typing import Any

from src.core.config.managed_content_policy import ManagedContentPolicy
from src.core.fs.paths import Paths
from src.core.instance.settings_manager import SettingsManager, default_instance_settings
from src.core.theme.theme_palette import normalize_hex_color


class LauncherSettingsManager:
    SCHEMA_VERSION = 19
    UPDATE_CHANNEL_POLICY_VERSION = 2
    DEFAULT_SETTINGS = {
        "schema_version": SCHEMA_VERSION,
        "gui": {
            "start_page": "instances",
            "show_snapshots": False,
            "remember_window_size": True,
            "language": "en-US",
            "show_content_descriptions": False,
        },
        "launch": {
            "debug_mode": False,
            "prefer_dedicated_gpu": False,
        },
        "onboarding": {
            "completed": False,
            "version": 1,
        },
        "window": {
            "geometry": None,
        },
        "appearance": {
            "theme": "mcw-default",
            "show_static_text": False,
            "motion_mode": "full",
            "live_theme_reload": False,
            "accent_mode": "theme",
            "accent_color": "#8ed35b",
            "text_color_mode": "theme",
            "text_color": "#f4f4f4",
        },
        "modrinth": {
            "include_beta": False,
            "include_alpha": False,
        },
        "managed_content": {
            "modrinth_failure_policy": "block",
            "curseforge_failure_policy": "block",
            "forge_preflight_failure_policy": "ask",
        },
        "network": {
            "download_limit_mbps": 0.0,
            "download_concurrency": 0,
            "download_performance_mode": "automatic",
        },
        "storage": {
            "notify_legacy_cache_cleanup": True,
            "unused_version_retention_days": 14,
        },
        "instance_defaults": default_instance_settings(),
        "updates": {
            "auto_check": True,
            "channel": "stable",
            "channel_policy_version": UPDATE_CHANNEL_POLICY_VERSION,
            "last_checked_at": None,
        },
    }

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else Paths.launcher_settings_path()
        self._lock = threading.RLock()

    def initialize(self) -> Path:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if not self.path.exists():
                self._write(copy.deepcopy(self.DEFAULT_SETTINGS))
            else:
                data = self._read_or_recover()
                normalized = self._normalize(data)
                if normalized != data:
                    self._write(normalized)
            return self.path

    def load(self) -> dict[str, Any]:
        with self._lock:
            self.initialize()
            return copy.deepcopy(self._normalize(self._read_or_recover()))

    def save(self, settings: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(settings, dict):
            raise TypeError("Launcher settings must be a dictionary.")

        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            current = self._read_or_recover() if self.path.exists() else copy.deepcopy(self.DEFAULT_SETTINGS)
            merged = self._deep_merge(current, settings)
            normalized = self._normalize(merged)
            self._write(normalized)
            return copy.deepcopy(normalized)

    def update_section(self, section: str, values: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(values, dict):
            raise TypeError("Launcher settings section must be a dictionary.")
        return self.save({str(section): values})

    def reset(self) -> dict[str, Any]:
        with self._lock:
            current = self._read_or_recover() if self.path.exists() else {}
            defaults = copy.deepcopy(self.DEFAULT_SETTINGS)
            onboarding = current.get("onboarding") if isinstance(current.get("onboarding"), dict) else {}
            if self._as_bool(onboarding.get("completed"), False):
                defaults["onboarding"] = {
                    "completed": True,
                    "version": max(1, self._as_non_negative_int(onboarding.get("version"), 1)),
                }
            self._write(defaults)
            return defaults

    def load_window_geometry(self) -> bytes | None:
        encoded = self.load().get("window", {}).get("geometry")
        if not isinstance(encoded, str) or not encoded:
            return None
        try:
            return base64.b64decode(encoded.encode("ascii"), validate=True)
        except (ValueError, UnicodeEncodeError):
            return None

    def save_window_geometry(self, geometry: bytes | bytearray | memoryview) -> None:
        encoded = base64.b64encode(bytes(geometry)).decode("ascii")
        self.update_section("window", {"geometry": encoded})

    def _read_or_recover(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Launcher settings root must be an object.")
            return data
        except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
            self._backup_broken_file()
            defaults = copy.deepcopy(self.DEFAULT_SETTINGS)
            self._write(defaults)
            return defaults

    def _backup_broken_file(self) -> None:
        if not self.path.exists():
            return

        candidate = self.path.with_name(f"{self.path.name}.broken")
        counter = 2
        while candidate.exists():
            candidate = self.path.with_name(f"{self.path.name}.broken.{counter}")
            counter += 1

        try:
            self.path.replace(candidate)
        except OSError:
            try:
                self.path.unlink()
            except OSError:
                pass

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_name(f"{self.path.name}.tmp")
        payload = json.dumps(data, indent=4, ensure_ascii=False) + "\n"

        with temporary_path.open("w", encoding="utf-8", newline="\n") as file:
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())

        temporary_path.replace(self.path)

    def _normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        raw_updates = data.get("updates") if isinstance(data.get("updates"), dict) else {}
        raw_channel_policy_version = self._as_non_negative_int(raw_updates.get("channel_policy_version"), 0)
        normalized = self._deep_merge(copy.deepcopy(self.DEFAULT_SETTINGS), data)
        normalized["schema_version"] = self.SCHEMA_VERSION

        gui = normalized.setdefault("gui", {})
        start_page = str(gui.get("start_page") or "instances").strip()
        gui["start_page"] = start_page if start_page in {"instances", "accounts", "launcher_settings", "logs", "about"} else "instances"
        gui["show_snapshots"] = self._as_bool(gui.get("show_snapshots"), False)
        gui["remember_window_size"] = self._as_bool(gui.get("remember_window_size"), True)
        gui["language"] = str(gui.get("language") or "en-US")
        gui["show_content_descriptions"] = self._as_bool(gui.get("show_content_descriptions"), False)

        launch = normalized.setdefault("launch", {})
        launch["debug_mode"] = self._as_bool(launch.get("debug_mode"), False)
        launch["prefer_dedicated_gpu"] = self._as_bool(launch.get("prefer_dedicated_gpu"), False)

        onboarding = normalized.setdefault("onboarding", {})
        onboarding["completed"] = self._as_bool(onboarding.get("completed"), False)
        onboarding["version"] = max(1, self._as_non_negative_int(onboarding.get("version"), 1))

        window = normalized.setdefault("window", {})
        geometry = window.get("geometry")
        window["geometry"] = geometry if isinstance(geometry, str) and geometry else None

        appearance = normalized.setdefault("appearance", {})
        appearance["theme"] = str(appearance.get("theme") or "mcw-default").strip() or "mcw-default"
        appearance["show_static_text"] = self._as_bool(appearance.get("show_static_text"), False)
        motion_mode = str(appearance.get("motion_mode") or "full").strip().lower()
        appearance["motion_mode"] = motion_mode if motion_mode in {"full", "reduced", "off"} else "full"
        appearance["live_theme_reload"] = self._as_bool(appearance.get("live_theme_reload"), False)
        accent_mode = str(appearance.get("accent_mode") or "theme").strip().lower()
        appearance["accent_mode"] = accent_mode if accent_mode in {"theme", "custom"} else "theme"
        try:
            appearance["accent_color"] = normalize_hex_color(appearance.get("accent_color") or "#8ed35b")
        except ValueError:
            appearance["accent_color"] = "#8ed35b"
        text_color_mode = str(appearance.get("text_color_mode") or "theme").strip().lower()
        appearance["text_color_mode"] = text_color_mode if text_color_mode in {"theme", "custom"} else "theme"
        try:
            appearance["text_color"] = normalize_hex_color(appearance.get("text_color") or "#f4f4f4")
        except ValueError:
            appearance["text_color"] = "#f4f4f4"

        modrinth = normalized.setdefault("modrinth", {})
        modrinth["include_beta"] = self._as_bool(modrinth.get("include_beta"), False)
        modrinth["include_alpha"] = self._as_bool(modrinth.get("include_alpha"), False)

        managed_content = normalized.setdefault("managed_content", {})
        managed_content["modrinth_failure_policy"] = ManagedContentPolicy.normalize_global(managed_content.get("modrinth_failure_policy"))
        managed_content["curseforge_failure_policy"] = ManagedContentPolicy.normalize_global(managed_content.get("curseforge_failure_policy"))
        managed_content["forge_preflight_failure_policy"] = ManagedContentPolicy.normalize_global(managed_content.get("forge_preflight_failure_policy"), ManagedContentPolicy.ASK)

        network = normalized.setdefault("network", {})
        network["download_limit_mbps"] = self._as_download_limit(network.get("download_limit_mbps"))
        network["download_concurrency"] = self._as_download_concurrency(network.get("download_concurrency"))
        network["download_performance_mode"] = self._as_download_performance_mode(network.get("download_performance_mode"))

        storage = normalized.setdefault("storage", {})
        storage["notify_legacy_cache_cleanup"] = self._as_bool(storage.get("notify_legacy_cache_cleanup"), True)
        storage["unused_version_retention_days"] = max(1, min(self._as_non_negative_int(storage.get("unused_version_retention_days"), 14), 365))

        normalized["instance_defaults"] = SettingsManager.normalize_dict(normalized.get("instance_defaults"))

        updates = normalized.setdefault("updates", {})
        updates["auto_check"] = self._as_bool(updates.get("auto_check"), True)
        channel = str(updates.get("channel") or "stable").strip().lower()
        normalized_channel = channel if channel in {"stable", "beta"} else "stable"
        if raw_channel_policy_version < self.UPDATE_CHANNEL_POLICY_VERSION:
            normalized_channel = "stable"
        updates["channel"] = normalized_channel
        updates["channel_policy_version"] = self.UPDATE_CHANNEL_POLICY_VERSION
        last_checked_at = updates.get("last_checked_at")
        updates["last_checked_at"] = last_checked_at if isinstance(last_checked_at, str) and last_checked_at else None

        return normalized

    @classmethod
    def _deep_merge(cls, base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
        result = copy.deepcopy(base)
        for key, value in overlay.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = cls._deep_merge(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
        return result

    @staticmethod
    def _as_non_negative_int(value: Any, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed >= 0 else default

    @staticmethod
    def _as_download_limit(value: Any) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0.0
        if parsed <= 0 or not math.isfinite(parsed):
            return 0.0
        return min(parsed, 1024.0)


    @staticmethod
    def _as_download_concurrency(value: Any) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 0
        if parsed <= 0:
            return 0
        return min(max(parsed, 1), 16)

    @staticmethod
    def _as_download_performance_mode(value: Any) -> str:
        normalized = str(value or "automatic").strip().lower()
        return normalized if normalized in {"automatic", "responsive", "balanced", "maximum"} else "automatic"

    @staticmethod
    def _as_bool(value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
        if isinstance(value, (int, float)):
            return bool(value)
        return default
