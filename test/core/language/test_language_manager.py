from __future__ import annotations

import json
from pathlib import Path

from src.core.language.language_manager import LanguageManager


def _write_pack(directory: Path, locale: str, name: str, translations: dict[str, str], aliases: dict[str, str] | None = None) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    payload = {"meta": {"locale": locale, "name": name, "version": 1}, "translations": translations}
    if aliases is not None:
        payload["aliases"] = aliases
    (directory / f"{locale}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_discovers_json_language_packs(tmp_path: Path) -> None:
    _write_pack(tmp_path, "en-US", "English - US", {"navigation.home": "Home"})
    _write_pack(tmp_path, "vi-VN", "Tiếng Việt - Việt Nam", {"navigation.home": "Trang chủ"})

    manager = LanguageManager(tmp_path)

    assert [(item.locale, item.name) for item in manager.available_languages()] == [
        ("en-US", "English - US"),
        ("vi-VN", "Tiếng Việt - Việt Nam"),
    ]


def test_switches_language_and_formats_semantic_key(tmp_path: Path) -> None:
    _write_pack(tmp_path, "en-US", "English - US", {"account.greeting": "Hello {name}"})
    _write_pack(tmp_path, "vi-VN", "Tiếng Việt - Việt Nam", {"account.greeting": "Xin chào {name}"})
    manager = LanguageManager(tmp_path)

    assert manager.set_language("vi-VN") is True
    assert manager.translate("account.greeting", name="Tùng") == "Xin chào Tùng"


def test_english_alias_keeps_existing_gui_text_compatible(tmp_path: Path) -> None:
    _write_pack(tmp_path, "en-US", "English - US", {"navigation.home": "Home"}, {"Home": "navigation.home"})
    _write_pack(tmp_path, "vi-VN", "Tiếng Việt - Việt Nam", {"navigation.home": "Trang chủ"})
    manager = LanguageManager(tmp_path)

    manager.set_language("vi-VN")

    assert manager.resolve_key("Home") == "navigation.home"
    assert manager.translate("Home") == "Trang chủ"
    assert manager.translate("navigation.home") == "Trang chủ"


def test_missing_translation_falls_back_to_english_semantic_value(tmp_path: Path) -> None:
    _write_pack(tmp_path, "en-US", "English - US", {"instance.create.success": "Instance created."})
    _write_pack(tmp_path, "vi-VN", "Tiếng Việt - Việt Nam", {})
    manager = LanguageManager(tmp_path)

    manager.set_language("vi-VN")

    assert manager.translate("instance.create.success") == "Instance created."
    assert manager.missing_keys() == ["instance.create.success"]


def test_reports_placeholder_mismatch(tmp_path: Path) -> None:
    _write_pack(tmp_path, "en-US", "English - US", {"instance.created": "Created {name}"})
    _write_pack(tmp_path, "vi-VN", "Tiếng Việt - Việt Nam", {"instance.created": "Đã tạo {instance}"})
    manager = LanguageManager(tmp_path)

    manager.set_language("vi-VN")

    assert manager.placeholder_mismatches() == {"instance.created": ({"name"}, {"instance"})}


def test_falls_back_to_english_for_unknown_locale(tmp_path: Path) -> None:
    _write_pack(tmp_path, "en-US", "English - US", {"navigation.home": "Home"})
    manager = LanguageManager(tmp_path)

    assert manager.set_language("missing") is True
    assert manager.current_locale == "en-US"
    assert manager.translate("unknown.key") == "unknown.key"


def test_ignores_invalid_language_pack(tmp_path: Path) -> None:
    _write_pack(tmp_path, "en-US", "English - US", {})
    (tmp_path / "broken.json").write_text("not json", encoding="utf-8")

    manager = LanguageManager(tmp_path)

    assert [item.locale for item in manager.available_languages()] == ["en-US"]


def test_builtin_language_packs_have_expected_names_and_matching_keys() -> None:
    manager = LanguageManager(Path(__file__).resolve().parents[3] / "lang")

    assert {item.locale: item.name for item in manager.available_languages()} == {
        "en-US": "English - US",
        "vi-VN": "Tiếng Việt - Việt Nam",
    }
    assert manager.missing_keys("vi-VN") == []
    assert manager.placeholder_mismatches("vi-VN") == {}
