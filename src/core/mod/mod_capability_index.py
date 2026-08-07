from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Iterable
import json
import re
import tomllib
import zipfile

from src.core.mod.mod_manager import ModManager
from src.models.instance.instance import Instance
from src.models.mod.mod_info import ModInfo


@dataclass(frozen=True, slots=True)
class ModCapability:
    mod_id: str
    version: str
    source: str
    owner_file: str
    nested_path: str = ""


class ModCapabilityIndex:
    """Indexes mod IDs supplied by top-level and safely nested JARs.

    Forge/NeoForge Jar-in-Jar dependencies are runtime capabilities, not
    necessarily separate files in ``mods``. Treating only top-level JARs as
    installed causes false missing-dependency errors (for example Flywheel
    embedded in Create). This scanner is intentionally read-only and bounded.
    """

    MAX_NESTED_DEPTH = 3
    MAX_NESTED_JARS_PER_OWNER = 128
    MAX_NESTED_JAR_BYTES = 64 * 1024 * 1024
    MAX_TOTAL_NESTED_BYTES = 192 * 1024 * 1024
    MAX_COMPRESSION_RATIO = 250

    @staticmethod
    def build(instance: Instance, mods: Iterable[ModInfo] | None = None) -> dict[str, tuple[ModCapability, ...]]:
        listed = list(mods) if mods is not None else ModManager.list_mods(instance)
        output: dict[str, list[ModCapability]] = {}

        for mod in listed:
            if not mod.enabled:
                continue
            ModCapabilityIndex._append(
                output,
                ModCapability(
                    mod_id=mod.mod_id,
                    version=mod.version,
                    source="top_level",
                    owner_file=mod.file_name,
                ),
            )
            path = Path(mod.path)
            if not path.is_file():
                continue
            for capability in ModCapabilityIndex._scan_owner(path):
                ModCapabilityIndex._append(output, capability)

        return {key: tuple(values) for key, values in output.items()}

    @staticmethod
    def installed_versions(instance: Instance, mods: Iterable[ModInfo] | None = None) -> dict[str, str]:
        capabilities = ModCapabilityIndex.build(instance, mods)
        selected: dict[str, str] = {}
        for mod_id, entries in capabilities.items():
            versions = [str(entry.version or "").strip() for entry in entries if str(entry.version or "").strip()]
            if versions:
                selected[mod_id] = ModCapabilityIndex._best_version(versions)
        return selected

    @staticmethod
    def provides(path: Path, mod_id: str, preferred_loader: str = "") -> tuple[ModCapability, ...]:
        """Returns capabilities with ``mod_id`` supplied by a candidate JAR."""

        candidate = Path(path)
        if not candidate.is_file():
            return ()
        wanted = ModCapabilityIndex._normalize_id(mod_id)
        if not wanted:
            return ()

        capabilities: list[ModCapability] = []
        top_level = ModManager.read_mod(candidate, preferred_loader=preferred_loader)
        if ModCapabilityIndex._normalize_id(top_level.mod_id) == wanted:
            capabilities.append(ModCapability(top_level.mod_id, top_level.version, "top_level", candidate.name))
        capabilities.extend(
            capability
            for capability in ModCapabilityIndex._scan_owner(candidate)
            if ModCapabilityIndex._normalize_id(capability.mod_id) == wanted
        )
        return tuple(capabilities)

    @staticmethod
    def _scan_owner(path: Path) -> tuple[ModCapability, ...]:
        output: list[ModCapability] = []
        budget = {"count": 0, "bytes": 0}
        try:
            with zipfile.ZipFile(path, "r") as archive:
                ModCapabilityIndex._scan_nested_archive(
                    archive,
                    owner_file=path.name,
                    parent_path="",
                    depth=0,
                    output=output,
                    budget=budget,
                )
        except (OSError, zipfile.BadZipFile, RuntimeError, ValueError):
            return ()
        return tuple(output)

    @staticmethod
    def _scan_nested_archive(archive: zipfile.ZipFile, owner_file: str, parent_path: str, depth: int, output: list[ModCapability], budget: dict[str, int]) -> None:
        if depth >= ModCapabilityIndex.MAX_NESTED_DEPTH:
            return
        names = set(archive.namelist())
        manifest = ModCapabilityIndex._manifest(archive, names)
        for nested_path in ModCapabilityIndex._nested_paths(archive, names, manifest):
            if budget["count"] >= ModCapabilityIndex.MAX_NESTED_JARS_PER_OWNER:
                return
            info = ModCapabilityIndex._safe_info(archive, nested_path)
            if info is None:
                continue
            if info.file_size > ModCapabilityIndex.MAX_NESTED_JAR_BYTES:
                continue
            if budget["bytes"] + info.file_size > ModCapabilityIndex.MAX_TOTAL_NESTED_BYTES:
                return
            if info.compress_size > 0 and info.file_size / info.compress_size > ModCapabilityIndex.MAX_COMPRESSION_RATIO:
                continue
            try:
                raw = archive.read(info)
            except (KeyError, OSError, RuntimeError, zipfile.BadZipFile):
                continue
            budget["count"] += 1
            budget["bytes"] += len(raw)
            full_path = f"{parent_path}!/{nested_path}" if parent_path else nested_path
            try:
                with zipfile.ZipFile(BytesIO(raw), "r") as nested:
                    nested_names = set(nested.namelist())
                    nested_manifest = ModCapabilityIndex._manifest(nested, nested_names)
                    output.extend(ModCapabilityIndex._archive_capabilities(nested, nested_names, nested_manifest, owner_file, full_path))
                    ModCapabilityIndex._scan_nested_archive(
                        nested,
                        owner_file=owner_file,
                        parent_path=full_path,
                        depth=depth + 1,
                        output=output,
                        budget=budget,
                    )
            except (OSError, zipfile.BadZipFile, RuntimeError, ValueError):
                continue

    @staticmethod
    def _archive_capabilities(archive: zipfile.ZipFile, names: set[str], manifest: dict[str, str], owner_file: str, nested_path: str) -> tuple[ModCapability, ...]:
        output: list[ModCapability] = []

        for metadata_path in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"):
            if metadata_path not in names:
                continue
            try:
                data = tomllib.loads(archive.read(metadata_path).decode("utf-8-sig"))
            except (KeyError, UnicodeError, tomllib.TOMLDecodeError):
                continue
            mods = data.get("mods") if isinstance(data.get("mods"), list) else []
            for raw in mods:
                if not isinstance(raw, dict):
                    continue
                mod_id = str(raw.get("modId") or "").strip()
                if not mod_id:
                    continue
                version = ModManager._resolve_mod_version(raw.get("version"), manifest, {**data, **raw}, "", PurePosixPath(nested_path).name)
                output.append(ModCapability(mod_id, version, "embedded", owner_file, nested_path))

        if "fabric.mod.json" in names:
            try:
                data = json.loads(archive.read("fabric.mod.json").decode("utf-8-sig"))
            except (KeyError, UnicodeError, json.JSONDecodeError):
                data = None
            if isinstance(data, dict):
                mod_id = str(data.get("id") or "").strip()
                if mod_id:
                    version = ModManager._resolve_mod_version(data.get("version"), manifest, data, "", PurePosixPath(nested_path).name)
                    output.append(ModCapability(mod_id, version, "embedded", owner_file, nested_path))

        if "quilt.mod.json" in names:
            try:
                data = json.loads(archive.read("quilt.mod.json").decode("utf-8-sig"))
            except (KeyError, UnicodeError, json.JSONDecodeError):
                data = None
            if isinstance(data, dict):
                loader = data.get("quilt_loader") if isinstance(data.get("quilt_loader"), dict) else {}
                mod_id = str(loader.get("id") or data.get("id") or "").strip()
                if mod_id:
                    version = ModManager._resolve_mod_version(loader.get("version") or data.get("version"), manifest, {**data, **loader}, "", PurePosixPath(nested_path).name)
                    output.append(ModCapability(mod_id, version, "embedded", owner_file, nested_path))

        if "mcmod.info" in names:
            try:
                data = json.loads(archive.read("mcmod.info").decode("utf-8-sig"))
            except (KeyError, UnicodeError, json.JSONDecodeError):
                data = None
            if isinstance(data, dict):
                entries = data.get("modList") if isinstance(data.get("modList"), list) else [data]
            elif isinstance(data, list):
                entries = data
            else:
                entries = []
            for raw in entries:
                if not isinstance(raw, dict):
                    continue
                mod_id = str(raw.get("modid") or raw.get("modId") or "").strip()
                if mod_id:
                    output.append(ModCapability(mod_id, str(raw.get("version") or "Unknown").strip(), "embedded", owner_file, nested_path))

        return tuple(output)

    @staticmethod
    def _nested_paths(archive: zipfile.ZipFile, names: set[str], manifest: dict[str, str]) -> tuple[str, ...]:
        candidates: list[str] = []

        if "META-INF/jarjar/metadata.json" in names:
            try:
                payload = json.loads(archive.read("META-INF/jarjar/metadata.json").decode("utf-8-sig"))
            except (KeyError, UnicodeError, json.JSONDecodeError):
                payload = None
            jars = payload.get("jars") if isinstance(payload, dict) and isinstance(payload.get("jars"), list) else []
            for raw in jars:
                if isinstance(raw, dict):
                    candidates.append(str(raw.get("path") or "").strip())

        if "fabric.mod.json" in names:
            try:
                payload = json.loads(archive.read("fabric.mod.json").decode("utf-8-sig"))
            except (KeyError, UnicodeError, json.JSONDecodeError):
                payload = None
            jars = payload.get("jars") if isinstance(payload, dict) and isinstance(payload.get("jars"), list) else []
            for raw in jars:
                if isinstance(raw, dict):
                    candidates.append(str(raw.get("file") or "").strip())

        contained = str(manifest.get("containeddeps") or "").strip()
        if contained:
            candidates.extend(part.strip() for part in re.split(r"[,;\s]+", contained) if part.strip())

        # Forge JarJar always stores artifacts below this directory. Keeping a
        # bounded fallback makes the scanner resilient to missing/older
        # metadata while still avoiding a whole-archive recursive scan.
        candidates.extend(name for name in names if name.casefold().startswith("meta-inf/jarjar/") and name.casefold().endswith(".jar"))

        safe: list[str] = []
        for value in candidates:
            normalized = str(value).replace("\\", "/").strip().lstrip("/")
            pure = PurePosixPath(normalized)
            if not normalized or pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
                continue
            if normalized not in names or not normalized.casefold().endswith(".jar"):
                continue
            if normalized not in safe:
                safe.append(normalized)
        return tuple(safe)

    @staticmethod
    def _safe_info(archive: zipfile.ZipFile, name: str) -> zipfile.ZipInfo | None:
        try:
            info = archive.getinfo(name)
        except KeyError:
            return None
        if info.is_dir() or info.file_size < 0 or info.compress_size < 0:
            return None
        return info

    @staticmethod
    def _manifest(archive: zipfile.ZipFile, names: set[str]) -> dict[str, str]:
        if "META-INF/MANIFEST.MF" not in names:
            return {}
        try:
            return ModManager._manifest_attributes(archive.read("META-INF/MANIFEST.MF"))
        except (KeyError, OSError, RuntimeError):
            return {}

    @staticmethod
    def _append(output: dict[str, list[ModCapability]], capability: ModCapability) -> None:
        mod_id = ModCapabilityIndex._normalize_id(capability.mod_id)
        if not mod_id or mod_id == "unknown":
            return
        bucket = output.setdefault(mod_id, [])
        signature = (capability.version.casefold(), capability.source, capability.owner_file.casefold(), capability.nested_path.casefold())
        if any((item.version.casefold(), item.source, item.owner_file.casefold(), item.nested_path.casefold()) == signature for item in bucket):
            return
        bucket.append(capability)

    @staticmethod
    def _normalize_id(value: str) -> str:
        return str(value or "").strip().casefold()

    @staticmethod
    def _best_version(versions: list[str]) -> str:
        from src.core.mod.mod_compatibility_manager import ModCompatibilityManager

        def key(value: str):
            parsed = ModCompatibilityManager._version_key(value)
            return (parsed is not None, parsed or ((0, 0, 0, 0), 0, ()), value.casefold())

        return max(versions, key=key)
