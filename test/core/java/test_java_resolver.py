from pathlib import Path

import pytest

from src.core.java.java_provisioner import JavaProvisioner
from src.core.java.java_resolver import JavaResolver
from src.core.java.java_selector import JavaSelector


def test_resolve_returns_selected_java_without_provisioning(monkeypatch: pytest.MonkeyPatch):
    selected = Path("java21/javaw.exe")
    provision_calls = []

    monkeypatch.setattr(JavaSelector, "select_java", lambda major: selected)
    monkeypatch.setattr(JavaProvisioner, "install_managed", lambda major, reporter=None, force=False: provision_calls.append((major, reporter, force)))

    result = JavaResolver.resolve(21)

    assert result == selected
    assert provision_calls == []


def test_resolve_provisions_java_when_selection_fails(monkeypatch: pytest.MonkeyPatch):
    installed = Path("runtimes/java-25/bin/javaw.exe")
    reporter = object()
    calls = []

    def fail_selection(major):
        calls.append(("select", major))
        raise RuntimeError("Java 21 was not found.")

    def provision(major, received_reporter=None):
        calls.append(("provision", major, received_reporter))
        return installed

    monkeypatch.setattr(JavaSelector, "select_java", fail_selection)
    monkeypatch.setattr(JavaProvisioner, "install_managed", lambda major, received_reporter=None, force=False: provision(major, received_reporter))

    result = JavaResolver.resolve(21, reporter)

    assert result == installed
    assert calls == [("select", 21), ("provision", 21, reporter)]


def test_resolve_maps_java_16_requirement_to_java_17(monkeypatch: pytest.MonkeyPatch):
    selected = Path("java17/javaw.exe")
    calls = []

    def select(major):
        calls.append(major)
        return selected

    monkeypatch.setattr(JavaSelector, "select_java", select)

    assert JavaResolver.resolve(16) == selected
    assert calls == [17]


def test_resolve_does_not_use_java_25_for_java_17_requirement(monkeypatch: pytest.MonkeyPatch):
    installed = Path("runtimes/java-17/bin/javaw.exe")
    calls = []

    def fail_selection(major):
        calls.append(("select", major))
        raise RuntimeError("Java 17 was not found.")

    def provision(major, reporter=None):
        calls.append(("provision", major))
        return installed

    monkeypatch.setattr(JavaSelector, "select_java", fail_selection)
    monkeypatch.setattr(JavaProvisioner, "install_managed", lambda major, reporter=None, force=False: provision(major, reporter))

    assert JavaResolver.resolve(17) == installed
    assert calls == [("select", 17), ("provision", 17)]


