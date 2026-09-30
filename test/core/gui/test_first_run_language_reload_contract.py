from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_first_run_setup_can_be_reopened_from_launcher_settings() -> None:
    page_source = (_REPO_ROOT / "src/gui/pages/launcher_settings_page.py").read_text(encoding="utf-8")
    window_source = (_REPO_ROOT / "src/gui/main_window.py").read_text(encoding="utf-8")

    assert "first_run_setup_requested = Signal()" in page_source
    assert "launcher_settings.first_run.button" in page_source
    assert "first_run_setup_requested.connect(self._run_first_run_setup)" in window_source
    assert "def _run_first_run_setup(self)" in window_source


def test_language_change_is_applied_only_after_a_clean_restart() -> None:
    window_source = (_REPO_ROOT / "src/gui/main_window.py").read_text(encoding="utf-8")
    apply_method = window_source.split("    def _apply_gui_settings(self, settings: dict) -> None:\n", 1)[1].split("\n    def _preview_theme", 1)[0]

    assert "language_manager.set_language(self._session_locale, notify=False)" in apply_method
    assert "self._schedule_language_restart_prompt(requested_locale)" in apply_method
    assert "language_manager.set_language(requested_locale" not in apply_method
    assert "def _prompt_language_restart(self)" in window_source
    assert "def _restart_for_language_change(self)" in window_source
    assert "start_restarted_process()" in window_source


def test_first_run_language_selection_does_not_mutate_the_running_locale() -> None:
    source = (_REPO_ROOT / "src/gui/dialogs/first_run_setup_dialog.py").read_text(encoding="utf-8")
    method = source.split("    def _language_changed(self, _index: int) -> None:\n", 1)[1].split("\n    def _back", 1)[0]

    assert "language_manager.set_language" not in method
    assert "self._update_page()" in method
    assert "first_run.language.restart_hint" in source


def test_sidebar_labels_are_resolved_from_semantic_translation_keys() -> None:
    config_source = (_REPO_ROOT / "src/gui/config.py").read_text(encoding="utf-8")
    sidebar_source = (_REPO_ROOT / "src/gui/widget/sidebar_widget.py").read_text(encoding="utf-8")

    assert '("instances", "navigation.instances")' in config_source
    assert '("launcher_settings", "navigation.launcher_settings")' in config_source
    assert "self._button_keys" in sidebar_source
    assert 'label = tr(self._button_keys.get(page_id, ""))' in sidebar_source
