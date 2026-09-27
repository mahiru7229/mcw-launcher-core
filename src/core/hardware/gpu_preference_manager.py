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
    env_vars: tuple[tuple[str, str], ...] = ()


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

    _cache_enabled: bool = True
    _default_cache_path: Path | None = None

    @classmethod
    def _should_use_default_cache(cls) -> bool:
        if not cls._cache_enabled:
            return False
        if "pytest" in sys.modules:
            return False
        return True

    @classmethod
    def _get_cache_path(cls) -> Path | None:
        if cls._default_cache_path is not None:
            return cls._default_cache_path
        try:
            from mcw_core.api.fs.paths import Paths

            cls._default_cache_path = Paths.CACHE_ROOT / "hardware" / "gpu_cache.json"
            return cls._default_cache_path
        except Exception:
            return None

    @classmethod
    def _read_cache(cls, cache_path: Path | None = None) -> GraphicsDetectionResult | None:
        target = cache_path if cache_path is not None else (cls._get_cache_path() if cls._should_use_default_cache() else None)
        if target is None or not target.is_file():
            return None
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or int(data.get("version", 0)) != 1:
                return None
            supported = bool(data.get("supported", False))
            error = str(data.get("error", ""))
            raw_adapters = data.get("adapters", [])
            if not isinstance(raw_adapters, list):
                return None
            adapters: list[GraphicsAdapter] = []
            for item in raw_adapters:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                vendor = str(item.get("vendor", "")).strip()
                adapter_ram = cls._non_negative_int(item.get("adapter_ram"))
                pnp_device_id = str(item.get("pnp_device_id", "")).strip()
                dedicated = bool(item.get("dedicated", False))
                raw_env = item.get("env_vars", [])
                env_vars: tuple[tuple[str, str], ...] = ()
                if isinstance(raw_env, (list, tuple)):
                    env_vars = tuple(
                        (str(pair[0]), str(pair[1]))
                        for pair in raw_env
                        if isinstance(pair, (list, tuple)) and len(pair) == 2
                    )
                adapters.append(
                    GraphicsAdapter(
                        name=name,
                        vendor=vendor,
                        adapter_ram=adapter_ram,
                        pnp_device_id=pnp_device_id,
                        dedicated=dedicated,
                        env_vars=env_vars,
                    )
                )
            return GraphicsDetectionResult(supported=supported, adapters=tuple(adapters), error=error)
        except Exception:
            return None

    @classmethod
    def _write_cache(cls, result: GraphicsDetectionResult, cache_path: Path | None = None) -> None:
        target = cache_path if cache_path is not None else (cls._get_cache_path() if cls._should_use_default_cache() else None)
        if target is None:
            return
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "supported": result.supported,
                "error": result.error,
                "adapters": [
                    {
                        "name": adapter.name,
                        "vendor": adapter.vendor,
                        "adapter_ram": adapter.adapter_ram,
                        "pnp_device_id": adapter.pnp_device_id,
                        "dedicated": adapter.dedicated,
                        "env_vars": [list(pair) for pair in adapter.env_vars],
                    }
                    for adapter in result.adapters
                ],
            }
            tmp = target.with_suffix(f".tmp.{os.getpid()}")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(target)
        except Exception:
            pass

    @classmethod
    def detect(cls, force_refresh: bool = False, cache_path: Path | None = None) -> GraphicsDetectionResult:
        if not force_refresh:
            cached = cls._read_cache(cache_path)
            if cached is not None:
                return cached

        if cls._is_windows():
            result = cls._detect_windows()
        elif cls._is_linux():
            result = cls._detect_linux()
        else:
            result = GraphicsDetectionResult(supported=False)

        if result.supported and not result.error:
            cls._write_cache(result, cache_path)
        return result

    @classmethod
    def _detect_windows(cls) -> GraphicsDetectionResult:
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
    def _detect_linux(cls) -> GraphicsDetectionResult:
        try:
            # Tier 1: switcherooctl list (freedesktop / systemd switcheroo-control)
            adapters = cls._detect_linux_switcheroo()
            if adapters is not None:
                return GraphicsDetectionResult(supported=True, adapters=tuple(adapters))

            # Tier 2: lspci
            adapters = cls._detect_linux_lspci()
            if adapters is not None:
                return GraphicsDetectionResult(supported=True, adapters=tuple(adapters))

            # Tier 3: /sys/bus/pci/devices sysfs scan
            adapters = cls._detect_linux_sysfs()
            if adapters is not None:
                return GraphicsDetectionResult(supported=True, adapters=tuple(adapters))

            # Tier 4: NVIDIA driver file check
            adapters = cls._detect_linux_proc_nvidia()
            if adapters is not None:
                return GraphicsDetectionResult(supported=True, adapters=tuple(adapters))

            return GraphicsDetectionResult(supported=True, adapters=())
        except Exception as error:
            return GraphicsDetectionResult(supported=True, error=str(error))

    @classmethod
    def _detect_linux_switcheroo(cls) -> list[GraphicsAdapter] | None:
        try:
            completed = subprocess.run(
                ["switcherooctl", "list"],
                capture_output=True,
                text=True,
                timeout=cls.DETECTION_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None

        if completed.returncode != 0 or not completed.stdout.strip():
            return None

        adapters: list[GraphicsAdapter] = []
        current: dict[str, str] = {}

        for raw_line in completed.stdout.splitlines():
            line = raw_line.strip()
            if line.startswith("Device:"):
                if current and current.get("Name"):
                    adapters.append(cls._build_switcheroo_adapter(current))
                current = {"Device": line.split(":", 1)[1].strip()}
            elif ":" in line and current:
                key, val = line.split(":", 1)
                current[key.strip()] = val.strip()

        if current and current.get("Name"):
            adapters.append(cls._build_switcheroo_adapter(current))

        return adapters or None

    @classmethod
    def _build_switcheroo_adapter(cls, data: dict[str, str]) -> GraphicsAdapter:
        name = data.get("Name", "").strip()
        is_discrete = data.get("Discrete", "").casefold() == "yes"
        is_default = data.get("Default", "").casefold() == "yes"
        env_str = data.get("Environment", "").strip()
        parsed_env: list[tuple[str, str]] = []
        if env_str:
            for item in env_str.split():
                if "=" in item:
                    k, v = item.split("=", 1)
                    parsed_env.append((k.strip(), v.strip()))

        if not is_discrete and not is_default:
            is_discrete = cls._looks_dedicated(name, "", 0)

        if is_discrete and not parsed_env:
            parsed_env = list(cls._default_dgpu_env_for_adapter(name, "").items())

        return GraphicsAdapter(
            name=name,
            pnp_device_id=data.get("Device", ""),
            dedicated=is_discrete,
            env_vars=tuple(parsed_env),
        )

    @classmethod
    def _detect_linux_lspci(cls) -> list[GraphicsAdapter] | None:
        try:
            completed = subprocess.run(
                ["lspci"],
                capture_output=True,
                text=True,
                timeout=cls.DETECTION_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None

        if completed.returncode != 0 or not completed.stdout.strip():
            return None

        adapters: list[GraphicsAdapter] = []
        for raw_line in completed.stdout.splitlines():
            line = raw_line.strip()
            if not any(token in line for token in ("VGA compatible controller", "3D controller", "Display controller")):
                continue
            parts = line.split(":", 2)
            pnp_id = parts[0].strip() if len(parts) > 1 else ""
            desc = parts[2].strip() if len(parts) > 2 else line
            desc = re.sub(r"\(rev\s+[0-9a-fA-F]+\)", "", desc).strip()
            is_3d = "3D controller" in line
            dedicated = is_3d or cls._looks_dedicated(desc, "", 0)
            env_vars = cls._default_dgpu_env_for_adapter(desc, "") if dedicated else {}
            adapters.append(
                GraphicsAdapter(
                    name=desc,
                    pnp_device_id=pnp_id,
                    dedicated=dedicated,
                    env_vars=tuple(env_vars.items()),
                )
            )
        return adapters or None

    @classmethod
    def _detect_linux_sysfs(cls) -> list[GraphicsAdapter] | None:
        pci_dir = Path("/sys/bus/pci/devices")
        if not pci_dir.is_dir():
            return None

        adapters: list[GraphicsAdapter] = []
        try:
            entries = sorted(pci_dir.iterdir(), key=lambda p: p.name)
        except OSError:
            return None

        for entry in entries:
            class_file = entry / "class"
            vendor_file = entry / "vendor"
            if not (class_file.is_file() and vendor_file.is_file()):
                continue
            try:
                pci_class = class_file.read_text(encoding="ascii", errors="ignore").strip().lower()
                pci_vendor = vendor_file.read_text(encoding="ascii", errors="ignore").strip().lower()
            except OSError:
                continue

            if not pci_class.startswith("0x03"):
                continue

            vendor_name = ""
            name = f"PCI Graphics ({entry.name})"
            if pci_vendor in ("0x10de", "10de"):
                vendor_name = "NVIDIA"
                name = f"NVIDIA Graphics Device ({entry.name})"
            elif pci_vendor in ("0x1002", "1002"):
                vendor_name = "AMD"
                name = f"AMD Radeon Graphics Device ({entry.name})"
            elif pci_vendor in ("0x8086", "8086"):
                vendor_name = "Intel"
                name = f"Intel Graphics Device ({entry.name})"

            is_3d = pci_class.startswith("0x0302")
            dedicated = (vendor_name == "NVIDIA") or is_3d or cls._looks_dedicated(name, vendor_name, 0)
            env_vars = cls._default_dgpu_env_for_adapter(name, vendor_name) if dedicated else {}
            adapters.append(
                GraphicsAdapter(
                    name=name,
                    vendor=vendor_name,
                    pnp_device_id=entry.name,
                    dedicated=dedicated,
                    env_vars=tuple(env_vars.items()),
                )
            )
        return adapters or None

    @classmethod
    def _detect_linux_proc_nvidia(cls) -> list[GraphicsAdapter] | None:
        if Path("/proc/driver/nvidia/version").is_file():
            name = "NVIDIA Dedicated Graphics (Driver)"
            env_vars = cls._default_dgpu_env_for_adapter(name, "NVIDIA")
            return [
                GraphicsAdapter(
                    name=name,
                    vendor="NVIDIA",
                    dedicated=True,
                    env_vars=tuple(env_vars.items()),
                )
            ]
        return None

    @classmethod
    def _default_dgpu_env_for_adapter(cls, name: str, vendor: str) -> dict[str, str]:
        combined = f"{vendor} {name}".casefold()
        if any(token in combined for token in ("nvidia", "geforce", "rtx", "gtx", "quadro")):
            return {
                "__NV_PRIME_RENDER_OFFLOAD": "1",
                "__GLX_VENDOR_LIBRARY_NAME": "nvidia",
                "__VK_LAYER_NV_optimus": "NVIDIA_only",
            }
        return {
            "DRI_PRIME": "1",
        }

    @classmethod
    def get_discrete_gpu_env(cls, detection: GraphicsDetectionResult | None = None) -> dict[str, str]:
        """Returns the dictionary of environment variables to activate the discrete GPU on Linux."""
        result = detection or cls.detect()
        for adapter in result.dedicated_adapters:
            if adapter.env_vars:
                return dict(adapter.env_vars)
            env = cls._default_dgpu_env_for_adapter(adapter.name, adapter.vendor)
            if env:
                return env
        return {
            "__NV_PRIME_RENDER_OFFLOAD": "1",
            "__GLX_VENDOR_LIBRARY_NAME": "nvidia",
            "__VK_LAYER_NV_optimus": "NVIDIA_only",
            "DRI_PRIME": "1",
        }

    @classmethod
    def get_launch_environment(
        cls,
        enabled: bool,
        base_env: dict[str, str] | None = None,
        detection: GraphicsDetectionResult | None = None,
    ) -> dict[str, str] | None:
        """Returns launch environment for Minecraft process according to GPU preference."""
        if not enabled:
            return base_env
        if cls._is_windows():
            return base_env
        if cls._is_linux():
            merged = dict(os.environ if base_env is None else base_env)
            merged.update(cls.get_discrete_gpu_env(detection))
            return merged
        return base_env

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
        if cls._is_windows():
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
        if cls._is_linux():
            return True
        return False

    @classmethod
    def adapter_summary(cls, adapters: Iterable[GraphicsAdapter]) -> str:
        names = [adapter.name for adapter in adapters if adapter.name]
        return ", ".join(names)

    @staticmethod
    def _is_windows() -> bool:
        return os.name == "nt" and sys.platform == "win32"

    @staticmethod
    def _is_linux() -> bool:
        return sys.platform.startswith("linux") or (os.name == "posix" and sys.platform != "darwin")

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
