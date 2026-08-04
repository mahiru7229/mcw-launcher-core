from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _translations(locale: str) -> dict[str, str]:
    payload = json.loads((ROOT / "lang" / f"{locale}.json").read_text(encoding="utf-8"))
    return payload["translations"]


def test_navigation_language_contract() -> None:
    english = _translations("en-US")
    vietnamese = _translations("vi-VN")

    assert set(english) == set(vietnamese)
    assert english["navigation.instances"] == "Instance"
    assert vietnamese["navigation.instances"] == "Instance"
    assert vietnamese["navigation.launcher_settings"] == "Cài đặt launcher"
    assert "language.restart.message" in english
    assert "language.restart.message" in vietnamese
