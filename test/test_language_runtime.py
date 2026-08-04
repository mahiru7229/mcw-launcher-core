from pathlib import Path

from src.core.language.language_manager import LanguageManager


def test_dynamic_progress_message_is_localized() -> None:
    manager = LanguageManager(Path(__file__).resolve().parents[1] / "lang")
    manager.set_language("vi-VN", notify=False)

    assert manager.translate("Downloading Fabulously Optimized manifest...") == "Đang tải manifest của Fabulously Optimized..."
