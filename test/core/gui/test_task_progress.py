from src.gui.task_progress import task_progress_profile
from src.models.progress.progress_stage import ProgressStage


def test_profiles_cover_requested_long_running_tasks() -> None:
    expected = {
        "java.scan": ProgressStage.SELECTING_JAVA,
        "mods.update.check": ProgressStage.CHECKING_MODS,
        "modpack.update.check": ProgressStage.CHECKING_MODPACK,
        "backup.create": ProgressStage.EXPORTING_INSTANCE,
        "instance.import": ProgressStage.IMPORTING_INSTANCE,
        "modpack.import": ProgressStage.IMPORTING_INSTANCE,
        "lan.hosting.prepare": ProgressStage.PREPARING,
        "update.prepare": ProgressStage.DOWNLOADING_UPDATE,
        "storage.legacy.probe": ProgressStage.PREPARING,
        "storage.legacy.scan": ProgressStage.PREPARING,
        "storage.legacy.clean": ProgressStage.PREPARING,
        "modrinth.install.modpack": ProgressStage.DOWNLOADING_MODPACK,
        "curseforge.install.mod": ProgressStage.DOWNLOADING_MODS,
        "content.install.modrinth": ProgressStage.DOWNLOADING_CONTENT,
    }

    assert {task_id: task_progress_profile(task_id).stage for task_id in expected} == expected


def test_legacy_storage_scan_has_its_own_completion_detail() -> None:
    profile = task_progress_profile("storage.legacy.scan")

    assert profile is not None
    assert profile.success_message == "storage.legacy.scan.completed"
    assert profile.success_detail == "storage.legacy.scan.completed_detail"


def test_profile_lookup_ignores_unrelated_background_searches() -> None:
    assert task_progress_profile("mod_catalog.search.fabric") is None


def test_legacy_storage_probe_and_cleanup_have_terminal_progress_profiles() -> None:
    probe = task_progress_profile("storage.legacy.probe")
    cleanup = task_progress_profile("storage.legacy.clean")

    assert probe is not None
    assert probe.success_message == "storage.legacy.scan.completed"
    assert cleanup is not None
    assert cleanup.success_message == "storage.legacy.clean.completed"
    assert cleanup.success_detail == "storage.legacy.clean.completed_detail"
