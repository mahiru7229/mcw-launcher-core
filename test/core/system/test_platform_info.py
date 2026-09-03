from __future__ import annotations

import pytest

from src.core.system.platform_info import PlatformInfo


@pytest.mark.parametrize(
    ("system", "machine", "os_name", "architecture", "adoptium", "java", "suffix"),
    [
        ("Windows", "AMD64", "windows", "x64", "x64", "javaw.exe", ".zip"),
        ("Linux", "x86_64", "linux", "x64", "x64", "java", ".tar.gz"),
        ("Linux", "aarch64", "linux", "arm64", "aarch64", "java", ".tar.gz"),
    ],
)
def test_current_platform_profile(
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    machine: str,
    os_name: str,
    architecture: str,
    adoptium: str,
    java: str,
    suffix: str,
) -> None:
    monkeypatch.setattr("src.core.system.platform_info.platform.system", lambda: system)
    monkeypatch.setattr("src.core.system.platform_info.platform.machine", lambda: machine)

    profile = PlatformInfo.current()

    assert profile.os_name == os_name
    assert profile.architecture == architecture
    assert profile.adoptium_architecture == adoptium
    assert profile.java_executable == java
    assert profile.archive_suffix == suffix
    assert PlatformInfo.is_windows() is (os_name == "windows")


def test_linux_x64_supports_managed_java(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.core.system.platform_info.platform.system", lambda: "Linux")
    monkeypatch.setattr("src.core.system.platform_info.platform.machine", lambda: "x86_64")

    assert PlatformInfo.supports_managed_java() is True


def test_empty_system_name_uses_normalized_sys_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.core.system.platform_info.platform.system", lambda: "")
    monkeypatch.setattr("src.core.system.platform_info.platform.machine", lambda: "AMD64")
    monkeypatch.setattr("src.core.system.platform_info.sys.platform", "win32")

    profile = PlatformInfo.current()

    assert profile.os_name == "windows"
    assert profile.java_executable == "javaw.exe"
    assert profile.archive_suffix == ".zip"
