from __future__ import annotations

from dataclasses import replace as dataclass_replace
from pathlib import Path
from typing import Iterable
import json
import re
import shutil
import tomllib
import zipfile

from src.core.fs.paths import Paths
from src.core.instance.errors import InstanceModChangeBlockedError
from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.mod.mod_provenance_registry import ModProvenanceRegistry
from src.models.instance.instance import Instance
from src.models.mod.mod_info import ModInfo


class ModManager:
    DISABLED_SUFFIX = ".disabled"
    _INVALID_STATUSES = {"Broken JAR", "Not a mod", "Broken metadata", "Unverified"}

    @staticmethod
    def mods_dir(instance: Instance) -> Path:
        return Paths.instance_mods_dir(instance)

    @staticmethod
    def list_mods(instance: Instance) -> list[ModInfo]:
        directory = ModManager.mods_dir(instance)
        paths = [path for path in directory.iterdir() if path.is_file() and ModManager._is_mod_file(path)]
        loader_name, _ = ModLoaderManager.normalize(instance.mod_loader)
        provenance = ModProvenanceRegistry.entries_by_file(instance)
        mods: list[ModInfo] = []
        for path in paths:
            mod = ModManager.read_mod(path, preferred_loader=loader_name)
            source = provenance.get(mod.file_name.casefold())
            if isinstance(source, dict):
                mod = dataclass_replace(
                    mod,
                    source=str(source.get("provider") or "unknown").strip().casefold(),
                    source_project_id=str(source.get("projectId") or "").strip(),
                    source_version_id=str(source.get("versionId") or "").strip(),
                    source_file_id=str(source.get("fileId") or "").strip(),
                    managed_by_modpack=bool(source.get("managedByModpack", False)),
                    source_pack_provider=str(source.get("packProvider") or "").strip().casefold(),
                )
            mods.append(mod)
        return sorted(mods, key=lambda mod: (not mod.enabled, mod.name.casefold(), mod.file_name.casefold()))

    @staticmethod
    def add_mods(instance: Instance, source_paths: Iterable[Path], replace: bool = False, launch_lock_token: str | None = None, allow_unverified: bool = False) -> list[ModInfo]:
        ModManager._ensure_modifiable(instance, launch_lock_token)
        destination_dir = ModManager.mods_dir(instance)
        installed = ModManager.list_mods(instance)
        added: list[ModInfo] = []

        for source_value in source_paths:
            source = Path(source_value)
            if not source.is_file() or source.suffix.lower() != ".jar":
                raise RuntimeError(f"Mod file must be a .jar file: {source.name}")

            loader_name, _ = ModLoaderManager.normalize(instance.mod_loader)
            metadata = ModManager.read_mod(source, preferred_loader=loader_name)
            ModManager.validate_mod_for_instance(instance, metadata, allow_unverified=allow_unverified)

            destination = destination_dir / source.name
            disabled_destination = destination.with_name(destination.name + ModManager.DISABLED_SUFFIX)
            source_resolved = source.resolve()
            destination_resolved = destination.resolve()

            if source_resolved == destination_resolved:
                if not replace:
                    raise FileExistsError(f"Mod already exists: {source.name}")
                added.append(ModManager.read_mod(destination, preferred_loader=loader_name))
                continue

            same_id = [
                mod for mod in installed
                if mod.mod_id != "unknown" and mod.mod_id.casefold() == metadata.mod_id.casefold() and mod.path.resolve() != source_resolved
            ]
            file_conflicts = [path for path in (destination, disabled_destination) if path.exists()]
            if (same_id or file_conflicts) and not replace:
                if same_id:
                    files = ", ".join(mod.file_name for mod in same_id)
                    raise FileExistsError(f"Mod ID '{metadata.mod_id}' is already installed as: {files}")
                raise FileExistsError(f"Mod already exists: {source.name}")

            temporary_path = destination.with_name(destination.name + ".part")
            try:
                shutil.copy2(source, temporary_path)
                copied = ModManager.read_mod(temporary_path, preferred_loader=loader_name)
                ModManager.validate_mod_for_instance(instance, copied, allow_unverified=allow_unverified)

                for conflict in same_id:
                    conflict.path.unlink(missing_ok=True)
                disabled_destination.unlink(missing_ok=True)
                temporary_path.replace(destination)
            finally:
                temporary_path.unlink(missing_ok=True)

            installed = [mod for mod in installed if mod.mod_id.casefold() != metadata.mod_id.casefold()]
            installed_mod = ModManager.read_mod(destination, preferred_loader=loader_name)
            installed.append(installed_mod)
            added.append(installed_mod)

        return added

    @staticmethod
    def remove_mods(instance: Instance, paths: Iterable[Path]) -> None:
        ModManager._ensure_modifiable(instance)
        directory = ModManager.mods_dir(instance).resolve()

        removed_names: list[str] = []
        for path in paths:
            candidate = Path(path).resolve()
            if candidate.parent != directory:
                raise RuntimeError("Refusing to remove a file outside the instance mods folder.")
            removed_names.append(candidate.name)
            candidate.unlink(missing_ok=True)
        ModProvenanceRegistry.remove_by_filenames(instance, removed_names)

    @staticmethod
    def set_enabled(instance: Instance, paths: Iterable[Path], enabled: bool) -> list[ModInfo]:
        ModManager._ensure_modifiable(instance)
        directory = ModManager.mods_dir(instance).resolve()
        loader_name, _ = ModLoaderManager.normalize(instance.mod_loader)
        changed: list[ModInfo] = []

        for path in paths:
            source = Path(path).resolve()
            if source.parent != directory or not source.exists():
                raise RuntimeError("Mod file no longer exists in this instance.")

            currently_enabled = not source.name.endswith(ModManager.DISABLED_SUFFIX)
            if currently_enabled == enabled:
                changed.append(ModManager.read_mod(source, preferred_loader=loader_name))
                continue

            target = source.with_name(source.name[:-len(ModManager.DISABLED_SUFFIX)]) if enabled else source.with_name(source.name + ModManager.DISABLED_SUFFIX)
            if target.exists():
                raise FileExistsError(f"Cannot change mod state because '{target.name}' already exists.")

            source.replace(target)
            changed.append(ModManager.read_mod(target, preferred_loader=loader_name))

        return changed

    @staticmethod
    def read_mod(path: Path, preferred_loader: str = "", provider_version: str = "") -> ModInfo:
        path = Path(path)
        enabled = not path.name.endswith(ModManager.DISABLED_SUFFIX)
        file_name = path.name[:-len(ModManager.DISABLED_SUFFIX)] if not enabled else path.name
        normalized_preference = str(preferred_loader).strip().casefold()

        try:
            with zipfile.ZipFile(path, "r") as archive:
                names = set(archive.namelist())
                manifest = ModManager._manifest_attributes(archive.read("META-INF/MANIFEST.MF")) if "META-INF/MANIFEST.MF" in names else {}
                has_fabric = "fabric.mod.json" in names
                has_quilt = "quilt.mod.json" in names
                has_forge = "META-INF/mods.toml" in names

                if has_quilt and (normalized_preference == ModLoaderManager.QUILT or not has_fabric):
                    return ModManager._read_quilt_mod(path, file_name, enabled, archive.read("quilt.mod.json"), manifest, provider_version)
                if has_fabric and has_forge:
                    return ModManager._read_universal_fabric_forge_mod(
                        path,
                        file_name,
                        enabled,
                        archive.read("fabric.mod.json"),
                        archive.read("META-INF/mods.toml"),
                        normalized_preference,
                        manifest,
                        provider_version,
                    )
                if has_fabric:
                    fabric = ModManager._read_fabric_mod(path, file_name, enabled, archive.read("fabric.mod.json"), manifest, provider_version)
                    if normalized_preference == ModLoaderManager.QUILT:
                        return dataclass_replace(fabric, loader="quilt", metadata_format="fabric.mod.json (Quilt compatibility)")
                    return fabric
                if has_quilt:
                    return ModManager._read_quilt_mod(path, file_name, enabled, archive.read("quilt.mod.json"), manifest, provider_version)
                if "META-INF/neoforge.mods.toml" in names:
                    return ModManager._read_forge_mod(path, file_name, enabled, archive.read("META-INF/neoforge.mods.toml"), loader="neoforge", metadata_format="neoforge.mods.toml", manifest=manifest, provider_version=provider_version)
                if has_forge:
                    loader = ModLoaderManager.NEOFORGE if normalized_preference == ModLoaderManager.NEOFORGE else ModLoaderManager.FORGE
                    return ModManager._read_forge_mod(path, file_name, enabled, archive.read("META-INF/mods.toml"), loader=loader, metadata_format="mods.toml", manifest=manifest, provider_version=provider_version)
                if "mcmod.info" in names:
                    return ModManager._read_legacy_forge_mod(path, file_name, enabled, archive.read("mcmod.info"))
                fml_mod_type = str(manifest.get("fmlmodtype") or "").strip().upper()
                if fml_mod_type in {"LANGPROVIDER", "LIBRARY", "GAMELIBRARY"}:
                    loader = normalized_preference if normalized_preference in ModLoaderManager.FORGE_FAMILY else ModLoaderManager.FORGE
                    label = {
                        "LANGPROVIDER": f"{loader.title()} language provider",
                        "LIBRARY": f"{loader.title()} managed library",
                        "GAMELIBRARY": f"{loader.title()} game library",
                    }[fml_mod_type]
                    return ModInfo(
                        path=path,
                        file_name=file_name,
                        enabled=enabled,
                        mod_id="unknown",
                        name=Path(file_name).stem,
                        version=str(manifest.get("implementation-version") or manifest.get("specification-version") or provider_version or "Unknown").strip(),
                        loader=loader,
                        metadata_format=f"MANIFEST.MF:FMLModType={fml_mod_type}",
                        status="Ready",
                        description=label,
                    )
                has_java_content = any(name.endswith(".class") for name in names)
                status = "Unverified" if manifest or has_java_content else "Not a mod"
                return ModManager._invalid_mod(
                    path,
                    file_name,
                    enabled,
                    status,
                    "No quilt.mod.json, fabric.mod.json, Forge META-INF/mods.toml, NeoForge metadata, mcmod.info, or recognized Forge library metadata was found.",
                )
        except (OSError, zipfile.BadZipFile) as error:
            return ModManager._invalid_mod(path, file_name, enabled, "Broken JAR", str(error))

    @staticmethod
    def _read_universal_fabric_forge_mod(path: Path, file_name: str, enabled: bool, fabric_metadata: bytes, forge_metadata: bytes, preferred_loader: str, manifest: dict[str, str] | None = None, provider_version: str = "") -> ModInfo:
        if preferred_loader == ModLoaderManager.FORGE:
            return ModManager._read_forge_mod(path, file_name, enabled, forge_metadata, loader="forge", metadata_format="mods.toml", manifest=manifest, provider_version=provider_version)
        if preferred_loader == ModLoaderManager.NEOFORGE:
            return ModManager._read_forge_mod(path, file_name, enabled, forge_metadata, loader="neoforge", metadata_format="mods.toml", manifest=manifest, provider_version=provider_version)
        if preferred_loader == ModLoaderManager.FABRIC:
            return ModManager._read_fabric_mod(path, file_name, enabled, fabric_metadata, manifest, provider_version)
        if preferred_loader == ModLoaderManager.QUILT:
            fabric = ModManager._read_fabric_mod(path, file_name, enabled, fabric_metadata, manifest, provider_version)
            return dataclass_replace(fabric, loader="quilt", metadata_format="fabric.mod.json (Quilt compatibility)")

        fabric = ModManager._read_fabric_mod(path, file_name, enabled, fabric_metadata, manifest, provider_version)
        forge = ModManager._read_forge_mod(path, file_name, enabled, forge_metadata, loader="forge", metadata_format="mods.toml", manifest=manifest, provider_version=provider_version)
        fabric_valid = fabric.status not in ModManager._INVALID_STATUSES
        forge_valid = forge.status not in ModManager._INVALID_STATUSES
        if fabric_valid and forge_valid:
            return dataclass_replace(fabric, loader="universal", metadata_format="fabric.mod.json + mods.toml")
        if fabric_valid:
            return fabric
        if forge_valid:
            return forge
        return fabric

    @staticmethod
    def _read_fabric_mod(path: Path, file_name: str, enabled: bool, raw_metadata: bytes, manifest: dict[str, str] | None = None, provider_version: str = "") -> ModInfo:
        try:
            data = json.loads(raw_metadata.decode("utf-8-sig"))
        except (UnicodeError, json.JSONDecodeError) as error:
            return ModManager._invalid_mod(path, file_name, enabled, "Broken JAR", f"Invalid fabric.mod.json: {error}")
        if not isinstance(data, dict):
            return ModManager._invalid_mod(path, file_name, enabled, "Broken JAR", "fabric.mod.json must contain an object.")

        mod_id = str(data.get("id") or "").strip()
        version = ModManager._resolve_mod_version(data.get("version"), manifest, data, provider_version, file_name)
        name = str(data.get("name") or mod_id or Path(file_name).stem).strip()
        environment = str(data.get("environment") or "*").strip()
        status = "Server only" if environment == "server" else "Ready"
        error = "This mod declares a server-only environment." if environment == "server" else ""
        if not mod_id:
            status = "Broken metadata"
            error = "Fabric mod id is missing."
        return ModInfo(
            path=path,
            file_name=file_name,
            enabled=enabled,
            mod_id=mod_id or "unknown",
            name=name,
            version=version,
            loader="fabric",
            metadata_format="fabric.mod.json",
            description=str(data.get("description") or "").strip(),
            environment=environment,
            authors=ModManager._parse_authors(data.get("authors")),
            licenses=ModManager._parse_licenses(data.get("license")),
            dependencies=dict(data.get("depends") or {}) if isinstance(data.get("depends"), dict) else {},
            recommends=dict(data.get("recommends") or {}) if isinstance(data.get("recommends"), dict) else {},
            suggests=dict(data.get("suggests") or {}) if isinstance(data.get("suggests"), dict) else {},
            conflicts=dict(data.get("conflicts") or {}) if isinstance(data.get("conflicts"), dict) else {},
            breaks=dict(data.get("breaks") or {}) if isinstance(data.get("breaks"), dict) else {},
            status=status,
            error=error,
        )

    @staticmethod
    def _read_quilt_mod(path: Path, file_name: str, enabled: bool, raw_metadata: bytes, manifest: dict[str, str] | None = None, provider_version: str = "") -> ModInfo:
        try:
            data = json.loads(raw_metadata.decode("utf-8-sig"))
        except (UnicodeError, json.JSONDecodeError) as error:
            return ModManager._invalid_mod(path, file_name, enabled, "Broken JAR", f"Invalid quilt.mod.json: {error}", loader="quilt", metadata_format="quilt.mod.json")
        if not isinstance(data, dict):
            return ModManager._invalid_mod(path, file_name, enabled, "Broken JAR", "quilt.mod.json must contain an object.", loader="quilt", metadata_format="quilt.mod.json")

        loader_data = data.get("quilt_loader") if isinstance(data.get("quilt_loader"), dict) else {}
        metadata = loader_data.get("metadata") if isinstance(loader_data.get("metadata"), dict) else {}
        minecraft = data.get("minecraft") if isinstance(data.get("minecraft"), dict) else {}
        mod_id = str(loader_data.get("id") or data.get("id") or "").strip()
        version = ModManager._resolve_mod_version(loader_data.get("version") or data.get("version"), manifest, {**data, **loader_data, **metadata}, provider_version, file_name)
        name = str(metadata.get("name") or loader_data.get("name") or mod_id or Path(file_name).stem).strip()
        environment = str(minecraft.get("environment") or data.get("environment") or "*").strip()
        status = "Server only" if environment == "server" else "Ready"
        error = "This mod declares a server-only environment." if environment == "server" else ""
        if not mod_id:
            status = "Broken metadata"
            error = "Quilt mod id is missing."

        dependencies, recommends, suggests, conflicts, breaks = ModManager._quilt_dependencies(loader_data)
        contributors = metadata.get("contributors")
        if isinstance(contributors, dict):
            authors = tuple(str(name).strip() for name in contributors if str(name).strip())
        else:
            authors = ModManager._parse_authors(contributors or metadata.get("authors"))
        return ModInfo(
            path=path,
            file_name=file_name,
            enabled=enabled,
            mod_id=mod_id or "unknown",
            name=name,
            version=version,
            loader="quilt",
            metadata_format="quilt.mod.json",
            description=str(metadata.get("description") or loader_data.get("description") or "").strip(),
            environment=environment,
            authors=authors,
            licenses=ModManager._parse_licenses(metadata.get("license") or data.get("license")),
            dependencies=dependencies,
            recommends=recommends,
            suggests=suggests,
            conflicts=conflicts,
            breaks=breaks,
            status=status,
            error=error,
        )

    @staticmethod
    def _quilt_dependencies(loader_data: dict) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
        buckets: dict[str, dict[str, object]] = {
            "depends": {},
            "recommends": {},
            "suggests": {},
            "conflicts": {},
            "breaks": {},
        }

        def append(kind: str, value: object) -> None:
            target = buckets[kind]
            if isinstance(value, dict):
                for dependency_id, requirement in value.items():
                    normalized = str(dependency_id).strip()
                    if normalized:
                        target[normalized] = requirement if requirement not in (None, "") else "*"
                return
            if not isinstance(value, list):
                return
            for entry in value:
                if isinstance(entry, str):
                    normalized = entry.strip()
                    if normalized:
                        target[normalized] = "*"
                    continue
                if not isinstance(entry, dict):
                    continue
                dependency_id = str(entry.get("id") or "").strip()
                if not dependency_id:
                    continue
                versions = entry.get("versions", entry.get("version", "*"))
                target[dependency_id] = versions if versions not in (None, "") else "*"

        for kind in buckets:
            append(kind, loader_data.get(kind))
        return buckets["depends"], buckets["recommends"], buckets["suggests"], buckets["conflicts"], buckets["breaks"]

    @staticmethod
    def _read_forge_mod(path: Path, file_name: str, enabled: bool, raw_metadata: bytes, loader: str, metadata_format: str, manifest: dict[str, str] | None = None, provider_version: str = "") -> ModInfo:
        try:
            data = tomllib.loads(raw_metadata.decode("utf-8-sig"))
        except (UnicodeError, tomllib.TOMLDecodeError) as error:
            return ModManager._invalid_mod(path, file_name, enabled, "Broken JAR", f"Invalid Forge mods.toml: {error}", loader=loader, metadata_format=metadata_format)

        mods = data.get("mods") if isinstance(data.get("mods"), list) else []
        metadata = next((item for item in mods if isinstance(item, dict)), {})
        mod_id = str(metadata.get("modId") or "").strip()
        name = str(metadata.get("displayName") or mod_id or Path(file_name).stem).strip()
        version = ModManager._resolve_mod_version(metadata.get("version"), manifest, {**data, **metadata}, provider_version, file_name)
        authors = ModManager._parse_authors(metadata.get("authors"))
        license_value = data.get("license") or metadata.get("license")
        if not mod_id:
            return ModManager._invalid_mod(path, file_name, enabled, "Broken metadata", "Forge mod id is missing.", loader=loader, metadata_format=metadata_format)

        dependencies, recommends = ModManager._forge_dependencies(data, mod_id)
        loader_requirement = str(data.get("loaderVersion") or "").strip()
        loader_dependency = "neoforge" if loader == "neoforge" else "forge"
        if loader_requirement:
            dependencies.setdefault(loader_dependency, loader_requirement)

        return ModInfo(
            path=path,
            file_name=file_name,
            enabled=enabled,
            mod_id=mod_id,
            name=name,
            version=version,
            loader=loader,
            metadata_format=metadata_format,
            description=str(metadata.get("description") or "").strip(),
            environment="*",
            authors=authors,
            licenses=ModManager._parse_licenses(license_value),
            dependencies=dependencies,
            recommends=recommends,
            suggests={},
            conflicts={},
            breaks={},
            status="Ready",
            error="",
        )

    @staticmethod
    def _read_legacy_forge_mod(path: Path, file_name: str, enabled: bool, raw_metadata: bytes) -> ModInfo:
        try:
            data = json.loads(raw_metadata.decode("utf-8-sig"))
        except (UnicodeError, json.JSONDecodeError) as error:
            return ModManager._invalid_mod(path, file_name, enabled, "Broken JAR", f"Invalid mcmod.info: {error}", loader="forge", metadata_format="mcmod.info")

        if isinstance(data, dict):
            entries = data.get("modList") if isinstance(data.get("modList"), list) else [data]
        elif isinstance(data, list):
            entries = data
        else:
            entries = []
        metadata = next((item for item in entries if isinstance(item, dict)), {})
        mod_id = str(metadata.get("modid") or metadata.get("modId") or "").strip()
        if not mod_id:
            return ModManager._invalid_mod(path, file_name, enabled, "Broken metadata", "Legacy Forge mod id is missing.", loader="forge", metadata_format="mcmod.info")

        dependencies, recommends = ModManager._legacy_forge_dependencies(metadata)
        minecraft_version = str(metadata.get("mcversion") or "").strip()
        if minecraft_version and minecraft_version.casefold() not in {"unknown", "*"}:
            dependencies.setdefault("minecraft", minecraft_version)

        return ModInfo(
            path=path,
            file_name=file_name,
            enabled=enabled,
            mod_id=mod_id,
            name=str(metadata.get("name") or mod_id).strip(),
            version=str(metadata.get("version") or "Unknown").strip(),
            loader="forge",
            metadata_format="mcmod.info",
            description=str(metadata.get("description") or "").strip(),
            environment="*",
            authors=ModManager._parse_authors(metadata.get("authorList") or metadata.get("authors")),
            licenses=ModManager._parse_licenses(metadata.get("license")),
            dependencies=dependencies,
            recommends=recommends,
            suggests={},
            conflicts={},
            breaks={},
            status="Ready",
            error="",
        )

    @staticmethod
    def _forge_dependencies(data: dict, mod_id: str) -> tuple[dict[str, object], dict[str, object]]:
        required: dict[str, object] = {}
        optional: dict[str, object] = {}
        groups = data.get("dependencies") if isinstance(data.get("dependencies"), dict) else {}
        entries = groups.get(mod_id) if isinstance(groups.get(mod_id), list) else []
        if not entries:
            entries = next((value for value in groups.values() if isinstance(value, list)), [])
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            dependency_id = str(entry.get("modId") or "").strip()
            if not dependency_id or dependency_id.casefold() == mod_id.casefold():
                continue
            requirement = str(entry.get("versionRange") or "*").strip() or "*"
            target = required if bool(entry.get("mandatory", True)) else optional
            target[dependency_id] = requirement
        return required, optional

    @staticmethod
    def _legacy_forge_dependencies(metadata: dict) -> tuple[dict[str, object], dict[str, object]]:
        required: dict[str, object] = {}
        optional: dict[str, object] = {}
        raw_values: list[object] = []
        for key in ("requiredMods", "dependencies", "dependants"):
            value = metadata.get(key)
            if isinstance(value, list):
                raw_values.extend(value)
            elif isinstance(value, str):
                raw_values.extend(part.strip() for part in value.split(";") if part.strip())

        for value in raw_values:
            token = str(value).strip()
            if not token:
                continue
            mandatory = token.casefold().startswith(("required-after:", "required-before:"))
            token = re.sub(r"^(?:required-)?(?:after|before):", "", token, flags=re.IGNORECASE)
            match = re.match(r"(?P<id>[A-Za-z0-9_.-]+)(?:@(?P<range>.+))?", token)
            if match is None:
                continue
            dependency_id = match.group("id")
            requirement = (match.group("range") or "*").strip()
            (required if mandatory else optional)[dependency_id] = requirement
        return required, optional

    @staticmethod
    def validate_mod_for_instance(instance: Instance, mod: ModInfo, allow_unverified: bool = False) -> None:
        if mod.status in ModManager._INVALID_STATUSES and not allow_unverified:
            raise RuntimeError(mod.error or f"'{mod.file_name}' is not a supported Minecraft mod.")
        loader_name, _ = ModLoaderManager.normalize(instance.mod_loader)
        if mod.loader not in {loader_name, "unknown", "universal"} and not allow_unverified:
            expected = loader_name.title()
            actual = mod.loader.title()
            raise RuntimeError(f"'{mod.file_name}' is a {actual} mod and cannot be added to this {expected} instance.")

    @staticmethod
    def compatibility_warning(instance: Instance, mod: ModInfo) -> str:
        loader_name, _ = ModLoaderManager.normalize(instance.mod_loader)
        if mod.status in ModManager._INVALID_STATUSES:
            return mod.error or f"'{mod.file_name}' has no supported mod metadata."
        if mod.loader not in {loader_name, "unknown", "universal"}:
            return f"'{mod.file_name}' declares {mod.loader.title()} metadata but is being installed into a {loader_name.title()} instance."
        return ""

    @staticmethod
    def ensure_modifiable(instance: Instance, launch_lock_token: str | None = None) -> None:
        ModManager._ensure_modifiable(instance, launch_lock_token)

    @staticmethod
    def _ensure_modifiable(instance: Instance, launch_lock_token: str | None = None) -> None:
        loader_name, _ = ModLoaderManager.normalize(instance.mod_loader)
        if loader_name not in ModLoaderManager.MODDED_LOADERS:
            raise RuntimeError("This instance does not use Fabric, Quilt, Forge, or NeoForge.")
        if InstanceRunLock.is_active(instance) and not InstanceRunLock.owns_preparing_lock(instance, launch_lock_token):
            raise InstanceModChangeBlockedError(instance.name)

    @staticmethod
    def _is_mod_file(path: Path) -> bool:
        lower_name = path.name.lower()
        return lower_name.endswith(".jar") or lower_name.endswith(".jar" + ModManager.DISABLED_SUFFIX)

    @staticmethod
    def _parse_authors(value: object) -> tuple[str, ...]:
        if isinstance(value, str):
            return tuple(part.strip() for part in re.split(r"[,;]", value) if part.strip())
        if not isinstance(value, list):
            return ()
        authors: list[str] = []
        for author in value:
            if isinstance(author, str) and author.strip():
                authors.append(author.strip())
            elif isinstance(author, dict):
                name = str(author.get("name") or "").strip()
                if name:
                    authors.append(name)
        return tuple(authors)

    @staticmethod
    def _parse_licenses(value: object) -> tuple[str, ...]:
        if isinstance(value, str) and value.strip():
            return (value.strip(),)
        if isinstance(value, list):
            return tuple(str(item).strip() for item in value if str(item).strip())
        return ()

    @staticmethod
    def _manifest_attributes(raw: bytes) -> dict[str, str]:
        try:
            text = raw.decode("utf-8-sig", errors="replace")
        except (AttributeError, UnicodeError):
            return {}
        unfolded: list[str] = []
        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            if line.startswith(" ") and unfolded:
                unfolded[-1] += line[1:]
            else:
                unfolded.append(line)
        attributes: dict[str, str] = {}
        for line in unfolded:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            normalized = key.strip().casefold()
            if normalized:
                attributes[normalized] = value.strip()
        return attributes

    @staticmethod
    def _resolve_mod_version(raw_version: object, manifest: dict[str, str] | None, properties: dict | None, provider_version: str, file_name: str) -> str:
        raw = str(raw_version or "").strip()
        manifest_values = {str(key).casefold(): str(value).strip() for key, value in dict(manifest or {}).items() if str(value).strip()}
        property_values = {str(key).casefold(): str(value).strip() for key, value in dict(properties or {}).items() if not isinstance(value, (dict, list, tuple)) and str(value).strip()}
        placeholder = re.fullmatch(r"\$\{file\.([^}]+)\}", raw, flags=re.IGNORECASE)
        if raw and placeholder is None:
            return raw
        if placeholder is not None:
            key = placeholder.group(1).strip().casefold()
            candidates: list[str] = []
            if key == "jarversion":
                candidates.extend((manifest_values.get("implementation-version", ""), manifest_values.get("specification-version", "")))
            normalized_keys = {
                key,
                key.replace("_", "-"),
                re.sub(r"(?<!^)(?=[A-Z])", "-", placeholder.group(1)).casefold(),
            }
            for candidate_key in normalized_keys:
                candidates.extend((property_values.get(candidate_key, ""), manifest_values.get(candidate_key, "")))
            resolved = next((value for value in candidates if value and "${file." not in value.casefold()), "")
            if resolved:
                return resolved
        provider = str(provider_version or "").strip()
        if provider and "${file." not in provider.casefold():
            return provider
        stem = Path(file_name).stem
        matches = re.findall(r"(?<![A-Za-z0-9])v?(\d+(?:[._-]\d+)+(?:[-+._A-Za-z0-9]*)?)", stem)
        if matches:
            return matches[-1].replace("_", ".")
        return "Unknown"

    @staticmethod
    def _invalid_mod(path: Path, file_name: str, enabled: bool, status: str, error: str, loader: str = "unknown", metadata_format: str = "unknown") -> ModInfo:
        return ModInfo(path=path, file_name=file_name, enabled=enabled, mod_id="unknown", name=Path(file_name).stem, version="Unknown", loader=loader, metadata_format=metadata_format, status=status, error=error)
