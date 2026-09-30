from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_ftb_browser_is_wide_and_reuses_rich_detail_panel() -> None:
    source = read("src/gui/dialogs/ftb_browser_dialog.py")

    assert "resize_dialog_to_screen(self, 1240, 620" in source
    assert "ContentProjectDetailPanel" in source
    assert "set_show_project_descriptions" in source
    assert "QTimer.singleShot(0" in source
    assert "install_modpack_requested" in source


def test_ftb_is_wired_through_instance_creation_and_main_window() -> None:
    main = read("src/gui/main_window.py")
    workspace = read("src/gui/pages/instance_workspace_page.py")
    create_dialog = read("src/gui/dialogs/create_instance_dialog.py")

    assert "self.ftb_controller" in main
    assert "self.ftb_modpack_dialog" in main
    assert "self.ftb_controller," in main
    assert "browse_ftb_modpacks_requested" in workspace
    assert "browse_ftb_requested" in create_dialog


def test_ftb_install_has_shared_progress_profile() -> None:
    source = read("src/gui/task_progress.py")
    assert 'task.startswith("ftb.install.modpack")' in source
    assert "ProgressStage.DOWNLOADING_MODPACK" in source
