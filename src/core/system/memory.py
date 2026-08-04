from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path


class SystemMemory:
    BYTES_PER_MB = 1024 * 1024

    @classmethod
    def total_physical_memory_mb(cls) -> int:
        total_bytes = cls._total_physical_memory_bytes()
        if total_bytes <= 0:
            return 0
        return max(1, total_bytes // cls.BYTES_PER_MB)

    @classmethod
    def _total_physical_memory_bytes(cls) -> int:
        if sys.platform == "win32":
            detected = cls._windows_total_physical_memory_bytes()
            if detected > 0:
                return detected

        detected = cls._posix_total_physical_memory_bytes()
        if detected > 0:
            return detected

        return cls._proc_meminfo_total_physical_memory_bytes()

    @staticmethod
    def _windows_total_physical_memory_bytes() -> int:
        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        try:
            status = MemoryStatusEx()
            status.dwLength = ctypes.sizeof(MemoryStatusEx)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return 0
            return int(status.ullTotalPhys)
        except (AttributeError, OSError, ValueError):
            return 0

    @staticmethod
    def _posix_total_physical_memory_bytes() -> int:
        try:
            page_size = int(os.sysconf("SC_PAGE_SIZE"))
            page_count = int(os.sysconf("SC_PHYS_PAGES"))
        except (AttributeError, OSError, TypeError, ValueError):
            return 0
        return page_size * page_count if page_size > 0 and page_count > 0 else 0

    @staticmethod
    def _proc_meminfo_total_physical_memory_bytes() -> int:
        try:
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                if not line.startswith("MemTotal:"):
                    continue
                kibibytes = int(line.split()[1])
                return kibibytes * 1024
        except (FileNotFoundError, OSError, UnicodeError, ValueError, IndexError):
            return 0
        return 0


class MemoryAllocationPolicy:
    MIN_MEMORY_MB = 256
    DEFAULT_MIN_MEMORY_MB = 1024
    DEFAULT_MAX_MEMORY_MB = 2048
    SLIDER_STEP_MB = 256
    FALLBACK_PHYSICAL_LIMIT_MB = 4096

    @classmethod
    def physical_limit_mb(cls, total_memory_mb: int | None = None) -> int:
        detected = cls._as_int(total_memory_mb)
        if detected <= 0:
            detected = SystemMemory.total_physical_memory_mb()
        if detected <= 0:
            detected = cls.FALLBACK_PHYSICAL_LIMIT_MB
        return max(cls.MIN_MEMORY_MB, detected)

    @classmethod
    def normalize(cls, min_memory_mb: object, max_memory_mb: object, total_memory_mb: int | None = None) -> tuple[int, int]:
        limit = cls.physical_limit_mb(total_memory_mb)
        maximum = cls._as_int(max_memory_mb, cls.DEFAULT_MAX_MEMORY_MB)
        minimum = cls._as_int(min_memory_mb, cls.DEFAULT_MIN_MEMORY_MB)
        maximum = min(max(maximum, cls.MIN_MEMORY_MB), limit)
        minimum = min(max(minimum, cls.MIN_MEMORY_MB), maximum)
        return minimum, maximum

    @classmethod
    def is_valid(cls, min_memory_mb: object, max_memory_mb: object, total_memory_mb: int | None = None) -> bool:
        minimum = cls._as_int(min_memory_mb)
        maximum = cls._as_int(max_memory_mb)
        limit = cls.physical_limit_mb(total_memory_mb)
        return cls.MIN_MEMORY_MB <= minimum <= maximum <= limit

    @classmethod
    def snap_mb(cls, memory_mb: object, upper_bound_mb: int) -> int:
        upper_bound = max(cls.MIN_MEMORY_MB, int(upper_bound_mb))
        value = min(max(cls._as_int(memory_mb, cls.MIN_MEMORY_MB), cls.MIN_MEMORY_MB), upper_bound)
        step_count = round((value - cls.MIN_MEMORY_MB) / cls.SLIDER_STEP_MB)
        snapped = cls.MIN_MEMORY_MB + step_count * cls.SLIDER_STEP_MB
        return min(max(snapped, cls.MIN_MEMORY_MB), upper_bound)

    @staticmethod
    def format_mb(memory_mb: int) -> str:
        value = max(0, int(memory_mb))
        if value < 1024:
            return f"{value} MB"
        gibibytes = value / 1024
        formatted = f"{gibibytes:.2f}".rstrip("0").rstrip(".")
        return f"{formatted} GB ({value} MB)"

    @staticmethod
    def _as_int(value: object, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            return default
