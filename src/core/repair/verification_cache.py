from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import os
import threading


@dataclass(frozen=True, slots=True)
class VerificationResult:
    valid: bool
    cache_hit: bool
    hashed: bool
    actual_size: int
    actual_hash: str = ""
    reason: str = ""


class VerificationCache:
    SCHEMA_VERSION = 1

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._records = self._load()
        self._dirty = False

    def verify(self, key: str, path: Path, expected_size: int = 0, expected_hash: str = "", algorithm: str = "sha1", force_hash: bool = False) -> VerificationResult:
        normalized_key = str(key).strip().casefold()
        target = Path(path)
        expected_hash = str(expected_hash or "").strip().lower()
        expected_size = max(0, int(expected_size or 0))
        algorithm = str(algorithm or "sha1").strip().lower()

        if not target.is_file():
            self.remove(normalized_key)
            return VerificationResult(False, False, False, 0, reason="missing")

        try:
            stat_result = target.stat()
        except OSError:
            self.remove(normalized_key)
            return VerificationResult(False, False, False, 0, reason="unreadable")

        if expected_size > 0 and stat_result.st_size != expected_size:
            self.remove(normalized_key)
            return VerificationResult(False, False, False, stat_result.st_size, reason="size_mismatch")

        with self._lock:
            record = self._records.get(normalized_key)
        if expected_hash and self._record_matches(record, target, stat_result.st_size, stat_result.st_mtime_ns, expected_hash, algorithm):
            return VerificationResult(True, True, False, stat_result.st_size, expected_hash)

        if not force_hash:
            # Quick verification deliberately avoids hashing unchanged large files.
            # Exact size plus a readable regular file is enough for a fast launch
            # health check. A later full verification records the trusted digest.
            return VerificationResult(True, False, False, stat_result.st_size, reason="size_only")

        if not expected_hash:
            return VerificationResult(True, False, False, stat_result.st_size, reason="no_expected_hash")

        try:
            actual_hash = self._hash(target, algorithm)
        except (OSError, ValueError):
            self.remove(normalized_key)
            return VerificationResult(False, False, True, stat_result.st_size, reason="hash_failed")

        valid = actual_hash.casefold() == expected_hash.casefold()
        if valid:
            with self._lock:
                self._records[normalized_key] = {
                    "path": str(target),
                    "size": stat_result.st_size,
                    "mtimeNs": stat_result.st_mtime_ns,
                    "algorithm": algorithm,
                    "hash": expected_hash,
                }
                self._dirty = True
        else:
            self.remove(normalized_key)
        return VerificationResult(valid, False, True, stat_result.st_size, actual_hash, "" if valid else "hash_mismatch")

    def remove(self, key: str) -> None:
        normalized = str(key).strip().casefold()
        with self._lock:
            if normalized in self._records:
                self._records.pop(normalized, None)
                self._dirty = True

    def save(self) -> None:
        with self._lock:
            if not self._dirty:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"schemaVersion": self.SCHEMA_VERSION, "records": self._records}
            temporary = self.path.with_suffix(self.path.suffix + ".part")
            try:
                with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(self.path)
                self._dirty = False
            finally:
                temporary.unlink(missing_ok=True)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
            self._dirty = True
        self.save()

    def _load(self) -> dict[str, dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict) or int(data.get("schemaVersion", 0) or 0) != self.SCHEMA_VERSION:
            return {}
        raw = data.get("records")
        if not isinstance(raw, dict):
            return {}
        return {str(key).casefold(): value for key, value in raw.items() if isinstance(value, dict)}

    @staticmethod
    def _record_matches(record: object, path: Path, size: int, mtime_ns: int, expected_hash: str, algorithm: str) -> bool:
        if not isinstance(record, dict):
            return False
        return (
            str(record.get("path") or "") == str(path)
            and int(record.get("size", -1)) == int(size)
            and int(record.get("mtimeNs", -1)) == int(mtime_ns)
            and str(record.get("algorithm") or "").casefold() == algorithm.casefold()
            and str(record.get("hash") or "").casefold() == expected_hash.casefold()
        )

    @staticmethod
    def _hash(path: Path, algorithm: str) -> str:
        normalized = algorithm.casefold().replace("-", "")
        if normalized == "sha1":
            digest = hashlib.sha1(usedforsecurity=False)
        elif normalized == "sha256":
            digest = hashlib.sha256()
        elif normalized == "sha512":
            digest = hashlib.sha512()
        else:
            raise ValueError(f"Unsupported verification algorithm: {algorithm}")
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
