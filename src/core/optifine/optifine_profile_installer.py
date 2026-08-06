from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess

from src.core.fs.paths import Paths
from src.core.instance.settings_manager import SettingsManager
from src.core.java.java_resolver import JavaResolver
from src.core.minecraft.download_manager import DownloadClientManager
from src.core.minecraft.version_manager import VersionManager
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.minecraft.version import Version
from src.models.progress.progress_stage import ProgressStage


class OptiFineProfileInstaller:
    INSTALL_TIMEOUT_SECONDS = 20 * 60

    @classmethod
    def install(cls, instance: Instance, source_jar: Path, version_id: str, reporter: ProgressReporter | None = None) -> Version:
        base = VersionManager.load(instance.version_id)
        if reporter is not None:
            reporter.status(ProgressStage.DOWNLOADING_CLIENT, "optifine.progress.preparing_base")
        DownloadClientManager.load(base, reporter=reporter)
        staging = Paths.optifine_staging_dir(instance)
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        minecraft_dir = staging / ".minecraft"
        cls._prepare_staging(base, minecraft_dir)
        if reporter is not None:
            reporter.status(ProgressStage.INSTALLING_MOD_LOADER, "optifine.progress.opening_installer")
        cls._run_installer(instance, source_jar, staging)
        generated = cls._find_generated_profile(minecraft_dir, base.id)
        cls._import_libraries(minecraft_dir)
        normalized = cls._normalize_local_libraries(generated, minecraft_dir)
        merged = cls._merge_profiles(base.raw_json, normalized, base.id, version_id)
        profile_path = Paths.optifine_profile(instance)
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        cls._write_json(profile_path, merged)
        parsed = VersionManager._parse_version(merged, profile_path)
        if parsed is None:
            raise RuntimeError("The OptiFine standalone profile could not be parsed.")
        if reporter is not None:
            reporter.status(ProgressStage.INSTALLING_MOD_LOADER, "optifine.progress.profile_ready")
        shutil.rmtree(staging, ignore_errors=True)
        return parsed

    @staticmethod
    def load(instance: Instance) -> Version:
        path = Paths.optifine_profile(instance)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError) as error:
            raise RuntimeError("The managed OptiFine standalone profile is missing or corrupt. Use Repair OptiFine.") from error
        version = VersionManager._parse_version(data, path)
        if version is None:
            raise RuntimeError("The managed OptiFine standalone profile is invalid. Use Repair OptiFine.")
        return version

    @staticmethod
    def _prepare_staging(base: Version, minecraft_dir: Path) -> None:
        minecraft_dir.mkdir(parents=True, exist_ok=True)
        OptiFineProfileInstaller._write_json(minecraft_dir / "launcher_profiles.json", {"profiles": {}, "selectedProfile": None, "clientToken": "mcw-launcher"})
        version_dir = minecraft_dir / "versions" / base.id
        version_dir.mkdir(parents=True, exist_ok=True)
        OptiFineProfileInstaller._write_json(version_dir / f"{base.id}.json", deepcopy(base.raw_json))
        client = Paths.client(base)
        if not client.is_file():
            raise RuntimeError("The base Minecraft client is missing before OptiFine installation.")
        shutil.copy2(client, version_dir / f"{base.id}.jar")

    @staticmethod
    def _run_installer(instance: Instance, source_jar: Path, staging_home: Path) -> None:
        settings = SettingsManager.load(instance)
        required_major = int(VersionManager.load(instance.version_id).java_version.get("majorVersion") or 8)
        resolution = JavaResolver.resolve_with_recovery(required_major, preferred_path=str(getattr(settings, "java_path", "") or ""))
        env = os.environ.copy()
        env["APPDATA"] = str(staging_home)
        env["HOME"] = str(staging_home)
        env["USERPROFILE"] = str(staging_home)
        command = [str(resolution.path), f"-Duser.home={staging_home}", "-jar", str(source_jar)]
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            result = subprocess.run(command, cwd=source_jar.parent, env=env, timeout=OptiFineProfileInstaller.INSTALL_TIMEOUT_SECONDS, creationflags=creation_flags, check=False)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("The OptiFine installer did not finish within 20 minutes.") from error
        if result.returncode != 0:
            raise RuntimeError(f"The official OptiFine installer exited with code {result.returncode}.")

    @staticmethod
    def _find_generated_profile(minecraft_dir: Path, base_id: str) -> dict:
        candidates: list[tuple[Path, dict]] = []
        versions = minecraft_dir / "versions"
        for path in versions.glob("*/*.json"):
            if path.parent.name == base_id:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            identity = f"{path.parent.name} {data.get('id', '')}".casefold()
            if "optifine" in identity and isinstance(data, dict):
                candidates.append((path, data))
        if not candidates:
            raise RuntimeError("The official OptiFine installer closed without creating an OptiFine launch profile. Confirm that Install completed successfully in the installer window.")
        candidates.sort(key=lambda item: item[0].stat().st_mtime_ns)
        return candidates[-1][1]

    @staticmethod
    def _import_libraries(minecraft_dir: Path) -> None:
        source_root = minecraft_dir / "libraries"
        if not source_root.is_dir():
            raise RuntimeError("The OptiFine installer did not create its runtime library.")
        for source in source_root.rglob("*"):
            if not source.is_file():
                continue
            target = Paths.libraries() / source.relative_to(source_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + ".part")
            try:
                shutil.copy2(source, temporary)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _normalize_local_libraries(profile: dict, minecraft_dir: Path) -> dict:
        normalized = deepcopy(profile)
        result: list[dict] = []
        for raw in profile.get("libraries", []):
            if not isinstance(raw, dict):
                continue
            item = deepcopy(raw)
            downloads = deepcopy(item.get("downloads")) if isinstance(item.get("downloads"), dict) else {}
            artifact = downloads.get("artifact") if isinstance(downloads.get("artifact"), dict) else None
            if not artifact:
                relative = OptiFineProfileInstaller._coordinate_path(str(item.get("name") or ""))
                source = minecraft_dir / "libraries" / relative if relative is not None else None
                target = Paths.libraries() / relative if relative is not None else None
                candidate = target if target is not None and target.is_file() else source
                if candidate is not None and candidate.is_file() and relative is not None:
                    digest = hashlib.sha1(candidate.read_bytes()).hexdigest()
                    downloads["artifact"] = {"path": relative.as_posix(), "url": "https://optifine.net/", "sha1": digest, "size": candidate.stat().st_size}
                    item["downloads"] = downloads
            result.append(item)
        normalized["libraries"] = result
        return normalized

    @staticmethod
    def _coordinate_path(coordinate: str) -> Path | None:
        parts = str(coordinate).split(":")
        if len(parts) < 3:
            return None
        group, artifact, version = parts[:3]
        classifier = parts[3] if len(parts) > 3 else ""
        filename = f"{artifact}-{version}{'-' + classifier if classifier else ''}.jar"
        return Path(*group.split("."), artifact, version, filename)

    @staticmethod
    def _merge_profiles(base: dict, profile: dict, game_version: str, version_id: str) -> dict:
        merged = deepcopy(base)
        merged["id"] = f"optifine-{version_id}"
        merged["inheritsFrom"] = game_version
        if profile.get("mainClass"):
            merged["mainClass"] = profile["mainClass"]
        merged["libraries"] = OptiFineProfileInstaller._merge_libraries(base.get("libraries", []), profile.get("libraries", []))
        profile_arguments = profile.get("arguments") if isinstance(profile.get("arguments"), dict) else {}
        if profile_arguments:
            arguments = deepcopy(base.get("arguments") or {"game": [], "jvm": []})
            arguments.setdefault("game", []).extend(deepcopy(profile_arguments.get("game", [])))
            arguments.setdefault("jvm", []).extend(deepcopy(profile_arguments.get("jvm", [])))
            merged["arguments"] = arguments
        if profile.get("minecraftArguments"):
            existing = str(base.get("minecraftArguments") or "").strip()
            merged["minecraftArguments"] = " ".join(value for value in (existing, str(profile["minecraftArguments"]).strip()) if value)
        if profile.get("javaVersion"):
            merged["javaVersion"] = deepcopy(profile["javaVersion"])
        merged["optifine"] = {"schemaVersion": 1, "gameVersion": game_version, "versionId": version_id, "mode": "standalone"}
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
    def _write_json(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".part")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
