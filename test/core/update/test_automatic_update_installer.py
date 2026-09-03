from types import SimpleNamespace

import pytest

from src.core.update.automatic_update_installer import AutomaticUpdateInstaller
from src.core.update.linux_update_installer import LinuxUpdateInstaller
from src.core.update.windows_update_installer import WindowsUpdateInstaller


@pytest.mark.parametrize(
    ("os_name", "architecture", "expected"),
    [
        ("windows", "x64", WindowsUpdateInstaller),
        ("linux", "x64", LinuxUpdateInstaller),
        ("linux", "arm64", None),
        ("mac", "x64", None),
    ],
)
def test_routes_only_supported_release_platforms(monkeypatch, os_name, architecture, expected) -> None:
    monkeypatch.setattr(
        "src.core.update.automatic_update_installer.PlatformInfo.current",
        lambda: SimpleNamespace(os_name=os_name, architecture=architecture),
    )

    assert AutomaticUpdateInstaller._installer() is expected
