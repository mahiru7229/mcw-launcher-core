from __future__ import annotations

import ctypes
import os
import sys

from src.core.java.java_manager import JavaManager
from src.core.system.memory import MemoryAllocationPolicy, SystemMemory
from src.models.hardware.first_run_recommendation import FirstRunRecommendation, JavaRuntimeSummary


class FirstRunRecommendationService:
    """Collect safe first-run defaults without depending on the GUI."""

    @classmethod
    def inspect(cls) -> FirstRunRecommendation:
        base = cls.fallback()
        try:
            discovered = JavaManager.find_installation()
        except Exception:
            discovered = []
        installations = tuple(
            JavaRuntimeSummary(
                major=max(0, int(java.version)),
                executable=java.executable,
                source=str(getattr(getattr(java, "source", None), "value", getattr(java, "source", "unknown"))),
            )
            for java in discovered
            if int(getattr(java, "version", 0) or 0) > 0
        )
        preferred = cls._preferred_java(installations)
        return FirstRunRecommendation(
            total_memory_mb=base.total_memory_mb,
            available_memory_mb=base.available_memory_mb,
            recommended_min_memory_mb=base.recommended_min_memory_mb,
            recommended_max_memory_mb=base.recommended_max_memory_mb,
            java_installations=installations,
            recommended_java_path=str(preferred.executable) if preferred is not None else "",
        )

    @classmethod
    def fallback(cls) -> FirstRunRecommendation:
        """Return safe memory defaults even when Java or hardware probing fails."""
        try:
            total = SystemMemory.total_physical_memory_mb()
        except Exception:
            total = 0
        try:
            available = cls.available_physical_memory_mb()
        except Exception:
            available = 0
        recommended_max = cls.recommended_max_memory_mb(total, available)
        return FirstRunRecommendation(
            total_memory_mb=max(0, total),
            available_memory_mb=max(0, available),
            recommended_min_memory_mb=min(1024, recommended_max),
            recommended_max_memory_mb=recommended_max,
            java_installations=(),
            recommended_java_path="",
        )

    @classmethod
    def recommended_max_memory_mb(cls, total_memory_mb: int, available_memory_mb: int = 0) -> int:
        total = max(0, int(total_memory_mb or 0))
        available = max(0, int(available_memory_mb or 0))
        if total <= 0:
            return MemoryAllocationPolicy.DEFAULT_MAX_MEMORY_MB
        # Leave enough room for Windows and the launcher.  Recommendations are
        # deliberately conservative; users can still choose a custom value.
        if total < 4096:
            recommendation = 1024
        elif total < 8192:
            recommendation = 2048
        elif total < 12288:
            recommendation = 4096
        elif total < 24576:
            recommendation = 6144
        else:
            recommendation = 8192
        if available > 0:
            safe_available = max(1024, available - 1536)
            recommendation = min(recommendation, safe_available)
        recommendation = min(recommendation, max(1024, int(total * 0.60)))
        return MemoryAllocationPolicy.snap_mb(recommendation, MemoryAllocationPolicy.physical_limit_mb(total))

    @staticmethod
    def available_physical_memory_mb() -> int:
        if sys.platform == "win32":
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
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                    return int(status.ullAvailPhys // (1024 * 1024))
            except (AttributeError, OSError, ValueError):
                return 0
        try:
            page_size = int(os.sysconf("SC_PAGE_SIZE"))
            pages = int(os.sysconf("SC_AVPHYS_PAGES"))
            return max(0, page_size * pages // (1024 * 1024))
        except (AttributeError, OSError, TypeError, ValueError):
            return 0

    @staticmethod
    def _preferred_java(installations: tuple[JavaRuntimeSummary, ...]) -> JavaRuntimeSummary | None:
        if not installations:
            return None
        # Java 21 is the most useful modern default while the executor still
        # resolves the exact compatible major for each Minecraft version.
        order = {21: 0, 17: 1, 25: 2, 26: 3, 8: 4}
        return min(installations, key=lambda item: (order.get(item.major, 10), -item.major, str(item.executable).casefold()))
