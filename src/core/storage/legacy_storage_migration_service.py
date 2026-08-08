from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
import hashlib
import json
import os
import re
import shutil
import time

from src.config import VERSION_TAG
from src.core.fs.paths import Paths


@dataclass(frozen=True, slots=True)
class CleanupCandidate:
    candidate_id: str
    path: Path
    category: str
    reason: str
    safety: str
    size_bytes: int
    file_count: int
    directory_count: int
    reference_status: str = "unreferenced"
    reclaimable_bytes: int = -1

    @property
    def effective_reclaimable_bytes(self) -> int:
        return self.size_bytes if self.reclaimable_bytes < 0 else self.reclaimable_bytes


@dataclass(frozen=True, slots=True)
class CleanupPlan:
    candidates: tuple[CleanupCandidate, ...]

    @property
    def total_bytes(self) -> int:
        return sum(item.effective_reclaimable_bytes for item in self.candidates)

    @property
    def file_count(self) -> int:
        return sum(item.file_count for item in self.candidates)

    @property
    def directory_count(self) -> int:
        return sum(item.directory_count for item in self.candidates)

    def by_category(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for item in self.candidates:
            totals[item.category] = totals.get(item.category, 0) + item.effective_reclaimable_bytes
        return dict(sorted(totals.items(), key=lambda item: (-item[1], item[0])))


@dataclass(frozen=True, slots=True)
class CleanupResult:
    reclaimed_bytes: int
    removed: tuple[CleanupCandidate, ...]
    skipped: tuple[CleanupCandidate, ...]
    failures: tuple[tuple[CleanupCandidate, str], ...]


@dataclass(frozen=True, slots=True)
class LegacyCleanupProbe:
    candidate_count: int
    estimated_bytes: int

    @property
    def has_candidates(self) -> bool:
        return self.candidate_count > 0


class LegacyStorageMigrationService:
    """Reference-aware migration/cleanup for storage left by pre-v1.3 builds.

    This service deliberately does *not* own or clear provider API/metadata
    caches.  It only examines known binary/staging/update/version locations.
    Full scans remain read-only until ``apply`` is called with explicit ids.
    """

    SAFE = "safe"
    REVIEWED = "reviewed"
    STALE_TEMP_SECONDS = 7 * 24 * 60 * 60
    LOADER_STAGING_GRACE_SECONDS = 60 * 60
    DEFAULT_UNUSED_VERSION_RETENTION_DAYS = 14
    MIN_UNUSED_VERSION_RETENTION_DAYS = 1
    MAX_UNUSED_VERSION_RETENTION_DAYS = 365
    UNUSED_VERSION_RETENTION_SECONDS = DEFAULT_UNUSED_VERSION_RETENTION_DAYS * 24 * 60 * 60
    UNREFERENCED_CONTENT_RETENTION_SECONDS = 14 * 24 * 60 * 60

    @classmethod
    def probe(cls, *, now: float | None = None, unused_version_retention_days: int | None = None) -> LegacyCleanupProbe:
        """Lightweight startup probe that only checks whether cleanup exists.

        The startup path intentionally avoids recursive size calculation and
        hashing.  Exact item counts and bytes are produced only by ``scan``
        after the user opens the cleanup review.
        """

        current_time = time.time() if now is None else float(now)
        count = 0

        for root in cls._loader_staging_roots():
            if not root.is_dir():
                continue
            count += sum(
                1
                for child in cls._safe_children(root)
                if child.is_dir() and cls._older_than(child, current_time, cls.LOADER_STAGING_GRACE_SECONDS)
            )

        count += len(cls._old_update_directories())

        count += len(cls._unused_version_jar_paths(current_time, unused_version_retention_days))
        count += len(cls._orphan_instance_residue_paths())

        references, provider_references_reliable = cls._provider_references()
        if provider_references_reliable:
            for provider, root in cls._provider_artifact_roots():
                if not root.is_dir():
                    continue
                for project_dir in cls._safe_children(root):
                    if not project_dir.is_dir():
                        continue
                    for version_dir in cls._safe_children(project_dir):
                        if not version_dir.is_dir():
                            continue
                        if (provider, project_dir.name, version_dir.name) in references:
                            continue
                        if cls._older_than(version_dir, current_time, cls.UNREFERENCED_CONTENT_RETENTION_SECONDS):
                            count += 1

        store_root = Paths.CACHE_ROOT / "content-store" / "sha256"
        if store_root.is_dir():
            for prefix in cls._safe_children(store_root):
                if not prefix.is_dir():
                    continue
                for blob in cls._safe_children(prefix):
                    if not blob.is_file() or not cls._older_than(blob, current_time, cls.UNREFERENCED_CONTENT_RETENTION_SECONDS):
                        continue
                    try:
                        if int(blob.stat().st_nlink) <= 1:
                            count += 1
                    except OSError:
                        continue

        return LegacyCleanupProbe(candidate_count=count, estimated_bytes=0)

    @classmethod
    def scan(cls, *, now: float | None = None, unused_version_retention_days: int | None = None) -> CleanupPlan:
        current_time = time.time() if now is None else float(now)
        candidates: list[CleanupCandidate] = []
        candidates.extend(cls._scan_loader_staging(current_time))
        candidates.extend(cls._old_update_candidates(lightweight=False))
        candidates.extend(cls._scan_unused_versions(current_time, unused_version_retention_days))
        candidates.extend(cls._scan_orphan_instance_residue())
        candidates.extend(cls._scan_unreferenced_provider_artifacts(current_time))
        candidates.extend(cls._scan_stale_temp(current_time))
        candidates.extend(cls._scan_unreferenced_content_store(current_time))
        unique: dict[str, CleanupCandidate] = {}
        for item in candidates:
            try:
                key = str(item.path.resolve(strict=False)).casefold()
            except OSError:
                key = str(item.path).casefold()
            previous = unique.get(key)
            if previous is None or item.size_bytes > previous.size_bytes:
                unique[key] = item
        filtered = cls._without_descendant_candidates(tuple(unique.values()))
        return CleanupPlan(tuple(sorted(filtered, key=lambda item: (-item.size_bytes, item.category, str(item.path).casefold()))))

    @classmethod
    def apply(cls, plan: CleanupPlan, candidate_ids: Iterable[str] | None = None, *, unused_version_retention_days: int | None = None) -> CleanupResult:
        selected = {str(value) for value in candidate_ids} if candidate_ids is not None else {item.candidate_id for item in plan.candidates}
        latest = {item.candidate_id: item for item in cls.scan(unused_version_retention_days=unused_version_retention_days).candidates}
        removed: list[CleanupCandidate] = []
        skipped: list[CleanupCandidate] = []
        failures: list[tuple[CleanupCandidate, str]] = []
        reclaimed = 0

        for original in plan.candidates:
            if original.candidate_id not in selected:
                continue
            current = latest.get(original.candidate_id)
            if current is None or not cls._same_candidate(original, current):
                skipped.append(original)
                continue
            if current.category == "orphan_instance_residue":
                if not cls._is_legacy_orphan_instance_directory(current.path):
                    skipped.append(original)
                    continue
            elif cls._is_protected_path(current.path):
                skipped.append(original)
                continue
            try:
                if current.path.is_dir():
                    shutil.rmtree(current.path)
                else:
                    current.path.unlink(missing_ok=True)
                reclaimed += current.effective_reclaimable_bytes
                removed.append(current)
            except OSError as error:
                failures.append((current, str(error)))

        return CleanupResult(reclaimed_bytes=reclaimed, removed=tuple(removed), skipped=tuple(skipped), failures=tuple(failures))

    @classmethod
    def _scan_loader_staging(cls, now: float) -> list[CleanupCandidate]:
        output: list[CleanupCandidate] = []
        for root in cls._loader_staging_roots():
            if not root.is_dir():
                continue
            loader = root.parent.name
            for child in cls._safe_children(root):
                if not child.is_dir() or not cls._older_than(child, now, cls.LOADER_STAGING_GRACE_SECONDS):
                    continue
                output.append(cls._candidate(
                    child,
                    "loader_staging",
                    f"Completed legacy {loader.title()} installer workspace. v1.3 rebuilds staging as temporary data.",
                    cls.SAFE,
                ))
        return output

    @classmethod
    def _old_update_directories(cls) -> list[Path]:
        root = Paths.CACHE_ROOT / "updates" / "downloads"
        if not root.is_dir():
            return []
        releases = [child for child in cls._safe_children(root) if child.is_dir()]
        if not releases:
            return []
        protected = {VERSION_TAG.casefold()}
        rollback = cls._newest_release_directory([item for item in releases if item.name.casefold() not in protected])
        if rollback is not None:
            protected.add(rollback.name.casefold())
        return [child for child in releases if child.name.casefold() not in protected]

    @staticmethod
    def _provider_artifact_roots() -> tuple[tuple[str, Path], ...]:
        return (
            ("curseforge", Paths.CACHE_ROOT / "content" / "curseforge" / "files"),
            ("modrinth", Paths.CACHE_ROOT / "content" / "modrinth" / "files"),
        )

    @classmethod
    def _old_update_candidates(cls, *, lightweight: bool) -> list[CleanupCandidate]:
        releases = cls._old_update_directories()
        output: list[CleanupCandidate] = []
        for child in releases:
            if lightweight:
                size, files, directories = cls._path_size(child, count_items=False)
                output.append(cls._candidate_from_stats(
                    child,
                    "old_launcher_update",
                    "Superseded launcher update package; current and one rollback release are retained.",
                    cls.SAFE,
                    size,
                    files,
                    directories,
                ))
            else:
                output.append(cls._candidate(
                    child,
                    "old_launcher_update",
                    "Superseded launcher update package; current and one rollback release are retained.",
                    cls.SAFE,
                ))
        return output

    @classmethod
    def _scan_unused_versions(cls, now: float, retention_days: int | None) -> list[CleanupCandidate]:
        normalized_days = cls.normalize_unused_version_retention_days(retention_days)
        return [
            cls._candidate(
                jar_path,
                "unused_minecraft_version_jar",
                f"No installed instance or loader inheritance chain references this Minecraft version JAR, and it has been unused for at least {normalized_days} days. Version metadata is retained for future restore/download.",
                cls.REVIEWED,
            )
            for jar_path in cls._unused_version_jar_paths(now, normalized_days)
        ]

    @classmethod
    def _unused_version_jar_paths(cls, now: float, retention_days: int | None = None) -> list[Path]:
        root = Paths.CACHE_ROOT / "versions"
        if not root.is_dir():
            return []
        retention_seconds = cls.normalize_unused_version_retention_days(retention_days) * 24 * 60 * 60
        required, reliable = cls._referenced_version_directories()
        if not reliable:
            return []
        output: list[Path] = []
        for version_dir in cls._safe_children(root):
            if not version_dir.is_dir() or version_dir.name.casefold() in required:
                continue
            jar_path = version_dir / f"{version_dir.name}.jar"
            if not jar_path.is_file() or not cls._older_than(jar_path, now, retention_seconds):
                continue
            output.append(jar_path)
        return output

    @classmethod
    def _scan_orphan_instance_residue(cls) -> list[CleanupCandidate]:
        return [
            cls._candidate(
                path,
                "orphan_instance_residue",
                "Legacy instance residue has no instance metadata or registry reference and contains only known post-deletion .mcw/crash-reports data.",
                cls.REVIEWED,
            )
            for path in cls._orphan_instance_residue_paths()
        ]

    @classmethod
    def _orphan_instance_residue_paths(cls) -> list[Path]:
        root = Paths.INSTANCES_ROOT
        if not root.is_dir():
            return []
        registry_references, registry_reliable = cls._instance_registry_references()
        if not registry_reliable:
            return []
        return [
            child
            for child in cls._safe_children(root)
            if cls._is_legacy_orphan_instance_directory(child, registry_references)
        ]

    @classmethod
    def _scan_unreferenced_provider_artifacts(cls, now: float) -> list[CleanupCandidate]:
        references, reliable = cls._provider_references()
        if not reliable:
            return []
        output: list[CleanupCandidate] = []
        for provider, root in cls._provider_artifact_roots():
            if not root.is_dir():
                continue
            for project_dir in cls._safe_children(root):
                if not project_dir.is_dir():
                    continue
                for version_dir in cls._safe_children(project_dir):
                    if not version_dir.is_dir():
                        continue
                    identity = (provider, project_dir.name, version_dir.name)
                    if identity in references:
                        continue
                    if not cls._older_than(version_dir, now, cls.UNREFERENCED_CONTENT_RETENTION_SECONDS):
                        continue
                    output.append(cls._candidate(
                        version_dir,
                        "unreferenced_provider_content",
                        f"No installed instance references this {provider.title()} binary artifact version. Provider API metadata cache is not included.",
                        cls.REVIEWED,
                    ))
        return output

    @classmethod
    def _scan_unreferenced_content_store(cls, now: float) -> list[CleanupCandidate]:
        root = Paths.CACHE_ROOT / "content-store" / "sha256"
        if not root.is_dir():
            return []
        output: list[CleanupCandidate] = []
        for prefix in cls._safe_children(root):
            if not prefix.is_dir():
                continue
            for blob in cls._safe_children(prefix):
                if not blob.is_file() or not cls._older_than(blob, now, cls.UNREFERENCED_CONTENT_RETENTION_SECONDS):
                    continue
                try:
                    link_count = max(1, int(blob.stat().st_nlink))
                except OSError:
                    continue
                if link_count > 1:
                    continue
                output.append(cls._candidate(
                    blob,
                    "unreferenced_content_store",
                    "Shared binary blob has no remaining hardlink references and is past the retention window.",
                    cls.SAFE,
                ))
        return output

    @classmethod
    def _scan_stale_temp(cls, now: float) -> list[CleanupCandidate]:
        roots = (
            Paths.CACHE_ROOT / "downloads",
            Paths.CACHE_ROOT / "updates" / "staging",
            Paths.CACHE_ROOT / "content" / "modrinth" / "staging",
            Paths.CACHE_ROOT / "content" / "optifine" / "staging",
        )
        output: list[CleanupCandidate] = []
        for root in roots:
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                try:
                    if path.is_symlink():
                        continue
                except OSError:
                    continue
                name = path.name.casefold()
                is_temp = path.is_file() and (name.endswith((".part", ".tmp", ".temp", ".download")) or ".installing" in name)
                is_stale_update_dir = path.is_dir() and root.name == "staging" and path.parent == root
                if not is_temp and not is_stale_update_dir:
                    continue
                if not cls._older_than(path, now, cls.STALE_TEMP_SECONDS):
                    continue
                output.append(cls._candidate(
                    path,
                    "stale_temporary_data",
                    "Abandoned temporary/staging data older than the safety retention window.",
                    cls.SAFE,
                ))
        return output

    @classmethod
    def _referenced_version_directories(cls) -> tuple[set[str], bool]:
        required: set[str] = set()
        instances_root = Paths.INSTANCES_ROOT
        if not instances_root.is_dir():
            return required, True
        registry_references, registry_reliable = cls._instance_registry_references()
        if not registry_reliable:
            return set(), False
        for instance_dir in cls._safe_children(instances_root):
            if not instance_dir.is_dir() or instance_dir.name.startswith("."):
                continue
            metadata = cls._read_json(instance_dir / "instance.json")
            if metadata is None:
                if cls._is_legacy_orphan_instance_directory(instance_dir, registry_references):
                    continue
                return set(), False
            version_id = str(metadata.get("version_id") or "").strip()
            raw_loader = metadata.get("mod_loader")
            if not version_id or not isinstance(raw_loader, (list, tuple)) or len(raw_loader) != 2:
                return set(), False
            loader = str(raw_loader[0] or "vanilla").strip().casefold()
            loader_version = str(raw_loader[1] or "-1").strip()
            required.add(version_id.casefold())
            if loader not in {"", "vanilla"} and loader_version not in {"", "-1", "auto"}:
                if loader == "fabric":
                    profile_id = f"fabric-loader-{loader_version}-{version_id}"
                elif loader == "quilt":
                    profile_id = f"quilt-loader-{loader_version}-{version_id}"
                else:
                    profile_id = f"{loader}-{version_id}-{loader_version}"
                required.add(profile_id.casefold())

        # Follow inheritsFrom for every already-protected cached profile.
        changed = True
        versions_root = Paths.CACHE_ROOT / "versions"
        while changed and versions_root.is_dir():
            changed = False
            for name in tuple(required):
                directory = versions_root / name
                if not directory.is_dir():
                    # Original directory case can differ; resolve by casefold.
                    directory = next((item for item in cls._safe_children(versions_root) if item.is_dir() and item.name.casefold() == name), directory)
                if not directory.is_dir():
                    continue
                for json_path in directory.glob("*.json"):
                    data = cls._read_json(json_path)
                    if not isinstance(data, dict):
                        continue
                    inherited = str(data.get("inheritsFrom") or "").strip().casefold()
                    if inherited and inherited not in required:
                        required.add(inherited)
                        changed = True
        return required, True

    @classmethod
    def _provider_references(cls) -> tuple[set[tuple[str, str, str]], bool]:
        references: set[tuple[str, str, str]] = set()
        root = Paths.INSTANCES_ROOT
        if not root.is_dir():
            return references, True
        registry_references, registry_reliable = cls._instance_registry_references()
        if not registry_reliable:
            return set(), False
        for instance_dir in cls._safe_children(root):
            if not instance_dir.is_dir() or instance_dir.name.startswith("."):
                continue
            metadata_path = instance_dir / "instance.json"
            if cls._read_json(metadata_path) is None:
                if cls._is_legacy_orphan_instance_directory(instance_dir, registry_references):
                    continue
                return set(), False
            mcw = instance_dir / ".mcw"
            for path, provider in ((mcw / "curseforge.json", "curseforge"), (mcw / "modrinth.json", "modrinth")):
                data = cls._read_json_optional(path)
                if data is None:
                    continue
                if not isinstance(data, dict):
                    return set(), False
                mods = data.get("mods")
                if isinstance(mods, dict):
                    for project_key, entry in mods.items():
                        if not isinstance(entry, dict):
                            continue
                        project_id = str(entry.get("projectId") or project_key).strip()
                        version_id = str(entry.get("fileId") if provider == "curseforge" else entry.get("versionId") or "").strip()
                        if project_id and version_id:
                            references.add((provider, project_id, version_id))

            for path, provider in ((mcw / "curseforge-pack.json", "curseforge"), (mcw / "modrinth-pack.json", "modrinth")):
                data = cls._read_json_optional(path)
                if data is None:
                    continue
                if not isinstance(data, dict):
                    return set(), False
                project_id = str(data.get("projectId") or "").strip()
                version_id = str(data.get("fileId") if provider == "curseforge" else data.get("versionId") or "").strip()
                if project_id and version_id:
                    references.add((provider, project_id, version_id))
                managed = data.get("managedFiles")
                if isinstance(managed, list):
                    for entry in managed:
                        if not isinstance(entry, dict):
                            continue
                        item_project = str(entry.get("projectId") or "").strip()
                        item_version = str(entry.get("fileId") if provider == "curseforge" else entry.get("versionId") or "").strip()
                        if item_project and item_version:
                            references.add((provider, item_project, item_version))

            content_registry = cls._read_json_optional(mcw / "content-packs.json")
            if isinstance(content_registry, dict):
                for entry in content_registry.get("entries", []):
                    if not isinstance(entry, dict):
                        continue
                    provider = str(entry.get("provider") or "").strip().casefold()
                    if provider not in {"curseforge", "modrinth"}:
                        continue
                    project_id = str(entry.get("projectId") or "").strip()
                    version_id = str(entry.get("fileId") if provider == "curseforge" else entry.get("versionId") or "").strip()
                    if project_id and version_id:
                        references.add((provider, project_id, version_id))
            elif content_registry is not None:
                return set(), False
        return references, True

    @classmethod
    def _instance_registry_references(cls) -> tuple[set[str], bool]:
        path = Paths.instance_data_path()
        if not path.exists():
            return set(), True
        data = cls._read_json(path)
        if data is None:
            return set(), False
        entries = data.get("instances", [])
        if not isinstance(entries, list):
            return set(), False
        references: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                return set(), False
            raw_path = str(entry.get("instance_dir") or "").strip()
            name = str(entry.get("name") or "").strip()
            candidate = Path(raw_path) if raw_path else Paths.INSTANCES_ROOT / name if name else None
            if candidate is None:
                continue
            try:
                references.add(str(candidate.resolve(strict=False)).casefold())
            except OSError:
                references.add(str(candidate).casefold())
        return references, True

    @classmethod
    def _is_legacy_orphan_instance_directory(cls, path: Path, registry_references: set[str] | None = None) -> bool:
        candidate = Path(path)
        if not candidate.is_dir() or (candidate / "instance.json").exists():
            return False
        try:
            root = Paths.INSTANCES_ROOT.resolve(strict=False)
            resolved = candidate.resolve(strict=False)
            relative = resolved.relative_to(root)
        except (OSError, ValueError):
            return False
        if len(relative.parts) != 1 or relative.name.casefold() in {".runtime", "instances.json"}:
            return False
        if registry_references is None:
            registry_references, reliable = cls._instance_registry_references()
            if not reliable:
                return False
        if str(resolved).casefold() in registry_references:
            return False
        children = cls._safe_children(candidate)
        if not children:
            return False
        allowed = {".mcw", "crash-reports"}
        return all(child.is_dir() and child.name.casefold() in allowed for child in children)

    @classmethod
    def normalize_unused_version_retention_days(cls, value: int | None) -> int:
        try:
            days = int(cls.DEFAULT_UNUSED_VERSION_RETENTION_DAYS if value is None else value)
        except (TypeError, ValueError):
            days = cls.DEFAULT_UNUSED_VERSION_RETENTION_DAYS
        return max(cls.MIN_UNUSED_VERSION_RETENTION_DAYS, min(days, cls.MAX_UNUSED_VERSION_RETENTION_DAYS))

    @staticmethod
    def _read_json(path: Path) -> dict | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError, TypeError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _read_json_optional(path: Path) -> object | None:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return object()

    @classmethod
    def _candidate(cls, path: Path, category: str, reason: str, safety: str) -> CleanupCandidate:
        size, files, directories = cls._path_size(path, count_items=True)
        reclaimable = cls._physical_reclaimable_size(path)
        return cls._candidate_from_stats(path, category, reason, safety, size, files, directories, reclaimable)

    @staticmethod
    def _candidate_from_stats(path: Path, category: str, reason: str, safety: str, size: int, files: int, directories: int, reclaimable: int | None = None) -> CleanupCandidate:
        resolved = str(Path(path).resolve(strict=False))
        candidate_id = hashlib.sha256(f"{category}\0{resolved}".encode("utf-8", errors="surrogatepass")).hexdigest()[:24]
        return CleanupCandidate(
            candidate_id=candidate_id,
            path=Path(path),
            category=category,
            reason=reason,
            safety=safety,
            size_bytes=max(0, int(size)),
            file_count=max(0, int(files)),
            directory_count=max(0, int(directories)),
            reclaimable_bytes=max(0, int(size if reclaimable is None else reclaimable)),
        )

    @staticmethod
    def _path_size(path: Path, *, count_items: bool) -> tuple[int, int, int]:
        try:
            if path.is_file():
                return path.stat().st_size, 1 if count_items else 0, 0
        except OSError:
            return 0, 0, 0
        total = 0
        files = 0
        directories = 1 if count_items else 0
        try:
            for root, dir_names, file_names in os.walk(path, followlinks=False):
                if count_items and Path(root) != path:
                    directories += 1
                for name in file_names:
                    candidate = Path(root) / name
                    try:
                        if candidate.is_symlink():
                            continue
                        total += candidate.stat().st_size
                        if count_items:
                            files += 1
                    except OSError:
                        continue
        except OSError:
            return total, files, directories
        return total, files, directories

    @staticmethod
    def _physical_reclaimable_size(path: Path) -> int:
        candidate = Path(path)
        try:
            if candidate.is_file():
                info = candidate.stat()
                return info.st_size if int(getattr(info, "st_nlink", 1) or 1) <= 1 else 0
        except OSError:
            return 0

        identities: dict[tuple[int, int] | str, tuple[int, int, int]] = {}
        try:
            for root, _dir_names, file_names in os.walk(candidate, followlinks=False):
                for name in file_names:
                    file_path = Path(root) / name
                    try:
                        if file_path.is_symlink():
                            continue
                        info = file_path.stat()
                    except OSError:
                        continue
                    inode = int(getattr(info, "st_ino", 0) or 0)
                    device = int(getattr(info, "st_dev", 0) or 0)
                    key = (device, inode) if inode else str(file_path.resolve(strict=False)).casefold()
                    size, links, internal = identities.get(
                        key,
                        (int(info.st_size), max(1, int(getattr(info, "st_nlink", 1) or 1)), 0),
                    )
                    identities[key] = (size, links, internal + 1)
        except OSError:
            return 0

        reclaimable = 0
        for size, links, internal in identities.values():
            if internal >= links:
                reclaimable += size
        return reclaimable

    @staticmethod
    def _safe_children(root: Path) -> list[Path]:
        try:
            return list(root.iterdir())
        except OSError:
            return []

    @staticmethod
    def _older_than(path: Path, now: float, seconds: int) -> bool:
        try:
            return now - path.stat().st_mtime >= max(0, int(seconds))
        except OSError:
            return False

    @staticmethod
    def _loader_staging_roots() -> tuple[Path, ...]:
        return (
            Paths.CACHE_ROOT / "modloaders" / "forge" / "staging",
            Paths.CACHE_ROOT / "modloaders" / "neoforge" / "staging",
        )

    @classmethod
    def _is_protected_path(cls, path: Path) -> bool:
        candidate = Path(path).resolve(strict=False)
        protected_roots = (
            Paths.ACCOUNTS_ROOT,
            Paths.BACKUPS_ROOT,
            Paths.RUNTIMES_ROOT,
            Paths.CACHE_ROOT / "assets",
            Paths.CACHE_ROOT / "libraries",
            Paths.CACHE_ROOT / "content" / "curseforge" / "api-v2",
            Paths.CACHE_ROOT / "content" / "curseforge" / "api",
            Paths.CACHE_ROOT / "content" / "modrinth" / "api",
            Paths.CACHE_ROOT / "content" / "ftb" / "api-v1",
            Paths.CACHE_ROOT / "content" / "atlauncher" / "api",
        )
        for root in protected_roots:
            try:
                candidate.relative_to(Path(root).resolve(strict=False))
                return True
            except ValueError:
                continue
        # Never remove anything from an instance directory through legacy cache cleanup.
        try:
            candidate.relative_to(Paths.INSTANCES_ROOT.resolve(strict=False))
            return True
        except ValueError:
            return False

    @classmethod
    def _without_descendant_candidates(cls, candidates: tuple[CleanupCandidate, ...]) -> tuple[CleanupCandidate, ...]:
        ordered = sorted(candidates, key=lambda item: (len(item.path.resolve(strict=False).parts), -item.size_bytes))
        kept: list[CleanupCandidate] = []
        roots: list[Path] = []
        for item in ordered:
            resolved = item.path.resolve(strict=False)
            covered = False
            for root in roots:
                try:
                    resolved.relative_to(root)
                    covered = True
                    break
                except ValueError:
                    continue
            if covered:
                continue
            kept.append(item)
            if item.path.is_dir():
                roots.append(resolved)
        return tuple(kept)

    @staticmethod
    def _same_candidate(first: CleanupCandidate, second: CleanupCandidate) -> bool:
        try:
            same_path = first.path.resolve(strict=False) == second.path.resolve(strict=False)
        except OSError:
            same_path = first.path == second.path
        return same_path and first.category == second.category and first.size_bytes == second.size_bytes and first.file_count == second.file_count and first.directory_count == second.directory_count and first.effective_reclaimable_bytes == second.effective_reclaimable_bytes

    @staticmethod
    def _newest_release_directory(paths: list[Path]) -> Path | None:
        if not paths:
            return None

        def key(path: Path) -> tuple[tuple[int, ...], int, str]:
            numbers = tuple(int(value) for value in re.findall(r"\d+", path.name))
            prerelease = 0 if any(marker in path.name.casefold() for marker in ("alpha", "beta", "rc")) else 1
            return numbers, prerelease, path.name.casefold()

        return max(paths, key=key)
