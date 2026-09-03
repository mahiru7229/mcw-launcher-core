from __future__ import annotations

import json
from pathlib import Path

from src.core.config.launcher_settings_manager import LauncherSettingsManager


def test_initialize_creates_launcher_settings_file(tmp_path: Path) -> None:
    path = tmp_path / "config" / "launcher_settings.json"
    manager = LauncherSettingsManager(path)

    assert manager.initialize() == path
    assert path.exists()
    assert manager.load()["gui"]["language"] == "en-US"
    assert manager.load()["gui"]["show_content_descriptions"] is False


def test_save_updates_sections_and_preserves_unknown_options(tmp_path: Path) -> None:
    manager = LauncherSettingsManager(tmp_path / "launcher_settings.json")
    manager.save({
        "gui": {"language": "vi-VN", "future_option": "kept"},
        "launch": {"debug_mode": True},
        "plugins": {"example": True},
    })

    manager.save({"gui": {"show_snapshots": True}})
    data = manager.load()

    assert data["gui"]["language"] == "vi-VN"
    assert data["gui"]["show_snapshots"] is True
    assert data["gui"]["future_option"] == "kept"
    assert data["launch"]["debug_mode"] is True
    assert data["plugins"] == {"example": True}


def test_invalid_file_is_backed_up_and_recreated(tmp_path: Path) -> None:
    path = tmp_path / "launcher_settings.json"
    path.write_text("not json", encoding="utf-8")
    manager = LauncherSettingsManager(path)

    data = manager.load()

    assert data["schema_version"] == manager.SCHEMA_VERSION
    assert json.loads(path.read_text(encoding="utf-8"))["gui"]["start_page"] == "instances"
    assert (tmp_path / "launcher_settings.json.broken").read_text(encoding="utf-8") == "not json"


def test_content_descriptions_are_opt_in_and_persisted(tmp_path: Path) -> None:
    manager = LauncherSettingsManager(tmp_path / "launcher_settings.json")

    assert manager.load()["gui"]["show_content_descriptions"] is False

    manager.update_section("gui", {"show_content_descriptions": True})

    assert manager.load()["gui"]["show_content_descriptions"] is True


def test_window_geometry_round_trip(tmp_path: Path) -> None:
    manager = LauncherSettingsManager(tmp_path / "launcher_settings.json")
    geometry = b"\x00\x01window-geometry\xff"

    manager.save_window_geometry(geometry)

    assert manager.load_window_geometry() == geometry


def test_reset_restores_defaults(tmp_path: Path) -> None:
    manager = LauncherSettingsManager(tmp_path / "launcher_settings.json")
    manager.save({"gui": {"language": "vi-VN"}, "launch": {"debug_mode": True}})

    data = manager.reset()

    assert data == manager.DEFAULT_SETTINGS
    assert manager.load() == manager.DEFAULT_SETTINGS


def test_update_settings_are_created_and_persisted(tmp_path: Path) -> None:
    manager = LauncherSettingsManager(tmp_path / "launcher_settings.json")

    data = manager.load()
    assert data["updates"] == {
        "auto_check": True,
        "channel": "stable",
        "channel_policy_version": manager.UPDATE_CHANNEL_POLICY_VERSION,
        "last_checked_at": None,
    }

    manager.update_section("updates", {"auto_check": False, "last_checked_at": "2026-07-15T12:00:00+00:00"})
    updated = manager.load()["updates"]
    assert updated["auto_check"] is False
    assert updated["channel"] == "stable"
    assert updated["last_checked_at"] == "2026-07-15T12:00:00+00:00"


def test_existing_beta_channel_is_migrated_to_stable_once_for_stable_release(tmp_path: Path) -> None:
    path = tmp_path / "launcher_settings.json"
    path.write_text(json.dumps({
        "schema_version": 5,
        "updates": {
            "auto_check": True,
            "channel": "beta",
            "last_checked_at": None,
        },
    }), encoding="utf-8")
    manager = LauncherSettingsManager(path)

    migrated = manager.load()["updates"]

    assert migrated["channel"] == "stable"
    assert migrated["channel_policy_version"] == manager.UPDATE_CHANNEL_POLICY_VERSION


