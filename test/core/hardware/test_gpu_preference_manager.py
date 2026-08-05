from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.hardware.gpu_preference_manager import GpuPreferenceManager


def test_dedicated_gpu_classification_is_conservative() -> None:
    assert GpuPreferenceManager._looks_dedicated("NVIDIA GeForce RTX 4060 Laptop GPU", "NVIDIA", 8 * 1024**3)
    assert GpuPreferenceManager._looks_dedicated("AMD Radeon RX 7800 XT", "Advanced Micro Devices", 16 * 1024**3)
    assert GpuPreferenceManager._looks_dedicated("Intel(R) Arc(TM) A770 Graphics", "Intel Corporation", 16 * 1024**3)
    assert not GpuPreferenceManager._looks_dedicated("Intel(R) Iris(R) Xe Graphics", "Intel Corporation", 8 * 1024**3)
    assert not GpuPreferenceManager._looks_dedicated("AMD Radeon(TM) Graphics", "Advanced Micro Devices", 8 * 1024**3)


def test_detect_parses_windows_video_controllers(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = [
        {
            "Name": "Intel(R) UHD Graphics 770",
            "AdapterCompatibility": "Intel Corporation",
            "AdapterRAM": 1024,
            "PNPDeviceID": "PCI\\VEN_8086",
            "Status": "OK",
        },
        {
            "Name": "NVIDIA GeForce RTX 4070",
            "AdapterCompatibility": "NVIDIA",
            "AdapterRAM": 12 * 1024**3,
            "PNPDeviceID": "PCI\\VEN_10DE",
            "Status": "OK",
        },
    ]
    monkeypatch.setattr(GpuPreferenceManager, "_is_windows", staticmethod(lambda: True))
    monkeypatch.setattr(
        "src.core.hardware.gpu_preference_manager.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr=""),
    )

    result = GpuPreferenceManager.detect()

    assert result.supported is True
    assert [adapter.name for adapter in result.adapters] == ["Intel(R) UHD Graphics 770", "NVIDIA GeForce RTX 4070"]
    assert [adapter.name for adapter in result.dedicated_adapters] == ["NVIDIA GeForce RTX 4070"]


def test_detect_reports_powershell_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GpuPreferenceManager, "_is_windows", staticmethod(lambda: True))
    monkeypatch.setattr(
        "src.core.hardware.gpu_preference_manager.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="CIM unavailable"),
    )

    result = GpuPreferenceManager.detect()

    assert result.supported is True
    assert result.adapters == ()
    assert result.error == "CIM unavailable"


def test_apply_for_executable_writes_high_performance_preference(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    values: dict[str, str] = {}

    class FakeKey:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_winreg = SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        KEY_SET_VALUE=1,
        REG_SZ=1,
        CreateKeyEx=lambda *args, **kwargs: FakeKey(),
        SetValueEx=lambda key, name, reserved, value_type, value: values.__setitem__(name, value),
        DeleteValue=lambda key, name: values.pop(name, None),
    )
    monkeypatch.setattr(GpuPreferenceManager, "_is_windows", staticmethod(lambda: True))
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg)
    java = tmp_path / "javaw.exe"

    assert GpuPreferenceManager.apply_for_executable(java, True) is True
    assert list(values.values()) == [GpuPreferenceManager.HIGH_PERFORMANCE_VALUE]
