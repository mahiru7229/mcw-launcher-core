from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import zipfile

from src.core.fs.paths import Paths
from src.core.lan.lan_agent_manager import LanAgentManager
from src.core.minecraft.version_manager import VersionManager
from src.core.mod.mod_manager import ModManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.security.sensitive_data_redactor import SensitiveDataRedactor
from src.models.instance.instance import Instance


class QuiltDiagnosticsManager:
    SCHEMA_VERSION = 1
    MAX_TEXT_BYTES = 2 * 1024 * 1024

    @classmethod
    def export(cls, instance: Instance, destination: Path, launcher_version: str) -> Path:
        loader_name, loader_version = ModLoaderManager.normalize(instance.mod_loader)
        if loader_name != ModLoaderManager.QUILT:
            raise RuntimeError("Quilt diagnostics are available only for Quilt instances.")

        target = Path(destination)
        if target.suffix.casefold() != ".zip":
            target = target.with_suffix(".zip")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".part")
        temporary.unlink(missing_ok=True)

        profile_path = Paths.quilt_version_json(instance.version_id, loader_version)
        try:
            profile_data = json.loads(profile_path.read_text(encoding="utf-8"))
            version = VersionManager._parse_version(profile_data, profile_path)
            if version is None:
                raise RuntimeError("The cached Quilt launch profile could not be parsed.")
        except Exception as error:
            version = None
            profile_error = SensitiveDataRedactor.redact_text(error)
        else:
            profile_error = ""

        summary = cls._summary(instance, launcher_version, loader_version, version, profile_error)
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                cls._write_text(archive, "summary.txt", summary)
                cls._add_json_file(archive, Path(instance.instance_dir) / "instance.json", "instance/instance.json")
                cls._add_json_file(archive, Path(instance.instance_dir) / "settings.json", "instance/settings.json")
                if version is not None:
                    cls._write_text(archive, "quilt/profile.json", json.dumps(version.raw_json, ensure_ascii=False, indent=2) + "\n")
                cls._write_mod_inventory(archive, instance)
                cls._add_runtime_logs(archive, instance)
                agent_log = LanAgentManager.log_path(instance)
                if agent_log.is_file():
                    cls._add_text_file(archive, agent_log, "lan/mcw-lan-agent.log")
            with zipfile.ZipFile(temporary, "r") as archive:
                if archive.testzip() is not None:
                    raise RuntimeError("The Quilt diagnostic package failed integrity verification.")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return target

    @classmethod
    def _summary(cls, instance: Instance, launcher_version: str, loader_version: str, version: object | None, profile_error: str) -> str:
        heading = "MCW Launcher Quilt Diagnostic Package"
        java_major = int((getattr(version, "java_version", None) or {}).get("majorVersion") or 8)
        lines = [
            heading,
            "=" * len(heading),
            f"schema_version: {cls.SCHEMA_VERSION}",
            f"generated_at: {datetime.now(timezone.utc).isoformat()}",
            f"launcher_version: {launcher_version}",
            f"instance_name: {instance.name}",
            f"instance_id: {instance.instance_id}",
            f"minecraft_version: {instance.version_id}",
            "loader: quilt",
            f"loader_version: {loader_version}",
            f"required_java_major: {java_major}",
            "",
            "Quilt profile",
            "-------------",
        ]
        if version is not None:
            lines.append(f"profile_id: {version.id}")
            lines.append(f"main_class: {version.main_class}")
            lines.append(f"library_count: {len(version.libraries)}")
        else:
            lines.append(f"Could not load the cached Quilt profile: {profile_error or 'unknown error'}")
        lines.extend([
            "",
            "Privacy",
            "-------",
            "This package excludes account databases, access tokens, refresh tokens, passwords, worlds, saves, and mod JAR contents.",
        ])
        return "\n".join(lines).rstrip() + "\n"

    @classmethod
    def _write_mod_inventory(cls, archive: zipfile.ZipFile, instance: Instance) -> None:
        mods = [
            {
                "file_name": mod.file_name,
                "enabled": mod.enabled,
                "mod_id": mod.mod_id,
                "name": mod.name,
                "version": mod.version,
                "loader": mod.loader,
                "metadata_format": mod.metadata_format,
                "dependencies": mod.dependencies,
                "recommends": mod.recommends,
                "status": mod.status,
                "error": mod.error,
            }
            for mod in ModManager.list_mods(instance)
        ]
        cls._write_text(archive, "mods/inventory.json", json.dumps(mods, ensure_ascii=False, indent=2) + "\n")

    @classmethod
    def _add_runtime_logs(cls, archive: zipfile.ZipFile, instance: Instance) -> None:
        for relative, archive_name in (
            (Path("logs") / "latest.log", "minecraft/latest.log"),
            (Path(".mcw") / "minecraft.log", "minecraft/launcher-captured.log"),
        ):
            path = Path(instance.instance_dir) / relative
            if path.is_file():
                cls._add_text_file(archive, path, archive_name)

    @classmethod
    def _add_json_file(cls, archive: zipfile.ZipFile, path: Path, archive_name: str) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
            return
        safe = SensitiveDataRedactor.redact_value(data)
        cls._write_text(archive, archive_name, json.dumps(safe, ensure_ascii=False, indent=2) + "\n")

    @classmethod
    def _add_text_file(cls, archive: zipfile.ZipFile, path: Path, archive_name: str) -> None:
        try:
            raw = path.read_bytes()[-cls.MAX_TEXT_BYTES :]
            text = raw.decode("utf-8", errors="replace")
        except OSError:
            return
        cls._write_text(archive, archive_name, text)

    @staticmethod
    def _write_text(archive: zipfile.ZipFile, archive_name: str, content: str) -> None:
        safe = SensitiveDataRedactor.redact_text(content)
        archive.writestr(archive_name, safe.encode("utf-8"))
