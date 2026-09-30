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


def test_detect_parses_linux_switcherooctl(monkeypatch: pytest.MonkeyPatch) -> None:
    switcheroo_output = """Device: 0
  Name: Intel Corporation Raptor Lake-P [Iris Xe Graphics]
  Default: yes
  Discrete: no
  Environment: DRI_PRIME=pci-0000_00_02_0

Device: 1
  Name: NVIDIA Corporation AD104GLM [RTX 3500 Ada Generation Laptop GPU]
  Default: no
  Discrete: yes
  Environment: __GLX_VENDOR_LIBRARY_NAME=nvidia __NV_PRIME_RENDER_OFFLOAD=1 __VK_LAYER_NV_optimus=NVIDIA_only
"""
    monkeypatch.setattr(GpuPreferenceManager, "_is_windows", staticmethod(lambda: False))
    monkeypatch.setattr(GpuPreferenceManager, "_is_linux", staticmethod(lambda: True))
    monkeypatch.setattr(
        "src.core.hardware.gpu_preference_manager.subprocess.run",
        lambda cmd, *args, **kwargs: SimpleNamespace(returncode=0, stdout=switcheroo_output, stderr="")
        if cmd == ["switcherooctl", "list"]
        else SimpleNamespace(returncode=1, stdout="", stderr=""),
    )

    result = GpuPreferenceManager.detect()

    assert result.supported is True
    assert len(result.adapters) == 2
    assert result.has_dedicated_gpu is True
    assert result.dedicated_adapters[0].name == "NVIDIA Corporation AD104GLM [RTX 3500 Ada Generation Laptop GPU]"
    env_dict = dict(result.dedicated_adapters[0].env_vars)
    assert env_dict["__NV_PRIME_RENDER_OFFLOAD"] == "1"
    assert env_dict["__GLX_VENDOR_LIBRARY_NAME"] == "nvidia"


def test_detect_parses_linux_lspci(monkeypatch: pytest.MonkeyPatch) -> None:
    lspci_output = """00:02.0 VGA compatible controller: Intel Corporation Alder Lake-P GT2 [Iris Xe Graphics] (rev 0c)
01:00.0 3D controller: NVIDIA Corporation GA106M [GeForce RTX 3060 Mobile / Max-Q] (rev a1)
"""
    monkeypatch.setattr(GpuPreferenceManager, "_is_windows", staticmethod(lambda: False))
    monkeypatch.setattr(GpuPreferenceManager, "_is_linux", staticmethod(lambda: True))
    monkeypatch.setattr(GpuPreferenceManager, "_detect_linux_switcheroo", classmethod(lambda cls: None))
    monkeypatch.setattr(
        "src.core.hardware.gpu_preference_manager.subprocess.run",
        lambda cmd, *args, **kwargs: SimpleNamespace(returncode=0, stdout=lspci_output, stderr="")
        if cmd == ["lspci"]
        else SimpleNamespace(returncode=1, stdout="", stderr=""),
    )

    result = GpuPreferenceManager.detect()

    assert result.supported is True
    assert len(result.adapters) == 2
    assert result.has_dedicated_gpu is True
    dedicated = result.dedicated_adapters[0]
    assert "GeForce RTX 3060" in dedicated.name
    env_dict = dict(dedicated.env_vars)
    assert env_dict["__NV_PRIME_RENDER_OFFLOAD"] == "1"
    assert env_dict["__GLX_VENDOR_LIBRARY_NAME"] == "nvidia"


