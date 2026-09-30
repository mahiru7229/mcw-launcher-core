from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_atlauncher_browser_reuses_rich_detail_panel() -> None:
    source = read("src/gui/dialogs/atlauncher_browser_dialog.py")
    assert "resize_dialog_to_screen(self, 1240, 620" in source
    assert "ContentProjectDetailPanel" in source
    assert "install_modpack_requested" in source
    assert "set_show_project_descriptions" in source


def test_atlauncher_is_wired_through_instance_creation_and_main_window() -> None:
    main = read("src/gui/main_window.py")
    workspace = read("src/gui/pages/instance_workspace_page.py")
    create_dialog = read("src/gui/dialogs/create_instance_dialog.py")

    assert "self.atlauncher_controller" in main
    assert "self.atlauncher_modpack_dialog" in main
    assert "self.atlauncher_controller," in main
    assert "browse_atlauncher_modpacks_requested" in workspace
    assert "browse_atlauncher_requested" in create_dialog


def test_atlauncher_install_has_shared_progress_profile() -> None:
    source = read("src/gui/task_progress.py")
    assert 'task.startswith("atlauncher.install.modpack")' in source
    assert "ProgressStage.DOWNLOADING_MODPACK" in source
