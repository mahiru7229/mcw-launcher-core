from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True, slots=True)
class GraphicsAdapter:
    name: str
    vendor: str = ""
    adapter_ram: int = 0
    pnp_device_id: str = ""
    dedicated: bool = False


@dataclass(frozen=True, slots=True)
class GraphicsDetectionResult:
    supported: bool
    adapters: tuple[GraphicsAdapter, ...] = ()
    error: str = ""

    @property
    def dedicated_adapters(self) -> tuple[GraphicsAdapter, ...]:
        return tuple(adapter for adapter in self.adapters if adapter.dedicated)

    @property
    def has_dedicated_gpu(self) -> bool:
        return bool(self.dedicated_adapters)


class GpuPreferenceManager:
    """Best-effort Windows graphics preference integration.

    Windows owns the final adapter selection.  MCW records the per-executable
    high-performance preference for the selected Java runtime and never blocks a
    launch when Windows or a display driver refuses the preference.
    """

    REGISTRY_PATH = r"Software\Microsoft\DirectX\UserGpuPreferences"
    HIGH_PERFORMANCE_VALUE = "GpuPreference=2;"
    DETECTION_TIMEOUT_SECONDS = 8

    _SOFTWARE_TOKENS = (
        "microsoft basic display",
        "microsoft remote display",
        "remote display adapter",
        "virtualbox",
        "vmware",
        "parallels",
    )
    _INTEGRATED_TOKENS = (
        "intel(r) hd graphics",
        "intel(r) uhd graphics",
        "intel(r) iris",
        "intel hd graphics",
        "intel uhd graphics",
        "intel iris",
        "radeon(tm) graphics",
        "radeon graphics",
        "vega 3 graphics",
        "vega 6 graphics",
        "vega 7 graphics",
        "vega 8 graphics",
        "vega 10 graphics",
        "vega 11 graphics",
    )
    _DEDICATED_PATTERNS = (
        re.compile(r"\bnvidia\b", re.IGNORECASE),
        re.compile(r"\bgeforce\b", re.IGNORECASE),
        re.compile(r"\bquadro\b", re.IGNORECASE),
        re.compile(r"\brtx\s*[a-z]?\d", re.IGNORECASE),
        re.compile(r"\bgtx\s*\d", re.IGNORECASE),
        re.compile(r"\bradeon\s+(?:rx|r9|r7|r5|pro\s+w|pro\s+v|firepro)\b", re.IGNORECASE),
        re.compile(r"\bintel(?:\(r\))?\s+arc(?:\(tm\))?\s+[ab]\d{3}\b", re.IGNORECASE),
    )

    @classmethod
    def detect(cls) -> GraphicsDetectionResult:
        if not cls._is_windows():
            return GraphicsDetectionResult(supported=False)

        command = (
            "Get-CimInstance Win32_VideoController | "
            "Select-Object Name,AdapterCompatibility,AdapterRAM,PNPDeviceID,Status | "
            "ConvertTo-Json -Compress"
        )
        creation_flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command],
                capture_output=True,
                text=True,
                timeout=cls.DETECTION_TIMEOUT_SECONDS,
                check=False,
                creationflags=creation_flags,
            )
        except (OSError, subprocess.SubprocessError) as error:
            return GraphicsDetectionResult(supported=True, error=str(error))

        if completed.returncode != 0:
            error = (completed.stderr or completed.stdout or "GPU detection failed").strip()
            return GraphicsDetectionResult(supported=True, error=error)

        try:
            payload = json.loads(completed.stdout or "[]")
        except json.JSONDecodeError as error:
            return GraphicsDetectionResult(supported=True, error=str(error))

        records = payload if isinstance(payload, list) else [payload]
        adapters: list[GraphicsAdapter] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            name = str(record.get("Name") or "").strip()
            if not name or cls._is_software_adapter(name):
                continue
            vendor = str(record.get("AdapterCompatibility") or "").strip()
            pnp_device_id = str(record.get("PNPDeviceID") or "").strip()
            adapter_ram = cls._non_negative_int(record.get("AdapterRAM"))
            adapters.append(
                GraphicsAdapter(
                    name=name,
                    vendor=vendor,
                    adapter_ram=adapter_ram,
                    pnp_device_id=pnp_device_id,
                    dedicated=cls._looks_dedicated(name, vendor, adapter_ram),
                )
            )
        return GraphicsDetectionResult(supported=True, adapters=tuple(adapters))

    @classmethod
    def apply_for_executable(cls, executable: Path | str, enabled: bool) -> bool:
        if not cls._is_windows():
            return False
        path = Path(executable).expanduser()
        try:
            normalized = str(path.resolve(strict=False))
        except OSError:
            normalized = str(path.absolute())
        if not normalized:
            return False

        try:
            import winreg

            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, cls.REGISTRY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                if enabled:
                    winreg.SetValueEx(key, normalized, 0, winreg.REG_SZ, cls.HIGH_PERFORMANCE_VALUE)
                else:
                    try:
                        winreg.DeleteValue(key, normalized)
                    except FileNotFoundError:
                        pass
            return True
        except (OSError, ImportError):
            return False

    @classmethod
    def apply_to_java(cls, java_path: Path | str, enabled: bool) -> bool:
        if not cls._is_windows():
            return False
        path = Path(java_path)
        candidates = [path]
        if path.name.casefold() == "java.exe":
            candidates.insert(0, path.with_name("javaw.exe"))
        elif path.name.casefold() == "javaw.exe":
            candidates.append(path.with_name("java.exe"))

        applied = False
        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate).casefold()
            if key in seen:
                continue
            seen.add(key)
            if candidate == path or candidate.is_file():
                applied = cls.apply_for_executable(candidate, enabled) or applied
        return applied

    @classmethod
    def adapter_summary(cls, adapters: Iterable[GraphicsAdapter]) -> str:
        names = [adapter.name for adapter in adapters if adapter.name]
        return ", ".join(names)


    @staticmethod
    def _is_windows() -> bool:
        return os.name == "nt" and sys.platform == "win32"

    @classmethod
    def _looks_dedicated(cls, name: str, vendor: str, adapter_ram: int) -> bool:
        combined = f"{vendor} {name}".strip()
        lowered = combined.casefold()
        if any(token in lowered for token in cls._INTEGRATED_TOKENS):
            return False
        if any(pattern.search(combined) for pattern in cls._DEDICATED_PATTERNS):
            return True
        # Keep detection conservative. A large reported adapter memory alone is
        # not sufficient because several iGPUs expose shared system memory here.
        return False

    @classmethod
    def _is_software_adapter(cls, name: str) -> bool:
        lowered = name.casefold()
        return any(token in lowered for token in cls._SOFTWARE_TOKENS)

    @staticmethod
    def _non_negative_int(value: object) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError, OverflowError):
            return 0