def test_user_can_join_tester_program_after_stable_migration(tmp_path: Path) -> None:
    path = tmp_path / "launcher_settings.json"
    path.write_text(json.dumps({
        "schema_version": 5,
        "updates": {"channel": "beta"},
    }), encoding="utf-8")
    manager = LauncherSettingsManager(path)

    assert manager.load()["updates"]["channel"] == "stable"
    manager.update_section("updates", {"channel": "beta"})

    assert manager.load()["updates"]["channel"] == "beta"


def test_tester_opt_in_is_preserved_after_current_stable_policy(tmp_path: Path) -> None:
    path = tmp_path / "launcher_settings.json"
    path.write_text(json.dumps({
        "schema_version": 6,
        "updates": {
            "auto_check": True,
            "channel": "beta",
            "channel_policy_version": LauncherSettingsManager.UPDATE_CHANNEL_POLICY_VERSION,
            "last_checked_at": None,
        },
    }), encoding="utf-8")
    manager = LauncherSettingsManager(path)

    assert manager.load()["updates"]["channel"] == "beta"


def test_theme_and_modrinth_channels_are_created_and_persisted(tmp_path: Path) -> None:
    manager = LauncherSettingsManager(tmp_path / "launcher_settings.json")

    data = manager.load()
    assert data["appearance"] == {"theme": "mcw-default", "show_static_text": False, "motion_mode": "full", "live_theme_reload": False, "accent_mode": "theme", "accent_color": "#8ed35b", "text_color_mode": "theme", "text_color": "#f4f4f4"}
    assert data["modrinth"] == {"include_beta": False, "include_alpha": False}

    manager.save({"appearance": {"theme": "pixel-night", "show_static_text": "off", "motion_mode": "reduced", "live_theme_reload": "yes", "accent_mode": "custom", "accent_color": "#B26CFF"}, "modrinth": {"include_beta": True, "include_alpha": "yes"}})
    updated = manager.load()

    assert updated["appearance"] == {"theme": "pixel-night", "show_static_text": False, "motion_mode": "reduced", "live_theme_reload": True, "accent_mode": "custom", "accent_color": "#b26cff", "text_color_mode": "theme", "text_color": "#f4f4f4"}
    assert updated["modrinth"] == {"include_beta": True, "include_alpha": True}



def test_motion_mode_is_normalized_to_supported_values(tmp_path: Path) -> None:
    manager = LauncherSettingsManager(tmp_path / "launcher_settings.json")

    manager.update_section("appearance", {"motion_mode": "off"})
    assert manager.load()["appearance"]["motion_mode"] == "off"

    manager.update_section("appearance", {"motion_mode": "unknown"})
    assert manager.load()["appearance"]["motion_mode"] == "full"

def test_download_limit_is_unlimited_by_default_and_normalized(tmp_path: Path) -> None:
    manager = LauncherSettingsManager(tmp_path / "launcher_settings.json")

    assert manager.load()["network"] == {
        "download_limit_mbps": 0.0,
        "download_concurrency": 0,
        "download_performance_mode": "automatic",
    }

    manager.update_section("network", {"download_limit_mbps": "12.5"})
    assert manager.load()["network"]["download_limit_mbps"] == 12.5

    manager.update_section("network", {"download_limit_mbps": -1})
    assert manager.load()["network"]["download_limit_mbps"] == 0.0

    manager.update_section("network", {"download_limit_mbps": 5000})
    assert manager.load()["network"]["download_limit_mbps"] == 1024.0

    manager.update_section("network", {"download_concurrency": "8"})
    assert manager.load()["network"]["download_concurrency"] == 8

    manager.update_section("network", {"download_concurrency": -1})
    assert manager.load()["network"]["download_concurrency"] == 0

    manager.update_section("network", {"download_concurrency": 99})
    assert manager.load()["network"]["download_concurrency"] == 16

    manager.update_section("network", {"download_performance_mode": "responsive"})
    assert manager.load()["network"]["download_performance_mode"] == "responsive"

    manager.update_section("network", {"download_performance_mode": "unknown"})
    assert manager.load()["network"]["download_performance_mode"] == "automatic"


