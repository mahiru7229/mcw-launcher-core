from __future__ import annotations

from collections import deque
from collections.abc import Callable
import time


class DownloadRateMeter:
    WINDOW_SECONDS = 2.0

    def __init__(self, initial_bytes: int = 0, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.monotonic
        now = self._clock()
        self._samples: deque[tuple[float, int]] = deque([(now, max(0, int(initial_bytes)))])

    def update(self, current_bytes: int) -> float | None:
        now = self._clock()
        current = max(0, int(current_bytes))
        self._samples.append((now, current))

        cutoff = now - self.WINDOW_SECONDS
        while len(self._samples) > 2 and self._samples[1][0] <= cutoff:
            self._samples.popleft()

        started_at, started_bytes = self._samples[0]
        elapsed = now - started_at
        transferred = current - started_bytes

        if elapsed <= 0 or transferred <= 0:
            return None

        return transferred / elapsed
