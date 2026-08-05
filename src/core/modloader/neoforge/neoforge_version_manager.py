from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
import hashlib
import json
import shutil

from src.core.fs.paths import Paths
from src.core.minecraft.library_manager import DownloadLibraryManager
from src.core.minecraft.library_rule_manager import LibraryRuleManager
from src.core.minecraft.version_manager import VersionManager
from src.core.modloader.neoforge.neoforge_metadata_client import NeoForgeMetadataClient
from src.core.modloader.forge.legacy_forge_installer import LegacyForgeInstaller
from src.core.modloader.java_installer_runner import ModLoaderJavaRunner
from src.core.network.httpx_downloader import HttpDownloader
from src.core.progress.progress_reporter import ProgressReporter
from src.models.minecraft.version import Version
from src.models.progress.progress_stage import ProgressStage


@dataclass(frozen=True, slots=True)
class _NeoForgeInstallerDownload:
    url: str
    sha1: str
    size: int = 0


class NeoForgeVersionManager:
    CACHE_SCHEMA_VERSION = 1
    _locks: dict[str, Lock] = {}
    _guard = Lock()

    @staticmethod
    def recommended_loader_version(game_version: str) -> str:
        return NeoForgeMetadataClient.recommended_version(game_version)

    @staticmethod
    def load(game_version: str, neoforge_version: str, reporter: ProgressReporter | None = None, preferred_java_path: str | Path | None = None) -> Version:
        return NeoForgeVersionManager.install(VersionManager.load(game_version), neoforge_version, reporter=reporter, preferred_java_path=preferred_java_path)

    @staticmethod
    def install(base_version: Version, neoforge_version: str, reporter: ProgressReporter | None = None, force_refresh: bool = False, preferred_java_path: str | Path | None = None) -> Version:
        loader = str(neoforge_version).strip()
        if not loader:
            raise RuntimeError("Select a Minecraft NeoForge version.")
        cache_path = Paths.neoforge_version_json(base_version.id, loader)
        lock = NeoForgeVersionManager._lock_for(f"{base_version.id}:{loader}")
        with lock:
            if not force_refresh:
                cached = NeoForgeVersionManager._load_cached(cache_path, base_version.id, loader)
                if cached is not None:
                    version = VersionManager._parse_version(cached, cache_path)
                    if version is not None:
                        return version
            if reporter is not None:
                reporter.status(stage=ProgressStage.INSTALLING_MOD_LOADER, message=f"Preparing Minecraft NeoForge {loader}...")
            installer = NeoForgeVersionManager._download_installer(base_version.id, loader, reporter)
            staging = Paths.neoforge_staging_dir(base_version.id, loader)
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            staging.mkdir(parents=True, exist_ok=True)
            NeoForgeVersionManager._prepare_staging(base_version, staging)
            NeoForgeVersionManager._run_installer(base_version, loader, installer, staging, reporter, preferred_java_path)
            profile = NeoForgeVersionManager._find_profile(staging, base_version.id, loader)
            NeoForgeVersionManager._import_libraries(staging, reporter)
            normalized = NeoForgeVersionManager._normalize_libraries(profile)
            merged = NeoForgeVersionManager._merge_profiles(base_version.raw_json, normalized, base_version.id, loader)
            version = VersionManager._parse_version(merged, cache_path)
            if version is None:
                raise RuntimeError("The installed NeoForge profile could not be parsed.")
            issues = NeoForgeVersionManager.validate_installation(version, base_version.id, loader, verify_files=False)
            if issues:
                raise RuntimeError("The installed NeoForge profile is incomplete:\n" + "\n".join(f"- {issue}" for issue in issues))
            NeoForgeVersionManager._write_json(cache_path, merged)
            return version

    @staticmethod
    def repair(base_version: Version, neoforge_version: str, reporter: ProgressReporter | None = None, preferred_java_path: str | Path | None = None) -> Version:
        loader = str(neoforge_version).strip()
        if not loader:
            raise RuntimeError("Select a Minecraft NeoForge version.")
        cache_path = Paths.neoforge_version_json(base_version.id, loader)
        previous = cache_path.read_bytes() if cache_path.is_file() else None
        repair_log = Paths.neoforge_root() / "logs" / f"neoforge-repair-{base_version.id}-{loader}.log"
        repair_log.parent.mkdir(parents=True, exist_ok=True)
        if reporter is not None:
            reporter.status(stage=ProgressStage.INSTALLING_MOD_LOADER, message=f"Repairing Minecraft NeoForge {loader}...")
        try:
            version = NeoForgeVersionManager.install(base_version, loader, reporter=reporter, force_refresh=True, preferred_java_path=preferred_java_path)
            DownloadLibraryManager.load(version, reporter=reporter)
            issues = NeoForgeVersionManager.validate_installation(version, base_version.id, loader, verify_files=True)
            if issues:
                raise RuntimeError("NeoForge repair validation failed:\n" + "\n".join(f"- {issue}" for issue in issues))
            repair_log.write_text(
                f"NeoForge repair completed successfully.\nMinecraft: {base_version.id}\nNeoForge: {loader}\nProfile: {version.id}\n",
                encoding="utf-8",
            )
            if reporter is not None:
                reporter.status(stage=ProgressStage.INSTALLING_MOD_LOADER, message=f"NeoForge {loader} repair completed.")
            return version
        except Exception as error:
            if previous is None:
                cache_path.unlink(missing_ok=True)
            else:
                NeoForgeVersionManager._write_bytes(cache_path, previous)
            repair_log.write_text(
                f"NeoForge repair failed and the previous cached profile was restored.\nMinecraft: {base_version.id}\nNeoForge: {loader}\nError: {error}\n",
                encoding="utf-8",
                errors="replace",
            )
            raise

    @staticmethod
    def _download_installer(game_version: str, neoforge_version: str, reporter: ProgressReporter | None) -> Path:
        path = Paths.neoforge_installer_path(game_version, neoforge_version)
        info = _NeoForgeInstallerDownload(url=NeoForgeMetadataClient.installer_url(game_version, neoforge_version), sha1=NeoForgeMetadataClient.installer_sha1(game_version, neoforge_version))
        return HttpDownloader.download(info, path, max_retry=5, timeout=60.0, reporter=reporter, progress_stage=ProgressStage.DOWNLOADING_MOD_LOADER, progress_message=f"Downloading NeoForge {neoforge_version} installer...")


    @staticmethod
    def _prepare_staging(base_version: Version, staging: Path) -> None:
        """Create the minimal launcher layout expected by NeoForge's client installer."""
        profile_path = staging / "launcher_profiles.json"
        if not profile_path.exists():
            NeoForgeVersionManager._write_json(profile_path, {"profiles": {}, "selectedProfile": None, "clientToken": "mcw-launcher"})

        version_dir = staging / "versions" / base_version.id
        version_dir.mkdir(parents=True, exist_ok=True)
        NeoForgeVersionManager._write_json(version_dir / f"{base_version.id}.json", deepcopy(base_version.raw_json))

        client = Paths.client(base_version)
        if client.is_file():
            target = version_dir / f"{base_version.id}.jar"
            if not target.is_file() or target.stat().st_size != client.stat().st_size:
                shutil.copy2(client, target)

    @staticmethod
    def _run_installer(base_version: Version, neoforge_version: str, installer: Path, staging: Path, reporter: ProgressReporter | None, preferred_java_path: str | Path | None = None) -> None:
        log_path = Paths.neoforge_root() / "logs" / f"neoforge-{base_version.id}-{neoforge_version}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        if LegacyForgeInstaller.supports(installer):
            result = LegacyForgeInstaller.install(installer, staging, reporter)
            log_path.write_text(
                "Legacy NeoForge installer imported without opening the installer GUI.\n"
                f"Profile: {result.profile_id}\n"
                f"Embedded library: {result.embedded_library}\n",
                encoding="utf-8",
            )
            return

        java_major = int((base_version.java_version or {}).get("majorVersion") or 8)
        if reporter is not None:
            reporter.status(stage=ProgressStage.INSTALLING_MOD_LOADER, message=f"Running NeoForge {neoforge_version} installer...")
        result = ModLoaderJavaRunner.run(
            java_major,
            ["-jar", str(installer), "--installClient", str(staging)],
            staging,
            reporter=reporter,
            preferred_java_path=preferred_java_path,
        )
        output = result.output
        log_path.write_text(output, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            if NeoForgeVersionManager._is_unsupported_install_client(output):
                raise RuntimeError(
                    "This NeoForge installer uses a legacy installation format that MCW could not import. "
                    "Please send the NeoForge installer log so support for this legacy profile can be added.\n"
                    + "\n".join(output.splitlines()[-12:])
                )
            tail = "\n".join((output or "NeoForge installer failed.").splitlines()[-12:])
            raise RuntimeError(f"NeoForge installer exited with code {result.returncode}.\n{tail}")

    @staticmethod
    def _is_unsupported_install_client(output: str) -> bool:
        text = str(output).casefold()
        return "unrecognizedoptionexception" in text and "installclient" in text

    @staticmethod
    def _find_profile(staging: Path, game_version: str, neoforge_version: str) -> dict:
        candidates: list[tuple[Path, dict]] = []
        for path in sorted((staging / "versions").glob("*/*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            profile_id = str(data.get("id") or path.parent.name).strip()
            if profile_id == game_version:
                continue
            if NeoForgeVersionManager._profile_matches_neoforge(data, profile_id, neoforge_version):
                candidates.append((path, data))
        if not candidates:
            raise RuntimeError("NeoForge installer completed without creating a NeoForge launch profile.")
        return candidates[-1][1]

    @staticmethod
    def _profile_matches_neoforge(profile: dict, profile_id: str, neoforge_version: str) -> bool:
        if neoforge_version and neoforge_version in profile_id:
            return True
        for item in profile.get("libraries", []):
            coordinate = str(item.get("name") or "") if isinstance(item, dict) else ""
            if coordinate.startswith("net.neoforged:"):
                return True
        arguments = profile.get("arguments") if isinstance(profile.get("arguments"), dict) else {}
        game_arguments = NeoForgeVersionManager._argument_tokens(arguments.get("game"))
        legacy_arguments = str(profile.get("minecraftArguments") or "")
        return any(value in {"--fml.neoForgeVersion", "--fml.forgeVersion"} for value in game_arguments) or "--fml.neoForgeVersion" in legacy_arguments or "--fml.forgeVersion" in legacy_arguments

    @staticmethod
    def _import_libraries(staging: Path, reporter: ProgressReporter | None) -> None:
        source = staging / "libraries"
        if not source.is_dir():
            raise RuntimeError("NeoForge installer did not create its libraries directory.")
        files = [path for path in source.rglob("*") if path.is_file()]
        total = len(files)
        if reporter is not None:
            reporter.files(stage=ProgressStage.INSTALLING_MOD_LOADER, message="Importing NeoForge libraries...", current=0, total=total)
        for index, path in enumerate(files, start=1):
            target = Paths.libraries() / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.is_file() or target.stat().st_size != path.stat().st_size:
                temporary = target.with_suffix(target.suffix + ".part")
                try:
                    shutil.copy2(path, temporary)
                    if temporary.stat().st_size != path.stat().st_size:
                        raise RuntimeError(f"NeoForge library copy was incomplete: {path.name}")
                    temporary.replace(target)
                finally:
                    temporary.unlink(missing_ok=True)
            if reporter is not None:
                reporter.files(stage=ProgressStage.INSTALLING_MOD_LOADER, message="Importing NeoForge libraries...", current=index, total=total)

    @staticmethod
    def _normalize_libraries(profile: dict) -> dict:
        normalized = deepcopy(profile)
        output: list[dict] = []
        for raw in profile.get("libraries", []):
            if not isinstance(raw, dict):
                continue
            item = deepcopy(raw)
            downloads = item.get("downloads") if isinstance(item.get("downloads"), dict) else {}
            if isinstance(downloads.get("artifact"), dict):
                output.append(item)
                continue
            coordinate = str(item.get("name") or "").strip()
            path = NeoForgeVersionManager._maven_path(coordinate)
            local = Paths.libraries() / path
            repository = NeoForgeVersionManager._library_repository(item, coordinate)
            sha1 = NeoForgeVersionManager._sha1(local) if local.is_file() else NeoForgeVersionManager._legacy_library_sha1(item)
            if not sha1:
                output.append(item)
                continue
            size = local.stat().st_size if local.is_file() else max(0, int(item.get("size") or 0))
            item["downloads"] = {"artifact": {"path": path.as_posix(), "url": repository + path.as_posix(), "sha1": sha1, "size": size}}
            output.append(item)
        normalized["libraries"] = output
        return normalized

    @staticmethod
    def _maven_path(coordinate: str) -> Path:
        raw = str(coordinate).strip()
        extension = "jar"
        if "@" in raw:
            raw, extension = raw.rsplit("@", 1)
            extension = extension.strip() or "jar"
        parts = raw.split(":")
        if len(parts) < 3:
            raise RuntimeError(f"Invalid NeoForge library coordinate: {coordinate}")
        group, artifact, version = parts[:3]
        classifier = parts[3] if len(parts) > 3 and parts[3] else ""
        filename = f"{artifact}-{version}{'-' + classifier if classifier else ''}.{extension}"
        return Path(*group.split("."), artifact, version, filename)

    @staticmethod
    def _legacy_library_sha1(item: dict) -> str:
        values = item.get("checksums") if isinstance(item.get("checksums"), list) else []
        for value in values:
            checksum = str(value).strip().lower()
            if len(checksum) == 40 and all(character in "0123456789abcdef" for character in checksum):
                return checksum
        return ""

    @staticmethod
    def _library_repository(item: dict, coordinate: str) -> str:
        configured = str(item.get("url") or "").strip()
        if configured:
            if configured.startswith("http://files.minecraftforge.net/maven"):
                configured = configured.replace("http://files.minecraftforge.net/maven", "https://maven.minecraftforge.net", 1)
            return configured.rstrip("/") + "/"
        if str(coordinate).startswith("net.neoforged:"):
            return "https://maven.neoforged.net/releases/"
        if str(coordinate).startswith(("net.minecraftforge:", "de.oceanlabs.mcp:")):
            return "https://maven.minecraftforge.net/"
        return "https://libraries.minecraft.net/"

    @staticmethod
    def _merge_profiles(base: dict, profile: dict, game_version: str, neoforge_version: str) -> dict:
        merged = deepcopy(base)
        profile_id = f"neoforge-{game_version}-{neoforge_version}"
        merged["id"] = profile_id
        merged["inheritsFrom"] = game_version
        if profile.get("mainClass"):
            merged["mainClass"] = profile["mainClass"]
        merged["libraries"] = NeoForgeVersionManager._merge_libraries(base.get("libraries", []), profile.get("libraries", []))
        base_arguments = deepcopy(base.get("arguments") or {"game": [], "jvm": []})
        profile_arguments = profile.get("arguments") if isinstance(profile.get("arguments"), dict) else {}
        if profile_arguments:
            base_arguments.setdefault("game", []).extend(deepcopy(profile_arguments.get("game", [])))
            base_arguments.setdefault("jvm", []).extend(deepcopy(profile_arguments.get("jvm", [])))
            merged["arguments"] = base_arguments
        if profile.get("minecraftArguments"):
            existing = str(base.get("minecraftArguments") or "").strip()
            merged["minecraftArguments"] = " ".join(item for item in (existing, str(profile["minecraftArguments"]).strip()) if item)
        if profile.get("javaVersion"):
            merged["javaVersion"] = deepcopy(profile["javaVersion"])
        merged["neoforge"] = {"schemaVersion": NeoForgeVersionManager.CACHE_SCHEMA_VERSION, "gameVersion": game_version, "loaderVersion": neoforge_version}
        return merged

    @staticmethod
    def _merge_libraries(base: list, extra: list) -> list:
        result: list[dict] = []
        positions: dict[str, int] = {}
        for item in [*base, *extra]:
            if not isinstance(item, dict):
                continue
            key = str(item.get("name") or json.dumps(item, sort_keys=True))
            if key in positions:
                result[positions[key]] = deepcopy(item)
            else:
                positions[key] = len(result)
                result.append(deepcopy(item))
        return result

    @staticmethod
    def _load_cached(path: Path, game_version: str, neoforge_version: str) -> dict | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return None
        forge = data.get("neoforge") if isinstance(data.get("neoforge"), dict) else {}
        if forge.get("schemaVersion") != NeoForgeVersionManager.CACHE_SCHEMA_VERSION or forge.get("gameVersion") != game_version or forge.get("loaderVersion") != neoforge_version:
            return None
        if not data.get("mainClass") or not data.get("libraries"):
            return None
        return data


    @staticmethod
    def validate_installation(version: Version, game_version: str, neoforge_version: str, verify_files: bool = True) -> list[str]:
        issues: list[str] = []
        raw = version.raw_json if isinstance(version.raw_json, dict) else {}
        forge = raw.get("neoforge") if isinstance(raw.get("neoforge"), dict) else {}
        if forge.get("gameVersion") != game_version:
            issues.append("The NeoForge profile targets a different Minecraft version.")
        if forge.get("loaderVersion") != neoforge_version:
            issues.append("The NeoForge profile contains a different loader version.")
        if not str(raw.get("mainClass") or "").strip():
            issues.append("The NeoForge launch profile does not define a main class.")

        libraries = raw.get("libraries") if isinstance(raw.get("libraries"), list) else []
        if not NeoForgeVersionManager._has_neoforge_runtime(libraries, raw, neoforge_version):
            issues.append("The NeoForge runtime is missing from the launch profile.")

        if verify_files:
            for item in libraries:
                if not isinstance(item, dict) or not LibraryRuleManager.is_allowed(item):
                    continue
                downloads = item.get("downloads") if isinstance(item.get("downloads"), dict) else {}
                artifact = downloads.get("artifact") if isinstance(downloads.get("artifact"), dict) else {}
                relative = str(artifact.get("path") or "").strip()
                if not relative:
                    continue
                path = Paths.libraries() / Path(relative)
                if not path.is_file():
                    issues.append(f"Missing required library: {relative}")
                    continue
                expected_size = int(artifact.get("size") or 0)
                if expected_size > 0 and path.stat().st_size != expected_size:
                    issues.append(f"Required library has the wrong size: {relative}")
                    continue
                expected_sha1 = str(artifact.get("sha1") or "").strip().lower()
                if expected_sha1 and NeoForgeVersionManager._sha1(path) != expected_sha1:
                    issues.append(f"Required library failed SHA-1 verification: {relative}")
        return issues

    @staticmethod
    def _has_neoforge_runtime(libraries: list, raw: dict, neoforge_version: str) -> bool:
        runtime_artifacts = {"forge", "neoforge", "loader", "fmlloader", "fmlcore", "javafmllanguage", "lowcodelanguage", "mclanguage"}
        for item in libraries:
            if not isinstance(item, dict):
                continue
            coordinate = str(item.get("name") or "").strip()
            parts = coordinate.split(":")
            if len(parts) >= 3 and parts[0] == "net.neoforged" and parts[1] in runtime_artifacts:
                return True

        arguments = raw.get("arguments") if isinstance(raw.get("arguments"), dict) else {}
        game_arguments = NeoForgeVersionManager._argument_tokens(arguments.get("game"))
        for index, value in enumerate(game_arguments[:-1]):
            if value in {"--fml.neoForgeVersion", "--fml.forgeVersion"} and game_arguments[index + 1] == neoforge_version:
                return True

        legacy_arguments = str(raw.get("minecraftArguments") or "")
        return ("--fml.neoForgeVersion" in legacy_arguments or "--fml.forgeVersion" in legacy_arguments) and neoforge_version in legacy_arguments

    @staticmethod
    def _argument_tokens(value: object) -> tuple[str, ...]:
        tokens: list[str] = []

        def collect(item: object) -> None:
            if isinstance(item, str):
                normalized = item.strip()
                if normalized:
                    tokens.append(normalized)
                return
            if isinstance(item, (list, tuple)):
                for child in item:
                    collect(child)
                return
            if isinstance(item, dict):
                collect(item.get("value"))

        collect(value)
        return tuple(tokens)

    @staticmethod
    def _sha1(path: Path) -> str:
        digest = hashlib.sha1(usedforsecurity=False)
        with path.open("rb") as file:
            while chunk := file.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _write_json(path: Path, data: dict) -> None:
        NeoForgeVersionManager._write_bytes(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    @staticmethod
    def _write_bytes(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        try:
            temp.write_bytes(data)
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)

    @staticmethod
    def _lock_for(key: str) -> Lock:
        with NeoForgeVersionManager._guard:
            return NeoForgeVersionManager._locks.setdefault(key, Lock())