def test_resolve_accepts_compatible_preferred_java(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    java = tmp_path / "jdk-17" / "bin" / "javaw.exe"
    java.parent.mkdir(parents=True)
    java.write_bytes(b"")
    monkeypatch.setattr("src.core.java.java_resolver.JavaManager.get_major_version", lambda path: 17)

    assert JavaResolver.resolve(17, preferred_path=java) == java


def test_resolve_rejects_preferred_java_25_for_java_17(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    java = tmp_path / "jdk-25" / "bin" / "javaw.exe"
    java.parent.mkdir(parents=True)
    java.write_bytes(b"")
    monkeypatch.setattr("src.core.java.java_resolver.JavaManager.get_major_version", lambda path: 25)

    with pytest.raises(RuntimeError, match="Java 25 is incompatible.*Required: Java 17"):
        JavaResolver.resolve(17, preferred_path=java)


def test_resolve_accepts_raw_java_16_for_java_16_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    java = tmp_path / "jdk-16" / "bin" / "javaw.exe"
    java.parent.mkdir(parents=True)
    java.write_bytes(b"")
    monkeypatch.setattr("src.core.java.java_resolver.JavaManager.get_major_version", lambda path: 16)

    assert JavaResolver.resolve(16, preferred_path=java) == java


def test_resolve_with_recovery_falls_back_from_invalid_preferred_java(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    preferred = tmp_path / "missing" / "javaw.exe"
    fallback = tmp_path / "managed" / "bin" / "javaw.exe"
    fallback.parent.mkdir(parents=True)
    fallback.write_bytes(b"")
    monkeypatch.setattr(JavaResolver, "resolve_alternative", lambda required, excluded, reporter=None: fallback)

    result = JavaResolver.resolve_with_recovery(17, preferred_path=preferred)

    assert result.path == fallback
    assert result.automatic is True
    assert result.recovered is True
    assert result.rejected_path == preferred
    assert "does not exist" in result.recovery_reason


def test_resolve_with_recovery_reports_when_both_paths_fail(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    preferred = tmp_path / "missing" / "javaw.exe"

    def fail_recovery(required, excluded, reporter=None):
        raise RuntimeError("download unavailable")

    monkeypatch.setattr(JavaResolver, "resolve_alternative", fail_recovery)

    with pytest.raises(RuntimeError, match="automatic Java recovery also failed"):
        JavaResolver.resolve_with_recovery(17, preferred_path=preferred)


def test_automatic_java8_provisions_managed_runtime_instead_of_old_path_java(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    old_java = tmp_path / "external-jre8" / "bin" / "javaw.exe"
    old_java.parent.mkdir(parents=True)
    old_java.write_bytes(b"old")
    managed = tmp_path / "managed" / "java-8" / "bin" / "javaw.exe"
    managed.parent.mkdir(parents=True)
    managed.write_bytes(b"managed")
    calls = []

    monkeypatch.setattr("src.core.java.java_resolver.ManagedJavaRepository.executable", lambda major: tmp_path / "missing" / "javaw.exe")
    monkeypatch.setattr(JavaSelector, "select_java", lambda major: old_java)
    monkeypatch.setattr(JavaProvisioner, "install_managed", lambda major, reporter=None, force=False: calls.append((major, force)) or managed)

    assert JavaResolver.resolve(8) == managed
    assert calls == [(8, False)]


def test_explicit_java8_is_still_honored(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    explicit = tmp_path / "explicit-jre8" / "bin" / "javaw.exe"
    explicit.parent.mkdir(parents=True)
    explicit.write_bytes(b"java")
    monkeypatch.setattr("src.core.java.java_resolver.JavaManager.get_major_version", lambda path: 8)
    monkeypatch.setattr(JavaProvisioner, "install_managed", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("explicit Java must not provision")))

    assert JavaResolver.resolve(8, preferred_path=explicit) == explicit


def test_recovery_provisions_managed_before_external_candidate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    failed = tmp_path / "broken" / "javaw.exe"
    managed = tmp_path / "runtime" / "java-8" / "bin" / "javaw.exe"
    managed.parent.mkdir(parents=True)
    managed.write_bytes(b"managed")
    missing_managed = tmp_path / "missing" / "javaw.exe"
    calls = []

    monkeypatch.setattr("src.core.java.java_resolver.ManagedJavaRepository.executable", lambda major: missing_managed)
    monkeypatch.setattr(JavaProvisioner, "install_managed", lambda major, reporter=None, force=False: calls.append("managed") or managed)
    monkeypatch.setattr(JavaSelector, "select_automatic_java", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("external fallback should come after managed provisioning")))
    monkeypatch.setattr("src.core.java.java_resolver.JavaManager.get_major_version", lambda path: 8)

    assert JavaResolver.resolve_alternative(8, {failed}) == managed
    assert calls == ["managed"]


def test_automatic_java8_falls_back_to_modern_external_when_managed_download_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    modern = tmp_path / "modern-jre8" / "bin" / "javaw.exe"
    modern.parent.mkdir(parents=True)
    modern.write_bytes(b"modern")
    monkeypatch.setattr("src.core.java.java_resolver.ManagedJavaRepository.executable", lambda major: tmp_path / "missing" / "javaw.exe")
    monkeypatch.setattr(JavaProvisioner, "install_managed", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setattr(JavaSelector, "select_automatic_java", lambda major, excluded_paths=(): modern)

    assert JavaResolver.resolve(8) == modern
