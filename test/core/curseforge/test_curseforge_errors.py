from pathlib import Path

from src.core.curseforge.curseforge_content_manager import CurseForgeManagedFilesRequired as ReExportedError
from mcw_core.api.curseforge.curseforge_errors import CurseForgeManagedFilesRequired
from src.models.curseforge.manual_download import CurseForgeManualDownload


class _Instance:
    name = "Test Instance"
    instance_dir = Path("instances/Test Instance")


def test_managed_files_required_is_reexported_for_backward_compatibility() -> None:
    assert ReExportedError is CurseForgeManagedFilesRequired


def test_managed_files_required_preserves_recovery_context() -> None:
    requirement = CurseForgeManualDownload(
        project_id=1,
        file_id=2,
        project_name="Example",
        file_name="example.jar",
        file_size=10,
        sha1="a" * 40,
        project_url="https://www.curseforge.com/minecraft/mc-mods/example/files/2",
        reason="Manual download required",
        managed_kind="pack",
        managed_path="mods/example.jar",
    )

    error = CurseForgeManagedFilesRequired(_Instance(), (requirement,), "Files are missing")

    assert error.instance_name == "Test Instance"
    assert error.instance_dir == Path("instances/Test Instance")
    assert error.requirements == (requirement,)
    assert str(error) == "Files are missing"


def test_modpack_manual_download_exception_has_stable_module_and_legacy_reexport() -> None:
    from mcw_core.api.curseforge.curseforge_errors import CurseForgeModpackManualDownloadRequired as StableError
    from src.core.curseforge.curseforge_pack_installer import CurseForgeModpackManualDownloadRequired as LegacyError
    from src.models.curseforge.manual_download import CurseForgeManualDownload

    requirement = CurseForgeManualDownload(
        project_id=11,
        file_id=22,
        file_name="pack.zip",
        reason="manual download required",
        project_name="Pack",
        project_url="https://www.curseforge.com/minecraft/modpacks/pack/files/22",
        file_size=123,
        sha1="abc",
        managed_path="pack.zip",
        managed_kind="modpack_archive",
    )
    error = StableError(requirement, 11, 22, "Pack Instance", True, ("release",))

    assert LegacyError is StableError
    assert error.requirement is requirement
    assert error.project_id == 11
    assert error.file_id == 22
    assert error.instance_name == "Pack Instance"
    assert error.install_optional_files is True
    assert error.allowed_release_types == ("release",)
    assert error.expected_loader == ""

def test_gui_imports_curseforge_recovery_errors_from_stable_module() -> None:
    main_window = Path("src/gui/main_window.py").read_text(encoding="utf-8")
    controller = Path("src/gui/controllers/curseforge_controller.py").read_text(encoding="utf-8")

    assert "from mcw_core.api.curseforge.curseforge_errors import" in main_window
    assert "from src.core.curseforge.curseforge_pack_installer import CurseForgeModpackManualDownloadRequired" not in main_window
    assert "from mcw_core.api.curseforge.curseforge_errors import CurseForgeModpackManualDownloadRequired" in controller
