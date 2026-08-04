from __future__ import annotations


class DownloadEngineError(RuntimeError):
    """Base class for unified download-engine failures."""


class DownloadValidationError(DownloadEngineError):
    pass


class DownloadChecksumMismatchError(DownloadValidationError):
    def __init__(self, filename: str, algorithm: str) -> None:
        self.filename = str(filename)
        self.algorithm = str(algorithm).lower()
        super().__init__(f"{self.algorithm.upper()} mismatch for: {self.filename}")


class DownloadSizeMismatchError(DownloadValidationError):
    pass


class DownloadFailedError(DownloadEngineError):
    def __init__(self, filename: str, attempts: int, reason: str, url: str = "") -> None:
        self.filename = str(filename)
        self.attempts = max(1, int(attempts))
        self.reason = str(reason or "unknown error")
        self.url = str(url or "")
        super().__init__(f"Failed to download '{self.filename}' after {self.attempts} attempts: {self.reason}")
