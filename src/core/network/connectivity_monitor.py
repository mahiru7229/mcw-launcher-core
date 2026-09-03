from __future__ import annotations

from dataclasses import dataclass
import socket
from threading import RLock
import time


@dataclass(frozen=True, slots=True)
class ConnectivitySnapshot:
    online: bool
    checked_at: float
    latency_ms: float
    detail: str = ""


class ConnectivityMonitor:
    """Perform a bounded Internet reachability check without DNS lookups."""

    DEFAULT_TARGETS = (("1.1.1.1", 443), ("8.8.8.8", 443))
    DEFAULT_TIMEOUT_SECONDS = 0.6
    DEFAULT_MAX_AGE_SECONDS = 10.0

    def __init__(self, targets: tuple[tuple[str, int], ...] | None = None) -> None:
        self._targets = tuple(targets or self.DEFAULT_TARGETS)
        self._lock = RLock()
        self._snapshot: ConnectivitySnapshot | None = None

    @property
    def snapshot(self) -> ConnectivitySnapshot | None:
        with self._lock:
            return self._snapshot

    def probe(
        self,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        force: bool = False,
        max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
    ) -> ConnectivitySnapshot:
        now = time.monotonic()
        with self._lock:
            cached = self._snapshot
            if (
                not force
                and cached is not None
                and now - cached.checked_at <= max(0.0, float(max_age_seconds))
            ):
                return cached

        started = time.monotonic()
        failures: list[str] = []
        for host, port in self._targets:
            connection = None
            try:
                connection = socket.create_connection(
                    (str(host), int(port)),
                    timeout=max(0.05, float(timeout)),
                )
                snapshot = ConnectivitySnapshot(
                    online=True,
                    checked_at=time.monotonic(),
                    latency_ms=max(0.0, (time.monotonic() - started) * 1000.0),
                )
                return self._publish(snapshot)
            except OSError as error:
                failures.append(type(error).__name__)
            finally:
                if connection is not None:
                    try:
                        connection.close()
                    except OSError:
                        pass

        snapshot = ConnectivitySnapshot(
            online=False,
            checked_at=time.monotonic(),
            latency_ms=max(0.0, (time.monotonic() - started) * 1000.0),
            detail=failures[-1] if failures else "unreachable",
        )
        return self._publish(snapshot)

    def _publish(self, snapshot: ConnectivitySnapshot) -> ConnectivitySnapshot:
        with self._lock:
            self._snapshot = snapshot
        return snapshot


connectivity_monitor = ConnectivityMonitor()
