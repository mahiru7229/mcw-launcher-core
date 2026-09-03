from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.java.java_manager import JavaManager
from src.core.java.java_selector import JavaSelector
from src.models.java.java import JavaInstallation
from src.models.java.java_source import JavaSource


def make_java(
    version: int,
    executable_name: str
) -> JavaInstallation:
    return JavaInstallation(
        version=version,
        executable=Path(executable_name),
        source=JavaSource.PATH
    )


def test_select_java_prefers_exact_version(
    monkeypatch: pytest.MonkeyPatch
):
    java_8 = make_java(8, "java8/javaw.exe")
    java_17 = make_java(17, "java17/javaw.exe")
    java_21 = make_java(21, "java21/javaw.exe")

    monkeypatch.setattr(
        JavaManager,
        "find_installation",
        lambda: [java_21, java_8, java_17]
    )

    selected = JavaSelector.select_java(
        required_major=17
    )

    assert selected == java_17.executable


def test_select_java_chooses_nearest_higher_version(
    monkeypatch: pytest.MonkeyPatch
):
    java_17 = make_java(17, "java17/javaw.exe")
    java_21 = make_java(21, "java21/javaw.exe")
    java_25 = make_java(25, "java25/javaw.exe")

    monkeypatch.setattr(
        JavaManager,
        "find_installation",
        lambda: [java_25, java_21, java_17]
    )

    selected = JavaSelector.select_java(
        required_major=18,
        allow_higher=True
    )

    assert selected == java_21.executable


def test_select_java_does_not_use_lower_version(
    monkeypatch: pytest.MonkeyPatch
):
    java_8 = make_java(8, "java8/javaw.exe")
    java_17 = make_java(17, "java17/javaw.exe")

    monkeypatch.setattr(
        JavaManager,
        "find_installation",
        lambda: [java_8, java_17]
    )

    with pytest.raises(
        RuntimeError,
        match="Java 21 was not found"
    ):
        JavaSelector.select_java(
            required_major=21
        )


def test_select_java_rejects_higher_when_disabled(
    monkeypatch: pytest.MonkeyPatch
):
    java_17 = make_java(17, "java17/javaw.exe")
    java_21 = make_java(21, "java21/javaw.exe")

    monkeypatch.setattr(
        JavaManager,
        "find_installation",
        lambda: [java_17, java_21]
    )

    with pytest.raises(
        RuntimeError,
        match="Java 18 was not found"
    ):
        JavaSelector.select_java(
            required_major=18,
            allow_higher=False
        )


def test_select_java_raises_when_no_java_found(
    monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        JavaManager,
        "find_installation",
        lambda: []
    )

    with pytest.raises(
        RuntimeError,
        match="No Java found"
    ):
        JavaSelector.select_java(
            required_major=17
        )


def test_select_latest_java_returns_highest_version(
    monkeypatch: pytest.MonkeyPatch
):
    java_8 = make_java(8, "java8/javaw.exe")
    java_17 = make_java(17, "java17/javaw.exe")
    java_25 = make_java(25, "java25/javaw.exe")

    monkeypatch.setattr(
        JavaManager,
        "find_installation",
        lambda: [java_17, java_25, java_8]
    )

    selected = JavaSelector.select_latest_java()

    assert selected == java_25.executable


def test_select_latest_java_raises_when_no_java_found(
    monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        JavaManager,
        "find_installation",
        lambda: []
    )

    with pytest.raises(
        RuntimeError,
        match="No Java found"
    ):
        JavaSelector.select_latest_java()

def test_select_java_does_not_promote_java_17_to_java_25_by_default(monkeypatch: pytest.MonkeyPatch):
    java_25 = make_java(25, "java25/javaw.exe")
    monkeypatch.setattr(JavaManager, "find_installation", lambda: [java_25])

    with pytest.raises(RuntimeError, match="Java 17 was not found"):
        JavaSelector.select_java(17)


def test_select_java_excluding_uses_another_same_major_runtime(monkeypatch: pytest.MonkeyPatch):
    first = make_java(17, "java-a/javaw.exe")
    second = JavaInstallation(version=17, executable=Path("java-b/javaw.exe"), source=JavaSource.MINECRAFT_RUNTIME)
    monkeypatch.setattr(JavaManager, "find_installation_candidates", lambda: [first, second])

    selected = JavaSelector.select_java_excluding(17, {first.executable})

    assert selected == second.executable


def test_select_java_prefers_managed_source_even_when_returned_later(monkeypatch: pytest.MonkeyPatch):
    external = JavaInstallation(version=8, executable=Path("external/javaw.exe"), source=JavaSource.PATH)
    managed = JavaInstallation(version=8, executable=Path("managed/javaw.exe"), source=JavaSource.MINECRAFT_RUNTIME)
    monkeypatch.setattr(JavaManager, "find_installation", lambda: [external, managed])

    assert JavaSelector.select_java(8) == managed.executable


def test_automatic_java8_skips_legacy_external_runtime(monkeypatch: pytest.MonkeyPatch):
    old = JavaInstallation(version=8, executable=Path("old/javaw.exe"), source=JavaSource.PATH)
    modern = JavaInstallation(version=8, executable=Path("modern/javaw.exe"), source=JavaSource.PROGRAM_FILES)
    monkeypatch.setattr(JavaManager, "find_installation_candidates", lambda: [old, modern])

    from src.core.java.java_diagnostics_manager import JavaDiagnosticsManager
    monkeypatch.setattr(
        JavaDiagnosticsManager,
        "inspect",
        lambda java: SimpleNamespace(valid=True, version_string="1.8.0_51" if java is old else "1.8.0_492"),
    )

    assert JavaSelector.select_automatic_java(8) == modern.executable


def test_automatic_java8_rejects_only_legacy_external_runtime(monkeypatch: pytest.MonkeyPatch):
    old = JavaInstallation(version=8, executable=Path("old/javaw.exe"), source=JavaSource.PATH)
    monkeypatch.setattr(JavaManager, "find_installation_candidates", lambda: [old])
    from src.core.java.java_diagnostics_manager import JavaDiagnosticsManager
    monkeypatch.setattr(JavaDiagnosticsManager, "inspect", lambda java: SimpleNamespace(valid=True, version_string="1.8.0_51"))

    with pytest.raises(RuntimeError, match="No suitable automatic Java 8"):
        JavaSelector.select_automatic_java(8)
