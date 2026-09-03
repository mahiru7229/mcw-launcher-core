from pathlib import Path

from src.core.fs.paths import Paths


def test_short_workspace_uses_readable_three_character_prefix(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "short"
    monkeypatch.setattr(Paths, "SHORT_WORKSPACE_ROOT", root)

    workspace = Paths.create_short_workspace("jvm")

    assert workspace.parent == root / "jvm"
    assert len(workspace.name) == 8
    assert workspace.is_dir()

    Paths.cleanup_short_workspace(workspace)
    assert not workspace.exists()


def test_loader_and_modrinth_staging_use_short_workspace_root(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "short"
    monkeypatch.setattr(Paths, "SHORT_WORKSPACE_ROOT", root)
    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / ("very-long-launcher-root-" * 8) / "cache")

    forge = Paths.forge_staging_dir("1.20.1", "47.4.21")
    neoforge = Paths.neoforge_staging_dir("1.21.1", "21.1.200")
    modrinth = Paths.modrinth_staging_root()

    assert forge.parent == root / "frg"
    assert neoforge.parent == root / "neo"
    assert modrinth == root / "mrd"
    assert len(str(forge)) < len(str(Paths.CACHE_ROOT / "modloaders" / "forge" / "staging" / "1.20.1-47.4.21"))


def test_diagnostic_long_paths_fit_inside_short_workspace() -> None:
    long_root = Path(r"C:\Users\Administrator\Downloads\MCW-Launcher-v1.3.0-windows-x64\MCW-Launcher-v1.3.0-windows-x64")
    short_root = Path(r"C:\Users\Administrator\AppData\Local\MCW\t")
    java_relative = Path(r"jdk8u502-b07\sample\jmx\jmx-scandir\src\com\sun\jmx\examples\scandir\config\DirectoryScannerConfig.java")
    modrinth_relative = Path(r"config\modpack_defaults\config\crash_assistant\crash_assistant_localization_overrides\zlm_arab.json")

    old_java = long_root / "runtimes" / (".java-8.installing-" + "3" * 32) / java_relative
    new_java = short_root / "jvm" / "a31f42c0" / java_relative
    old_modrinth = long_root / "cache" / "content" / "modrinth" / "staging" / ("b" * 32) / modrinth_relative
    new_modrinth = short_root / "mrd" / "b0f92b34" / modrinth_relative

    assert len(str(old_java)) >= 260
    assert len(str(old_modrinth)) >= 260
    assert len(str(new_java)) < 260
    assert len(str(new_modrinth)) < 260


def test_cleanup_short_workspace_rejects_parent_escape(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "short"
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("keep", encoding="utf-8")
    monkeypatch.setattr(Paths, "SHORT_WORKSPACE_ROOT", root)

    escaped = root / "jvm" / ".." / ".." / "victim"
    try:
        Paths.cleanup_short_workspace(escaped)
    except ValueError:
        pass
    else:
        raise AssertionError("cleanup_short_workspace accepted a path that resolves outside the short workspace root")

    assert (victim / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_cleanup_short_workspace_rejects_root_itself(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "short"
    root.mkdir()
    (root / "keep.txt").write_text("keep", encoding="utf-8")
    monkeypatch.setattr(Paths, "SHORT_WORKSPACE_ROOT", root)

    try:
        Paths.cleanup_short_workspace(root)
    except ValueError:
        pass
    else:
        raise AssertionError("cleanup_short_workspace accepted the short workspace root itself")

    assert (root / "keep.txt").is_file()