def test_detect_parses_linux_sysfs(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeEntry:
        def __init__(self, name: str, pci_class: str, pci_vendor: str):
            self.name = name
            self._class = pci_class
            self._vendor = pci_vendor

        def __truediv__(self, child: str):
            val = self._class if child == "class" else self._vendor
            return SimpleNamespace(
                is_file=lambda: True,
                read_text=lambda *args, **kwargs: val,
            )

    entries = [
        FakeEntry("0000:00:02.0", "0x030000\n", "0x8086\n"),
        FakeEntry("0000:01:00.0", "0x030200\n", "0x10de\n"),
    ]

    fake_pci_dir = SimpleNamespace(
        is_dir=lambda: True,
        iterdir=lambda: entries,
    )

    monkeypatch.setattr(GpuPreferenceManager, "_is_windows", staticmethod(lambda: False))
    monkeypatch.setattr(GpuPreferenceManager, "_is_linux", staticmethod(lambda: True))
    monkeypatch.setattr(GpuPreferenceManager, "_detect_linux_switcheroo", classmethod(lambda cls: None))
    monkeypatch.setattr(GpuPreferenceManager, "_detect_linux_lspci", classmethod(lambda cls: None))
    monkeypatch.setattr(
        "src.core.hardware.gpu_preference_manager.Path",
        lambda path: fake_pci_dir if str(path) == "/sys/bus/pci/devices" else Path(path),
    )

    result = GpuPreferenceManager.detect()

    assert result.supported is True
    assert len(result.adapters) == 2
    assert result.has_dedicated_gpu is True
    assert result.dedicated_adapters[0].vendor == "NVIDIA"


def test_get_launch_environment_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GpuPreferenceManager, "_is_windows", staticmethod(lambda: False))
    monkeypatch.setattr(GpuPreferenceManager, "_is_linux", staticmethod(lambda: True))

    from src.core.hardware.gpu_preference_manager import GraphicsAdapter, GraphicsDetectionResult

    nvidia_adapter = GraphicsAdapter(
        name="NVIDIA RTX",
        vendor="NVIDIA",
        dedicated=True,
        env_vars=(("__NV_PRIME_RENDER_OFFLOAD", "1"), ("__GLX_VENDOR_LIBRARY_NAME", "nvidia")),
    )
    detection = GraphicsDetectionResult(supported=True, adapters=(nvidia_adapter,))

    base = {"USER": "testuser", "PATH": "/usr/bin"}
    env = GpuPreferenceManager.get_launch_environment(True, base_env=base, detection=detection)

    assert env is not None
    assert env["USER"] == "testuser"
    assert env["__NV_PRIME_RENDER_OFFLOAD"] == "1"
    assert env["__GLX_VENDOR_LIBRARY_NAME"] == "nvidia"

    # Disabled returns base
    disabled_env = GpuPreferenceManager.get_launch_environment(False, base_env=base, detection=detection)
    assert disabled_env == base


def test_apply_to_java_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GpuPreferenceManager, "_is_windows", staticmethod(lambda: False))
    monkeypatch.setattr(GpuPreferenceManager, "_is_linux", staticmethod(lambda: True))

    assert GpuPreferenceManager.apply_to_java("/usr/bin/java", True) is True
    assert GpuPreferenceManager.apply_to_java("/usr/bin/java", False) is True


def test_gpu_cache_read_write_and_force_refresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_file = tmp_path / "gpu_cache.json"
    call_count = 0

    def fake_detect_windows():
        nonlocal call_count
        call_count += 1
        from src.core.hardware.gpu_preference_manager import GraphicsAdapter, GraphicsDetectionResult

        adapter = GraphicsAdapter(name=f"Mock GPU {call_count}", vendor="MockCorp", dedicated=True)
        return GraphicsDetectionResult(supported=True, adapters=(adapter,))

    monkeypatch.setattr(GpuPreferenceManager, "_is_windows", staticmethod(lambda: True))
    monkeypatch.setattr(GpuPreferenceManager, "_detect_windows", fake_detect_windows)

    # First call: no cache exists, detection is called
    result1 = GpuPreferenceManager.detect(cache_path=cache_file)
    assert call_count == 1
    assert result1.adapters[0].name == "Mock GPU 1"
    assert cache_file.is_file()

    # Second call without force_refresh: returns cached result without running detection
    result2 = GpuPreferenceManager.detect(cache_path=cache_file)
    assert call_count == 1
    assert result2.adapters[0].name == "Mock GPU 1"

    # Third call with force_refresh=True: re-runs detection and updates cache
    result3 = GpuPreferenceManager.detect(force_refresh=True, cache_path=cache_file)
    assert call_count == 2
    assert result3.adapters[0].name == "Mock GPU 2"


def test_gpu_cache_handles_corrupt_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_file = tmp_path / "gpu_cache.json"
    cache_file.write_text("invalid json content", encoding="utf-8")

    monkeypatch.setattr(GpuPreferenceManager, "_is_windows", staticmethod(lambda: True))
    monkeypatch.setattr(
        GpuPreferenceManager,
        "_detect_windows",
        lambda: GpuPreferenceManager.GraphicsDetectionResult(supported=True, adapters=()) if hasattr(GpuPreferenceManager, "GraphicsDetectionResult") else SimpleNamespace(supported=True, adapters=(), error=""),
    )

    from src.core.hardware.gpu_preference_manager import GraphicsDetectionResult
    monkeypatch.setattr(
        GpuPreferenceManager,
        "_detect_windows",
        lambda: GraphicsDetectionResult(supported=True, adapters=()),
    )

    result = GpuPreferenceManager.detect(cache_path=cache_file)
    assert result.supported is True
    # Successfully recovered and rewrote valid cache
    assert cache_file.is_file()
    assert "version" in cache_file.read_text(encoding="utf-8")

