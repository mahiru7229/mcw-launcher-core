from __future__ import annotations

from datetime import datetime, timezone
import json
import os

from src.core.fs.paths import Paths
from src.core.instance.instance_manager import InstanceManager
from src.core.minecraft.library_manager import DownloadLibraryManager
from src.core.minecraft.version_manager import VersionManager
from src.core.modloader.forge.forge_version_manager import ForgeVersionManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.modloader.neoforge.neoforge_version_manager import NeoForgeVersionManager
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.progress.progress_stage import ProgressStage


class ForgeChangeManager:
    SNAPSHOT_SCHEMA_VERSION = 1

    @classmethod
    def change(
        cls,
        instance: Instance,
        loader_name: str,
        loader_version: str,
        reporter: ProgressReporter | None = None,
    ) -> Instance:
        previous_loader = ModLoaderManager.normalize(instance.mod_loader)
        resolved_loader = ModLoaderManager.resolve(instance.version_id, loader_name, loader_version)
        if previous_loader == resolved_loader:
            return instance

        if reporter is not None:
            reporter.status(
                stage=ProgressStage.INSTALLING_MOD_LOADER,
                message=f"Preparing {cls._display_loader(resolved_loader)} before switching...",
            )

        base_version = VersionManager.load(instance.version_id)
        prepared = ModLoaderManager.prepare(base_version, *resolved_loader, reporter=reporter)
        cls._verify_prepared(instance.version_id, resolved_loader, prepared, reporter)

        snapshot = cls._build_snapshot(instance, previous_loader, resolved_loader)
        try:
            updated = InstanceManager.set_mod_loader(instance.name, resolved_loader)
            cls._write_snapshot(instance, snapshot)
            cls._write_log(
                instance,
                "Mod-loader change completed.\n"
                f"Previous: {cls._display_loader(previous_loader)}\n"
                f"Current: {cls._display_loader(resolved_loader)}\n",
            )
            return updated
        except Exception:
            try:
                InstanceManager.set_mod_loader(instance.name, previous_loader)
            except Exception:
                pass
            raise

    @classmethod
    def restore_previous(cls, instance: Instance, reporter: ProgressReporter | None = None) -> Instance:
        snapshot = cls.load_snapshot(instance)
        if snapshot is None:
            raise RuntimeError("No previous mod-loader installation is available for this instance.")

        previous_loader = cls._snapshot_loader(snapshot, "previous_loader")
        current_loader = ModLoaderManager.normalize(instance.mod_loader)
        if previous_loader == current_loader:
            raise RuntimeError("The instance already uses the previous mod-loader installation.")

        if reporter is not None:
            reporter.status(
                stage=ProgressStage.INSTALLING_MOD_LOADER,
                message=f"Restoring {cls._display_loader(previous_loader)}...",
            )

        base_version = VersionManager.load(instance.version_id)
        prepared = ModLoaderManager.prepare(base_version, *previous_loader, reporter=reporter)
        cls._verify_prepared(instance.version_id, previous_loader, prepared, reporter)

        reverse_snapshot = cls._build_snapshot(instance, current_loader, previous_loader)
        try:
            restored = InstanceManager.set_mod_loader(instance.name, previous_loader)
            cls._write_snapshot(instance, reverse_snapshot)
            cls._write_log(
                instance,
                "Previous mod-loader installation restored.\n"
                f"Previous current: {cls._display_loader(current_loader)}\n"
                f"Restored: {cls._display_loader(previous_loader)}\n",
            )
            return restored
        except Exception:
            try:
                InstanceManager.set_mod_loader(instance.name, current_loader)
            except Exception:
                pass
            raise

    @classmethod
    def has_restore_point(cls, instance: Instance) -> bool:
        return cls.load_snapshot(instance) is not None

    @classmethod
    def load_snapshot(cls, instance: Instance) -> dict | None:
        path = Paths.forge_rollback_path(instance)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("schema_version") != cls.SNAPSHOT_SCHEMA_VERSION:
            return None
        if str(payload.get("instance_id") or "") != instance.instance_id:
            return None
        if str(payload.get("minecraft_version") or "") != instance.version_id:
            return None
        try:
            cls._snapshot_loader(payload, "previous_loader")
            cls._snapshot_loader(payload, "target_loader")
        except RuntimeError:
            return None
        return payload

    @classmethod
    def _verify_prepared(
        cls,
        game_version: str,
        loader: tuple[str, str],
        prepared: object,
        reporter: ProgressReporter | None,
    ) -> None:
        loader_name, loader_version = loader
        if loader_name not in ModLoaderManager.FORGE_FAMILY:
            return
        DownloadLibraryManager.load(prepared, reporter=reporter)
        manager = NeoForgeVersionManager if loader_name == ModLoaderManager.NEOFORGE else ForgeVersionManager
        issues = manager.validate_installation(prepared, game_version, loader_version, verify_files=True)
        if issues:
            details = "\n".join(f"- {issue}" for issue in issues)
            title = "NeoForge" if loader_name == ModLoaderManager.NEOFORGE else "Forge"
            raise RuntimeError(f"{title} version change validation failed:\n{details}")

    @classmethod
    def _build_snapshot(
        cls,
        instance: Instance,
        previous_loader: tuple[str, str],
        target_loader: tuple[str, str],
    ) -> dict:
        return {
            "schema_version": cls.SNAPSHOT_SCHEMA_VERSION,
            "instance_id": instance.instance_id,
            "instance_name": instance.name,
            "minecraft_version": instance.version_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "previous_loader": list(previous_loader),
            "target_loader": list(target_loader),
        }

    @classmethod
    def _write_snapshot(cls, instance: Instance, payload: dict) -> None:
        path = Paths.forge_rollback_path(instance)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as file:
            file.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(path)

    @staticmethod
    def _snapshot_loader(snapshot: dict, key: str) -> tuple[str, str]:
        raw = snapshot.get(key)
        if not isinstance(raw, list) or len(raw) != 2:
            raise RuntimeError("The mod-loader rollback snapshot is invalid.")
        return ModLoaderManager.normalize((str(raw[0]), str(raw[1])))

    @staticmethod
    def _display_loader(loader: tuple[str, str]) -> str:
        name, version = loader
        return name.title() if name == ModLoaderManager.VANILLA else f"{name.title()} {version}"

    @staticmethod
    def _write_log(instance: Instance, content: str) -> None:
        path = Paths.forge_instance_log_path(instance)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", errors="replace")
