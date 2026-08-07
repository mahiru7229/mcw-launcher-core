from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Lock
import hashlib
import json

import httpx

from src.core.fs.paths import Paths
from src.core.minecraft.version_manager import VersionManager
from src.core.modloader.fabric.maven_artifact import MavenArtifact
from src.core.modloader.quilt.quilt_meta_client import QuiltMetaClient
from src.core.network.httpx_downloader import HttpDownloader
from src.core.progress.progress_reporter import ProgressReporter
from src.models.minecraft.version import Version
from src.models.modloader.quilt_install_metadata import QuiltInstallMetadata
from src.models.progress.progress_stage import ProgressStage


class QuiltVersionManager:
    CACHE_SCHEMA_VERSION = 2
    MAX_METADATA_WORKERS = 6
    _locks: dict[str, Lock] = {}
    _locks_guard = Lock()

    @staticmethod
    def load(game_version: str, loader_version: str, reporter: ProgressReporter | None = None) -> Version:
        base_version = VersionManager.load(game_version)
        return QuiltVersionManager.install(base_version, loader_version, reporter)

    @staticmethod
    def recommended_loader_version(game_version: str) -> str:
        versions = QuiltMetaClient.list_loader_versions(game_version)
        if not versions:
            raise RuntimeError(f"Quilt Loader is not available for Minecraft {game_version}.")
        stable_versions = [version for version in versions if version.stable]
        if not stable_versions:
            raise RuntimeError(
                f"No stable Quilt Loader is available for Minecraft {game_version}. "
                "Choose an experimental Loader version manually from Manage selected instance."
            )
        recommended = max(stable_versions, key=lambda version: QuiltMetaClient.version_sort_key(version.version))
        return recommended.version

    @staticmethod
    def install(base_version: Version, loader_version: str, reporter: ProgressReporter | None = None, force_refresh: bool = False, repair_libraries: bool = False) -> Version:
        loader_version = loader_version.strip()
        if not loader_version:
            raise RuntimeError("Select a Quilt Loader version.")

        cache_path = Paths.quilt_version_json(base_version.id, loader_version)
        lock = QuiltVersionManager._get_lock(f"{base_version.id}:{loader_version}")
        with lock:
            if not force_refresh:
                cached = QuiltVersionManager._load_cached(cache_path, base_version.raw_json, base_version.id, loader_version)
                if cached is not None:
                    cached_version = VersionManager._parse_version(cached, cache_path)
                    if cached_version is not None:
                        return cached_version

            if reporter is not None:
                action = "Repairing" if force_refresh else "Installing"
                reporter.status(stage=ProgressStage.INSTALLING_MOD_LOADER, message=f"{action} Quilt Loader {loader_version}...")

            metadata = QuiltMetaClient.get_install_metadata(base_version.id, loader_version, force_refresh=force_refresh)
            profile = QuiltMetaClient.get_profile(base_version.id, loader_version, force_refresh=force_refresh)
            QuiltVersionManager._validate_bytecode_support(base_version, loader_version, metadata, profile)
            normalized_profile = QuiltVersionManager._normalize_profile_libraries(profile, reporter=reporter, force_artifact_refresh=repair_libraries)
            merged = QuiltVersionManager._merge_profiles(base_version.raw_json, normalized_profile, metadata)
            QuiltVersionManager._write_json(cache_path, merged)
            version = VersionManager._parse_version(merged, cache_path)
            if version is None:
                raise RuntimeError("Quilt version metadata could not be parsed.")
            return version

    @staticmethod
    def repair(base_version: Version, loader_version: str, reporter: ProgressReporter | None = None) -> Version:
        cache_path = Paths.quilt_version_json(base_version.id, loader_version)
        try:
            cache_path.unlink(missing_ok=True)
        except OSError:
            pass
        return QuiltVersionManager.install(base_version, loader_version, reporter, force_refresh=True, repair_libraries=True)

    @staticmethod
    def components(version: Version) -> tuple[dict, ...]:
        quilt_data = (getattr(version, "raw_json", {}) or {}).get("quilt", {})
        components = quilt_data.get("components", []) if isinstance(quilt_data, dict) else []
        return tuple(item for item in components if isinstance(item, dict))

    @staticmethod
    def _get_lock(key: str) -> Lock:
        with QuiltVersionManager._locks_guard:
            return QuiltVersionManager._locks.setdefault(key, Lock())

    @staticmethod
    def _load_cached(path: Path, base: dict, game_version: str, loader_version: str) -> dict | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        quilt_data = data.get("quilt", {})
        if not isinstance(quilt_data, dict):
            return None
        if quilt_data.get("schemaVersion") != QuiltVersionManager.CACHE_SCHEMA_VERSION:
            return None
        if data.get("inheritsFrom") != game_version:
            return None
        if quilt_data.get("gameVersion") != game_version or quilt_data.get("loaderVersion") != loader_version:
            return None
        if quilt_data.get("baseFingerprint") != QuiltVersionManager._fingerprint(base):
            return None
        components = quilt_data.get("components")
        if not isinstance(components, list) or not components:
            return None
        component_uids = {str(item.get("uid", "")).strip() for item in components if isinstance(item, dict)}
        if "net.minecraft" not in component_uids or "org.quiltmc.quilt-loader" not in component_uids:
            return None
        if not data.get("mainClass") or not data.get("libraries"):
            return None
        return data

    @staticmethod
    def _validate_bytecode_support(base_version: Version, loader_version: str, metadata: QuiltInstallMetadata, profile: dict) -> None:
        try:
            java_major = int((base_version.java_version or {}).get("majorVersion") or 8)
        except (TypeError, ValueError):
            java_major = 8
        required_asm = QuiltVersionManager._required_asm_version(java_major)
        if required_asm is None:
            return

        asm_versions: list[tuple[int, ...]] = []
        asm_labels: list[str] = []
        libraries = [*metadata.libraries, *(profile.get("libraries", []) if isinstance(profile, dict) else [])]
        for library in libraries:
            if not isinstance(library, dict):
                continue
            coordinate = str(library.get("name", "")).strip().split("@", 1)[0]
            parts = coordinate.split(":")
            if len(parts) < 3 or parts[0] != "org.ow2.asm" or parts[1] != "asm":
                continue
            parsed = QuiltVersionManager._numeric_version(parts[2])
            if parsed is not None:
                asm_versions.append(parsed)
                asm_labels.append(parts[2])

        if not asm_versions:
            return
        newest_asm = max(asm_versions)
        if newest_asm >= required_asm:
            return
        detected = max(asm_labels, key=QuiltVersionManager._numeric_version)
        required_label = ".".join(str(part) for part in required_asm)
        raise RuntimeError(
            f"Quilt Loader {loader_version} is too old for Minecraft {base_version.id}. "
            f"It uses ASM {detected}, but Java {java_major} bytecode requires ASM {required_label} or newer. "
            "Choose a newer stable Quilt Loader version."
        )

    @staticmethod
    def _required_asm_version(java_major: int) -> tuple[int, ...] | None:
        if java_major >= 26:
            return 9, 9
        if java_major >= 25:
            return 9, 8
        return None

    @staticmethod
    def _numeric_version(value: str) -> tuple[int, ...] | None:
        parts = str(value).strip().split(".")
        numbers: list[int] = []
        for part in parts:
            digits = "".join(character for character in part if character.isdigit())
            if not digits:
                break
            numbers.append(int(digits))
        return tuple(numbers) if numbers else None

    @staticmethod
    def _normalize_profile_libraries(profile: dict, reporter: ProgressReporter | None = None, force_artifact_refresh: bool = False) -> dict:
        normalized = deepcopy(profile)
        normalized_libraries: list[dict | None] = []
        pending: list[tuple[int, dict, MavenArtifact]] = []
        for library in profile.get("libraries", []):
            if not isinstance(library, dict):
                continue
            item = deepcopy(library)
            artifact_data = item.get("downloads", {}).get("artifact")
            if QuiltVersionManager._valid_artifact_data(artifact_data):
                normalized_libraries.append(item)
                continue
            coordinate = str(item.get("name", "")).strip()
            repository_url = str(item.get("url") or QuiltVersionManager._repository_for_coordinate(coordinate))
            artifact = MavenArtifact.from_coordinate(coordinate, repository_url)
            pending.append((len(normalized_libraries), item, artifact))
            normalized_libraries.append(None)

        metadata_reporter = reporter if len(pending) <= 1 else None

        def resolve(entry: tuple[int, dict, MavenArtifact]) -> tuple[int, dict]:
            index, item, artifact = entry
            sha1, size = QuiltVersionManager._load_artifact_metadata(artifact, force_artifact_refresh, metadata_reporter)
            item["downloads"] = {"artifact": {"path": artifact.path.as_posix(), "sha1": sha1, "size": size, "url": artifact.url}}
            return index, item

        if pending:
            workers = min(QuiltVersionManager.MAX_METADATA_WORKERS, len(pending))
            if workers == 1:
                for index, item in map(resolve, pending):
                    normalized_libraries[index] = item
            else:
                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="quilt-meta") as executor:
                    for index, item in executor.map(resolve, pending):
                        normalized_libraries[index] = item

        normalized["libraries"] = [item for item in normalized_libraries if item is not None]
        return normalized

    @staticmethod
    def _repository_for_coordinate(coordinate: str) -> str:
        normalized = str(coordinate).strip()
        if normalized.startswith("org.quiltmc:"):
            return "https://maven.quiltmc.org/repository/release/"
        if normalized.startswith("net.fabricmc:"):
            return "https://maven.fabricmc.net/"
        return "https://repo.maven.apache.org/maven2/"

    @staticmethod
    def _valid_artifact_data(value: object) -> bool:
        if not isinstance(value, dict) or "size" not in value:
            return False
        sha1 = str(value.get("sha1", "")).strip().lower()
        try:
            size = int(value.get("size", 0))
        except (TypeError, ValueError):
            return False
        return bool(value.get("path") and value.get("url") and size >= 0 and len(sha1) == 40 and all(character in "0123456789abcdef" for character in sha1))

    @staticmethod
    def _load_artifact_metadata(artifact: MavenArtifact, force_artifact_refresh: bool = False, reporter: ProgressReporter | None = None) -> tuple[str, int]:
        client = HttpDownloader.get_client()
        sha1 = ""
        try:
            sha1_response = client.get(artifact.url + ".sha1", timeout=20.0)
            sha1_response.raise_for_status()
            sha1 = sha1_response.text.strip().split()[0].lower()
        except (httpx.HTTPError, IndexError):
            sha1 = ""

        if len(sha1) == 40 and all(character in "0123456789abcdef" for character in sha1):
            size = 0
            try:
                response = client.head(artifact.url, timeout=20.0)
                response.raise_for_status()
                size = int(response.headers.get("Content-Length", 0) or 0)
            except (httpx.HTTPError, ValueError):
                size = 0
            return sha1, size

        library_path = Paths.libraries() / artifact.path
        _, calculated_sha1, size = HttpDownloader.download_and_hash(
            url=artifact.url,
            path=library_path,
            max_retry=3,
            force=force_artifact_refresh,
            reporter=reporter,
            progress_stage=ProgressStage.INSTALLING_MOD_LOADER,
            progress_message=f"Downloading Quilt library {artifact.path.name}...",
        )
        return calculated_sha1, size

    @staticmethod
    def _merge_profiles(base: dict, quilt: dict, metadata: QuiltInstallMetadata) -> dict:
        merged = deepcopy(base)
        game_version = metadata.game.version
        loader_version = metadata.loader.version
        profile_id = str(quilt.get("id") or f"quilt-loader-{loader_version}-{game_version}")
        profile_main_class = str(quilt.get("mainClass", "")).strip()
        if profile_main_class != metadata.main_class:
            raise RuntimeError("Quilt profile main class does not match its installation metadata.")
        if "quilt" not in profile_main_class.casefold():
            raise RuntimeError("Quilt profile does not declare a Quilt launch main class.")

        merged["id"] = profile_id
        merged["inheritsFrom"] = game_version
        merged["mainClass"] = profile_main_class
        merged["type"] = quilt.get("type", base.get("type", "release"))
        merged["libraries"] = QuiltVersionManager._merge_libraries(base.get("libraries", []), quilt.get("libraries", []))
        merged["arguments"] = QuiltVersionManager._merge_arguments(base.get("arguments"), quilt.get("arguments"))

        base_legacy = str(base.get("minecraftArguments", "")).strip()
        quilt_legacy = str(quilt.get("minecraftArguments", "")).strip()
        if base_legacy or quilt_legacy:
            merged["minecraftArguments"] = " ".join(value for value in (base_legacy, quilt_legacy) if value)

        components = [{"uid": metadata.game.uid, "version": metadata.game.version}]
        if metadata.mappings is not None:
            components.append({"uid": metadata.mappings.uid, "version": metadata.mappings.version, "maven": metadata.mappings.maven})
        components.append({"uid": metadata.loader.uid, "version": metadata.loader.version, "maven": metadata.loader.maven})

        quilt_metadata = {
            "schemaVersion": QuiltVersionManager.CACHE_SCHEMA_VERSION,
            "gameVersion": game_version,
            "loaderVersion": loader_version,
            "mappingNamespace": metadata.mappings.uid if metadata.mappings is not None else "named",
            "profileId": profile_id,
            "baseFingerprint": QuiltVersionManager._fingerprint(base),
            "components": components,
        }
        if metadata.mappings is not None:
            quilt_metadata["mappingsVersion"] = metadata.mappings.version
        merged["quilt"] = quilt_metadata
        return merged

    @staticmethod
    def _merge_libraries(base_libraries: list, quilt_libraries: list) -> list:
        merged: list[dict] = []
        indexes: dict[str, int] = {}
        for library in [*base_libraries, *quilt_libraries]:
            if not isinstance(library, dict):
                continue
            key = QuiltVersionManager._library_key(str(library.get("name", "")))
            if key and key in indexes:
                merged[indexes[key]] = deepcopy(library)
                continue
            if key:
                indexes[key] = len(merged)
            merged.append(deepcopy(library))
        return merged

    @staticmethod
    def _library_key(coordinate: str) -> str:
        base_coordinate = coordinate.split("@", 1)[0]
        parts = base_coordinate.split(":")
        if len(parts) < 3:
            return coordinate
        group, artifact = parts[:2]
        classifier = parts[3] if len(parts) > 3 else ""
        return ":".join((group, artifact, classifier))

    @staticmethod
    def _merge_arguments(base_arguments: object, quilt_arguments: object) -> dict:
        base = deepcopy(base_arguments) if isinstance(base_arguments, dict) else {}
        quilt = quilt_arguments if isinstance(quilt_arguments, dict) else {}
        return {"jvm": [*base.get("jvm", []), *quilt.get("jvm", [])], "game": [*base.get("game", []), *quilt.get("game", [])]}

    @staticmethod
    def _fingerprint(data: dict) -> str:
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _write_json(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".part")
        temp_path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(path)
