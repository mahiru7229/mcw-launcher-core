from __future__ import annotations

from pathlib import Path
import os
import tempfile
import time


DEFAULT_RETRY_DELAYS = (0.05, 0.15, 0.30, 0.50)
_WINDOWS_RETRYABLE_ERRORS = {5, 32}


def _is_retryable_replace_error(error: OSError) -> bool:
    if isinstance(error, PermissionError):
        return True
    return getattr(error, "winerror", None) in _WINDOWS_RETRYABLE_ERRORS


def replace_with_retry(
    source: Path,
    destination: Path,
    *,
    retry_delays: tuple[float, ...] = DEFAULT_RETRY_DELAYS,
) -> None:
    source_path = Path(source)
    destination_path = Path(destination)
    for attempt in range(len(retry_delays) + 1):
        try:
            os.replace(source_path, destination_path)
            return
        except OSError as error:
            if not _is_retryable_replace_error(error) or attempt >= len(retry_delays):
                raise
            time.sleep(max(0.0, float(retry_delays[attempt])))


def atomic_write_text(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
    newline: str | None = "\n",
    retry_delays: tuple[float, ...] = DEFAULT_RETRY_DELAYS,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding=encoding, newline=newline) as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        replace_with_retry(temporary, target, retry_delays=retry_delays)
        return target
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
