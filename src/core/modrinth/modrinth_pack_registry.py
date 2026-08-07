from __future__ import annotations

from pathlib import Path, PurePosixPath
import hashlib
import json

from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.modrinth.pack_state import ModrinthManagedFileChange, ModrinthPackStateReport
from src.models.progress.progress_stage import ProgressStage


class ModrinthPackRegistry:
    SCHEMA_VERSION = 6
    FILE_NAME = "modrinth-pack.json"

    @staticmethod
    def path(instance_dir: Path) -> Path:
        return Path(instance_dir) / ".mcw" / ModrinthPackRegistry.FILE_NAME

    @staticmethod
    def load(instance: Instance) -> dict:
        return ModrinthPackRegistry.load_from_dir(instance.instance_dir)

    @staticmethod
    def load_from_dir(instance_dir: Path) -> dict:
        path = ModrinthPackRegistry.path(instance_dir)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        files = data.get("managedFiles")
        if not isinstance(files, list):
            data["managedFiles"] = []
        if not isinstance(data.get("verificationCache"), dict):
            data["verificationCache"] = {}
        return data

    @staticmethod
    def save(instance_dir: Path, data: dict) -> None:
        path = ModrinthPackRegistry.path(instance_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(data)
        payload["schemaVersion"] = ModrinthPackRegistry.SCHEMA_VERSION
        payload["managedFiles"] = ModrinthPackRegistry._normalize_files(payload.get("managedFiles", []))
        payload["preservedFiles"] = ModrinthPackRegistry._normalize_preserved_files(payload.get("preservedFiles", []))
        payload["verificationCache"] = ModrinthPackRegistry._normalize_verification_cache(payload.get("verificationCache", {}), payload["managedFiles"])
        temp = path.with_suffix(path.suffix + ".part")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    @staticmethod
    def scan(instance: Instance, reporter: ProgressReporter | None = None, force_hash: bool = False) -> ModrinthPackStateReport:
        data = ModrinthPackRegistry.load(instance)
        changes: list[ModrinthManagedFileChange] = []
        root = Path(instance.instance_dir)
        managed_files = data.get("managedFiles", []) if isinstance(data.get("managedFiles"), list) else []
        cache = ModrinthPackRegistry._normalize_verification_cache(data.get("verificationCache", {}), managed_files)
        original_cache = json.dumps(cache, sort_keys=True, separators=(",", ":"))
        verified_files = 0
        cache_hits = 0
        hashed_files = 0
        message = "Scanning managed Modrinth pack files..."
        ModrinthPackRegistry._report(reporter, message, 0, len(managed_files))

        for completed, entry in enumerate(managed_files, start=1):
            if not isinstance(entry, dict):
                ModrinthPackRegistry._report(reporter, message, completed, len(managed_files))
                continue
            relative = ModrinthPackRegistry._safe_relative(str(entry.get("path") or ""))
            if relative is None:
                ModrinthPackRegistry._report(reporter, message, completed, len(managed_files))
                continue
            target = root.joinpath(*relative.parts)
            source = str(entry.get("source") or "")
            if not target.is_file():
                cache.pop(relative.as_posix().casefold(), None)
                changes.append(ModrinthManagedFileChange(path=relative.as_posix(), state="missing", source=source))
                ModrinthPackRegistry._report(reporter, message, completed, len(managed_files))
                continue

            verified, cache_hit, hashed_bytes = ModrinthPackRegistry.verify_entry(root, entry, cache=cache, force_hash=force_hash)
            if verified:
                verified_files += 1
                cache_hits += int(cache_hit)
                hashed_files += int(hashed_bytes > 0)
            else:
                hashed_files += int(hashed_bytes > 0)
                changes.append(ModrinthManagedFileChange(path=relative.as_posix(), state="modified", source=source))
            ModrinthPackRegistry._report(reporter, message, completed, len(managed_files))

        normalized_cache = ModrinthPackRegistry._normalize_verification_cache(cache, managed_files)
        if json.dumps(normalized_cache, sort_keys=True, separators=(",", ":")) != original_cache:
            data["verificationCache"] = normalized_cache
            ModrinthPackRegistry.save(instance.instance_dir, data)

        return ModrinthPackStateReport(
            project_id=str(data.get("projectId") or ""),
            version_id=str(data.get("versionId") or ""),
            managed_files=len(managed_files),
            changes=tuple(changes),
            verified_files=verified_files,
            cache_hits=cache_hits,
            hashed_files=hashed_files,
        )

    @staticmethod
    def verify_entry(instance_dir: Path, entry: dict, cache: dict | None = None, force_hash: bool = False) -> tuple[bool, bool, int]:
        relative = ModrinthPackRegistry._safe_relative(str(entry.get("path") or ""))
        if relative is None:
            return False, False, 0
        target = Path(instance_dir).joinpath(*relative.parts)
        key = relative.as_posix().casefold()
        cache_data = cache if isinstance(cache, dict) else {}
        if not target.is_file():
            cache_data.pop(key, None)
            return False, False, 0

        try:
            stat_result = target.stat()
        except OSError:
            cache_data.pop(key, None)
            return False, False, 0

        expected_size = max(0, int(entry.get("size", 0) or 0))
        expected_sha1 = str(entry.get("sha1") or "").lower()
        expected_sha512 = str(entry.get("sha512") or "").lower()
        if expected_size > 0 and stat_result.st_size != expected_size:
            cache_data.pop(key, None)
            return False, False, 0
        if not expected_sha1 and not expected_sha512:
            cache_data.pop(key, None)
            return False, False, 0

        cached = cache_data.get(key)
        if not force_hash and ModrinthPackRegistry._cache_matches(cached, relative.as_posix(), stat_result.st_size, stat_result.st_mtime_ns, expected_sha1, expected_sha512):
            return True, True, 0

        from src.core.modrinth.modrinth_downloader import ModrinthDownloader

        verified = ModrinthDownloader.verify(target, sha1=expected_sha1, sha512=expected_sha512, expected_size=expected_size)
        if verified:
            cache_data[key] = ModrinthPackRegistry._cache_record(relative.as_posix(), stat_result.st_size, stat_result.st_mtime_ns, expected_sha1, expected_sha512)
        else:
            cache_data.pop(key, None)
        return verified, False, stat_result.st_size

    @staticmethod
    def build_verification_cache(instance_dir: Path, managed_files: list[dict]) -> dict:
        cache: dict[str, dict] = {}
        root = Path(instance_dir)
        for entry in managed_files:
            if not isinstance(entry, dict):
                continue
            relative = ModrinthPackRegistry._safe_relative(str(entry.get("path") or ""))
            if relative is None:
                continue
            target = root.joinpath(*relative.parts)
            try:
                stat_result = target.stat()
            except OSError:
                continue
            expected_size = max(0, int(entry.get("size", 0) or 0))
            if not target.is_file() or (expected_size > 0 and stat_result.st_size != expected_size):
                continue
            expected_sha1 = str(entry.get("sha1") or "").lower()
            expected_sha512 = str(entry.get("sha512") or "").lower()
            if not expected_sha1 and not expected_sha512:
                continue
            key = relative.as_posix().casefold()
            cache[key] = ModrinthPackRegistry._cache_record(relative.as_posix(), stat_result.st_size, stat_result.st_mtime_ns, expected_sha1, expected_sha512)
        return cache

    @staticmethod
    def _normalize_files(value: object) -> list[dict]:
        if not isinstance(value, list):
            return []
        normalized: dict[str, dict] = {}
        for item in value:
            if not isinstance(item, dict):
                continue
            relative = ModrinthPackRegistry._safe_relative(str(item.get("path") or ""))
            if relative is None:
                continue
            key = relative.as_posix()
            normalized[key.casefold()] = {
                "path": key,
                "sha1": str(item.get("sha1") or "").lower(),
                "sha512": str(item.get("sha512") or "").lower(),
                "size": max(0, int(item.get("size", 0) or 0)),
                "source": str(item.get("source") or "pack"),
                "provider": str(item.get("provider") or ("modrinth" if str(item.get("source") or "") == "download" else "pack")).strip().casefold(),
                "projectId": str(item.get("projectId") or "").strip(),
                "versionId": str(item.get("versionId") or "").strip(),
                "fileName": Path(str(item.get("fileName") or relative.name)).name,
                "downloads": ModrinthPackRegistry._normalize_downloads(item.get("downloads", [])),
                "required": bool(item.get("required", True)),
                "selectionReason": str(item.get("selectionReason") or "pack_manifest").strip().casefold(),
                "requiredBy": ModrinthPackRegistry._normalize_required_by(item.get("requiredBy", [])),
                "displayName": str(item.get("displayName") or item.get("title") or relative.name).strip(),
                "versionNumber": str(item.get("versionNumber") or "").strip(),
                "providesModId": str(item.get("providesModId") or "").strip().casefold(),
                "requestedVersionRanges": ModrinthPackRegistry._normalize_required_by(item.get("requestedVersionRanges", [])),
            }
        return sorted(normalized.values(), key=lambda item: item["path"].casefold())

    @staticmethod
    def _normalize_downloads(value: object) -> list[str]:
        if not isinstance(value, (list, tuple)):
            return []
        return list(dict.fromkeys(str(url).strip() for url in value if str(url).strip()))

    @staticmethod
    def _normalize_required_by(value: object) -> list[str]:
        if not isinstance(value, (list, tuple, set)):
            return []
        return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))

    @staticmethod
    def _normalize_preserved_files(value: object) -> list[dict]:
        if not isinstance(value, list):
            return []
        normalized: dict[str, dict] = {}
        for item in value:
            if not isinstance(item, dict):
                continue
            relative = ModrinthPackRegistry._safe_relative(str(item.get("path") or ""))
            if relative is None:
                continue
            key = relative.as_posix()
            normalized[key.casefold()] = {
                "path": key,
                "reason": str(item.get("reason") or "preserved"),
                "previousSha1": str(item.get("previousSha1") or "").lower(),
                "targetSha1": str(item.get("targetSha1") or "").lower(),
            }
        return sorted(normalized.values(), key=lambda item: item["path"].casefold())

    @staticmethod
    def _normalize_verification_cache(value: object, managed_files: list[dict]) -> dict[str, dict]:
        if not isinstance(value, dict):
            return {}
        managed_paths = {str(item.get("path") or "").casefold() for item in managed_files if isinstance(item, dict)}
        normalized: dict[str, dict] = {}
        for raw_key, raw_record in value.items():
            if not isinstance(raw_record, dict):
                continue
            relative = ModrinthPackRegistry._safe_relative(str(raw_record.get("path") or raw_key or ""))
            if relative is None:
                continue
            path = relative.as_posix()
            key = path.casefold()
            if key not in managed_paths:
                continue
            try:
                size = max(0, int(raw_record.get("size", 0) or 0))
                mtime_ns = max(0, int(raw_record.get("mtimeNs", 0) or 0))
            except (TypeError, ValueError):
                continue
            sha1 = str(raw_record.get("sha1") or "").lower()
            sha512 = str(raw_record.get("sha512") or "").lower()
            if not sha1 and not sha512:
                continue
            normalized[key] = ModrinthPackRegistry._cache_record(path, size, mtime_ns, sha1, sha512)
        return normalized

    @staticmethod
    def _cache_matches(record: object, path: str, size: int, mtime_ns: int, sha1: str, sha512: str) -> bool:
        if not isinstance(record, dict):
            return False
        return (
            str(record.get("path") or "").casefold() == path.casefold()
            and int(record.get("size", -1)) == size
            and int(record.get("mtimeNs", -1)) == mtime_ns
            and str(record.get("sha1") or "").lower() == sha1
            and str(record.get("sha512") or "").lower() == sha512
        )

    @staticmethod
    def _cache_record(path: str, size: int, mtime_ns: int, sha1: str, sha512: str) -> dict:
        return {"path": path, "size": max(0, int(size)), "mtimeNs": max(0, int(mtime_ns)), "sha1": sha1.lower(), "sha512": sha512.lower()}

    @staticmethod
    def _safe_relative(value: str) -> PurePosixPath | None:
        normalized = str(value).replace("\\", "/").strip()
        path = PurePosixPath(normalized)
        if not normalized or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            return None
        if ":" in path.parts[0]:
            return None
        return path

    @staticmethod
    def _hashes(path: Path, include_sha1: bool, include_sha512: bool) -> tuple[str, str]:
        sha1 = hashlib.sha1(usedforsecurity=False) if include_sha1 else None
        sha512 = hashlib.sha512() if include_sha512 else None
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                if sha1 is not None:
                    sha1.update(chunk)
                if sha512 is not None:
                    sha512.update(chunk)
        return sha1.hexdigest() if sha1 is not None else "", sha512.hexdigest() if sha512 is not None else ""

    @staticmethod
    def _sha1(path: Path) -> str:
        return ModrinthPackRegistry._hashes(path, True, False)[0]

    @staticmethod
    def _report(reporter: ProgressReporter | None, message: str, current: int, total: int) -> None:
        if reporter is not None:
            reporter.files(stage=ProgressStage.CHECKING_MODPACK, message=message, current=current, total=total)
