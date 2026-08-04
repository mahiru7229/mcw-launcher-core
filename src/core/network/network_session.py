from __future__ import annotations

from threading import RLock

import httpx

from src.config import MODRINTH_USER_AGENT


DEFAULT_MAX_CONCURRENT_DOWNLOADS = 8
MAX_CONCURRENT_DOWNLOADS = 16


class NetworkSession:
    def __init__(self) -> None:
        self._lock = RLock()
        self._client: httpx.Client | None = None
        self._max_concurrent_downloads = DEFAULT_MAX_CONCURRENT_DOWNLOADS

    @property
    def max_concurrent_downloads(self) -> int:
        with self._lock:
            return self._max_concurrent_downloads

    def configure(self, max_concurrent_downloads: object = DEFAULT_MAX_CONCURRENT_DOWNLOADS) -> int:
        try:
            parsed = int(max_concurrent_downloads)
        except (TypeError, ValueError):
            parsed = DEFAULT_MAX_CONCURRENT_DOWNLOADS
        normalized = min(max(parsed, 1), MAX_CONCURRENT_DOWNLOADS)
        with self._lock:
            changed = normalized != self._max_concurrent_downloads
            self._max_concurrent_downloads = normalized
            if changed:
                self._close_locked()
        return normalized

    def get_client(self) -> httpx.Client:
        with self._lock:
            if self._client is None or self._client.is_closed:
                max_connections = max(12, self._max_concurrent_downloads * 4)
                max_keepalive = max(6, self._max_concurrent_downloads * 2)
                self._client = httpx.Client(
                    follow_redirects=True,
                    headers={"User-Agent": MODRINTH_USER_AGENT, "Accept-Encoding": "identity"},
                    limits=httpx.Limits(max_connections=max_connections, max_keepalive_connections=max_keepalive, keepalive_expiry=30.0),
                )
            return self._client

    def close(self) -> None:
        with self._lock:
            self._close_locked()

    def _close_locked(self) -> None:
        if self._client is not None and not self._client.is_closed:
            self._client.close()
        self._client = None


network_session = NetworkSession()
