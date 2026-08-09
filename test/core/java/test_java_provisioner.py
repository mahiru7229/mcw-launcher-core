from pathlib import Path

import pytest

from src.core.java.java_manager import JavaManager
from src.core.java.java_provisioner import JavaProvisioner
from src.core.java.managed_java_repository import ManagedJavaRepository
from src.models.java.java import JavaInstallation
from src.models.java.java_release import JavaRelease
from src.models.java.java_source import JavaSource


def test_ensure_reuses_exact_system_java(monkeypatch: pytest.MonkeyPatch):
    system_java = Path("C:/Java17/bin/javaw.exe")
    monkeypatch.setattr(ManagedJavaRepository, "executable", lambda major: Path("missing/javaw.exe"))
    monkeypatch.setattr(JavaManager, "find_installation", lambda: [JavaInstallation(version=17, executable=system_java, source=JavaSource.PATH)])
    monkeypatch.setattr(JavaProvisioner, "_download_and_install", classmethod(lambda cls, major, reporter: (_ for _ in ()).throw(AssertionError("download should not run"))))

    assert JavaProvisioner.ensure(17) == system_java


def test_install_managed_installs_even_when_system_java_exists(monkeypatch: pytest.MonkeyPatch):
    managed = Path("runtimes/java-21/bin/javaw.exe")
    system_java = Path("C:/Java21/bin/javaw.exe")
    monkeypatch.setattr(ManagedJavaRepository, "executable", lambda major: Path("missing/javaw.exe"))
    monkeypatch.setattr(JavaManager, "find_installation", lambda: [JavaInstallation(version=21, executable=system_java, source=JavaSource.PATH)])
    calls = []

    def install(cls, major, reporter):
        calls.append(major)
        return managed

    monkeypatch.setattr(JavaProvisioner, "_download_and_install", classmethod(install))

    assert JavaProvisioner.install_managed(21) == managed
    assert calls == [21]


def test_failed_reinstall_restores_previous_managed_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    runtime_root = tmp_path / "runtimes"
    target = runtime_root / "java-17"
    old_java = target / "bin" / "javaw.exe"
    old_java.parent.mkdir(parents=True)
    old_java.write_bytes(b"old")
    archive = tmp_path / "java.zip"
    archive.write_bytes(b"archive")
    release = JavaRelease(major=17, url="https://example.test/java.zip", sha256="0" * 64, size=7, filename="java.zip", release_name="test")

    monkeypatch.setattr(ManagedJavaRepository, "root", lambda: runtime_root)
    monkeypatch.setattr(ManagedJavaRepository, "runtime_dir", lambda major: target)

    def extract(_archive, staging):
        java_home = staging / "jdk"
        java_home.mkdir(parents=True)
        return java_home

    monkeypatch.setattr("src.core.java.java_provisioner.JavaArchiveExtractor.extract", extract)

    with pytest.raises(RuntimeError, match="without javaw.exe"):
        JavaProvisioner._install_release(release, archive)

    assert old_java.read_bytes() == b"old"


def test_install_managed_accepts_exact_latest_feature_release(monkeypatch: pytest.MonkeyPatch):
    managed = Path("runtimes/java-26/bin/javaw.exe")
    calls = []
    monkeypatch.setattr(ManagedJavaRepository, "executable", lambda major: Path("missing/javaw.exe"))

    def install(cls, major, reporter):
        calls.append(major)
        return managed

    monkeypatch.setattr(JavaProvisioner, "_download_and_install", classmethod(install))

    assert JavaProvisioner.install_managed(26) == managed
    assert calls == [26]


def test_install_release_extracts_in_short_jvm_workspace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from src.core.fs.paths import Paths

    runtime_root = tmp_path / ("very-long-launcher-root-" * 8) / "runtimes"
    target = runtime_root / "java-8"
    short_root = tmp_path / "short"
    archive = tmp_path / "java.zip"
    archive.write_bytes(b"archive")
    release = JavaRelease(major=8, url="https://example.test/java.zip", sha256="0" * 64, size=7, filename="java.zip", release_name="test")
    captured: dict[str, Path] = {}

    monkeypatch.setattr(Paths, "SHORT_WORKSPACE_ROOT", short_root)
    monkeypatch.setattr(ManagedJavaRepository, "root", lambda: runtime_root)
    monkeypatch.setattr(ManagedJavaRepository, "runtime_dir", lambda major: target)

    def extract(_archive, staging):
        captured["staging"] = staging
        java_home = staging / "jdk8u502-b07"
        executable = java_home / "bin" / "javaw.exe"
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b"java")
        return java_home

    monkeypatch.setattr("src.core.java.java_provisioner.JavaArchiveExtractor.extract", extract)

    executable = JavaProvisioner._install_release(release, archive)

    assert captured["staging"].parent == short_root / "jvm"
    assert len(str(captured["staging"])) < len(str(runtime_root / ".java-8.installing-" / ("x" * 32)))
    assert executable == target / "bin" / "javaw.exe"
    assert executable.is_file()
    assert not captured["staging"].exists()