def test_rc_tester_channel_is_forced_to_stable_for_first_stable_release(tmp_path: Path) -> None:
    path = tmp_path / "launcher_settings.json"
    path.write_text(json.dumps({
        "schema_version": 6,
        "updates": {
            "auto_check": True,
            "channel": "beta",
            "channel_policy_version": 1,
            "last_checked_at": None,
        },
    }), encoding="utf-8")
    manager = LauncherSettingsManager(path)

    updates = manager.load()["updates"]

    assert updates["channel"] == "stable"
    assert updates["channel_policy_version"] == 2


def test_managed_content_failure_defaults_are_source_specific_and_persisted(tmp_path: Path) -> None:
    manager = LauncherSettingsManager(tmp_path / "launcher_settings.json")

    assert manager.load()["managed_content"] == {
        "modrinth_failure_policy": "block",
        "curseforge_failure_policy": "block",
        "forge_preflight_failure_policy": "ask",
    }

    manager.update_section("managed_content", {
        "modrinth_failure_policy": "allow",
        "curseforge_failure_policy": "invalid",
        "forge_preflight_failure_policy": "allow",
    })

    assert manager.load()["managed_content"] == {
        "modrinth_failure_policy": "allow",
        "curseforge_failure_policy": "block",
        "forge_preflight_failure_policy": "allow",
    }


def test_accent_settings_are_normalized_and_migrated(tmp_path: Path) -> None:
    manager = LauncherSettingsManager(tmp_path / "launcher_settings.json")

    manager.update_section("appearance", {"accent_mode": "CUSTOM", "accent_color": "#12ABef"})
    appearance = manager.load()["appearance"]
    assert appearance["accent_mode"] == "custom"
    assert appearance["accent_color"] == "#12abef"

    manager.update_section("appearance", {"accent_mode": "unknown", "accent_color": "blue"})
    appearance = manager.load()["appearance"]
    assert appearance["accent_mode"] == "theme"
    assert appearance["accent_color"] == "#8ed35b"


def test_first_run_and_dedicated_gpu_settings_are_opt_in_and_persisted(tmp_path: Path) -> None:
    manager = LauncherSettingsManager(tmp_path / "launcher_settings.json")

    defaults = manager.load()
    assert defaults["onboarding"] == {"completed": False, "version": 1}
    assert defaults["launch"]["prefer_dedicated_gpu"] is False

    manager.save({
        "onboarding": {"completed": True},
        "launch": {"prefer_dedicated_gpu": True},
    })
    updated = manager.load()

    assert updated["onboarding"] == {"completed": True, "version": 1}
    assert updated["launch"]["prefer_dedicated_gpu"] is True


def test_reset_preserves_completed_first_run_state(tmp_path: Path) -> None:
    manager = LauncherSettingsManager(tmp_path / "launcher_settings.json")
    manager.save({"onboarding": {"completed": True, "version": 1}, "launch": {"debug_mode": True}})

    data = manager.reset()

    assert data["onboarding"] == {"completed": True, "version": 1}
    assert data["launch"]["debug_mode"] is False


def test_legacy_storage_notification_defaults_on_and_can_be_disabled(tmp_path: Path) -> None:
    manager = LauncherSettingsManager(tmp_path / "launcher_settings.json")

    assert manager.load()["storage"]["notify_legacy_cache_cleanup"] is True

    manager.update_section("storage", {"notify_legacy_cache_cleanup": False})

    assert manager.load()["storage"]["notify_legacy_cache_cleanup"] is False


def test_unused_version_retention_days_defaults_and_are_clamped(tmp_path: Path) -> None:
    manager = LauncherSettingsManager(tmp_path / "launcher_settings.json")

    assert manager.load()["storage"]["unused_version_retention_days"] == 14

    manager.update_section("storage", {"unused_version_retention_days": 30})
    assert manager.load()["storage"]["unused_version_retention_days"] == 30

    manager.update_section("storage", {"unused_version_retention_days": 0})
    assert manager.load()["storage"]["unused_version_retention_days"] == 1

    manager.update_section("storage", {"unused_version_retention_days": 9999})
    assert manager.load()["storage"]["unused_version_retention_days"] == 365
