from pathlib import Path

from src.core.language.language_manager import LanguageManager


def test_dynamic_progress_message_is_localized() -> None:
    manager = LanguageManager(Path(__file__).resolve().parents[1] / "lang")
    manager.set_language("vi-VN", notify=False)

    assert manager.translate("Downloading Fabulously Optimized manifest...") == "Đang tải manifest của Fabulously Optimized..."


def test_core_progress_messages_are_localized_in_vietnamese() -> None:
    manager = LanguageManager(Path(__file__).resolve().parents[1] / "lang")
    manager.set_language("vi-VN", notify=False)

    assert manager.translate("Preparing Minecraft libraries...") == "Đang chuẩn bị thư viện Minecraft..."
    assert manager.translate("Preparing Minecraft assets...") == "Đang chuẩn bị asset Minecraft..."
    assert manager.translate("Checking CurseForge files...") == "Đang kiểm tra các file CurseForge..."
    assert manager.translate("Checking CurseForge files after round 2/3...") == "Đang kiểm tra lại các file CurseForge sau lượt 2/3..."


def test_curseforge_file_loading_task_is_localized() -> None:
    manager = LanguageManager(Path(__file__).resolve().parents[1] / "lang")
    manager.set_language("vi-VN", notify=False)

    assert manager.translate("Loading compatible CurseForge files...") == "Đang tải các file CurseForge tương thích..."


def test_controller_runtime_templates_keep_dynamic_values_when_localized() -> None:
    manager = LanguageManager(Path(__file__).resolve().parents[1] / "lang")
    manager.set_language("vi-VN", notify=False)

    assert manager.translate("task.curseforge.install_mod", instance="Example") == "Đang cài mod CurseForge vào 'Example'..."
    assert manager.translate("task.instance.create", name="Test 1.20.1") == "Đang tạo instance 'Test 1.20.1'..."
