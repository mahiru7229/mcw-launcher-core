from __future__ import annotations

from dataclasses import dataclass
import platform
import sys


@dataclass(frozen=True, slots=True)
class PlatformProfile:
    os_name: str
    architecture: str
    adoptium_architecture: str
    java_executable: str
    java_console_executable: str
    archive_suffix: str


class PlatformInfo:
    """Single source of truth for launcher platform-specific names."""

    _OS_NAMES = {
        "windows": "windows",
        "linux": "linux",
        "darwin": "mac",
    }
    _ARCHITECTURES = {
        "amd64": ("x64", "x64"),
        "x86_64": ("x64", "x64"),
        "x86": ("x86", "x86"),
        "i386": ("x86", "x86"),
        "i686": ("x86", "x86"),
        "arm64": ("arm64", "aarch64"),
        "aarch64": ("arm64", "aarch64"),
    }

    @classmethod
    def current(cls) -> PlatformProfile:
        system = platform.system().strip().casefold()
        machine = platform.machine().strip().casefold()
        fallback = sys.platform.strip().casefold()
        if fallback.startswith("win"):
            fallback = "windows"
        elif fallback.startswith("linux"):
            fallback = "linux"
        elif fallback == "darwin":
            fallback = "mac"
        os_name = cls._OS_NAMES.get(system, system or fallback)
        architecture, adoptium_architecture = cls._ARCHITECTURES.get(
            machine,
            (machine or "unknown", machine or "unknown"),
        )
        # Keep every platform-specific value derived from the same detected
        # profile. Mixing in os.name makes cross-platform tests (and any
        # caller-supplied platform probe) produce a Linux profile containing
        # Windows Java/archive names when the host process is Windows.
        is_windows = os_name == "windows"
        return PlatformProfile(
            os_name=os_name,
            architecture=architecture,
            adoptium_architecture=adoptium_architecture,
            java_executable="javaw.exe" if is_windows else "java",
            java_console_executable="java.exe" if is_windows else "java",
            archive_suffix=".zip" if is_windows else ".tar.gz",
        )

    @classmethod
    def supports_managed_java(cls) -> bool:
        profile = cls.current()
        return profile.os_name in {"windows", "linux"} and profile.adoptium_architecture in {
            "x64",
            "x86",
            "aarch64",
        }

    @staticmethod
    def is_windows() -> bool:
        return PlatformInfo.current().os_name == "windows"

    @classmethod
    def java_home_executables(cls) -> tuple[str, ...]:
        profile = cls.current()
        if profile.os_name == "windows":
            return (profile.java_executable, profile.java_console_executable)
        return (profile.java_executable,)
