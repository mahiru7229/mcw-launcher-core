from __future__ import annotations

from collections.abc import Callable
from threading import Lock
import math
import time

from src.core.network.download_pause import download_pause_controller


class DownloadBandwidthLimiter:
    BYTES_PER_MEGABYTE = 1024 * 1024

    def __init__(self, clock: Callable[[], float] | None = None, sleeper: Callable[[float], None] | None = None) -> None:
        self._clock = clock or time.monotonic
        self._sleeper = sleeper or time.sleep
        self._interruptible_sleep = sleeper is None
        self._lock = Lock()
        self._limit_bytes_per_second = 0.0
        self._next_available_at = 0.0

    @property
    def limit_mbps(self) -> float:
        with self._lock:
            return self._limit_bytes_per_second / self.BYTES_PER_MEGABYTE

    @property
    def is_enabled(self) -> bool:
        with self._lock:
            return self._limit_bytes_per_second > 0

    def configure_mbps(self, value: object) -> float:
        limit_mbps = self._normalize_mbps(value)
        limit_bytes_per_second = limit_mbps * self.BYTES_PER_MEGABYTE

        with self._lock:
            if math.isclose(self._limit_bytes_per_second, limit_bytes_per_second, rel_tol=0.0, abs_tol=0.5):
                return limit_mbps
            self._limit_bytes_per_second = limit_bytes_per_second
            self._next_available_at = self._clock()

        return limit_mbps

    def throttle(self, byte_count: int) -> None:
        byte_count = max(0, int(byte_count))
        if byte_count == 0:
            return

        with self._lock:
            limit = self._limit_bytes_per_second
            if limit <= 0:
                return

            now = self._clock()
            scheduled_at = max(now, self._next_available_at) + (byte_count / limit)
            self._next_available_at = scheduled_at
            delay = scheduled_at - now

        if delay > 0:
            if self._interruptible_sleep:
                download_pause_controller.wait(delay)
            else:
                self._sleeper(delay)

    @staticmethod
    def _normalize_mbps(value: object) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0.0
        if not math.isfinite(parsed) or parsed <= 0:
            return 0.0
        return min(parsed, 1024.0)


download_bandwidth_limiter = DownloadBandwidthLimiter()
