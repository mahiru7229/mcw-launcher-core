from __future__ import annotations

from pathlib import Path
import hashlib
import shutil

from src.core.fs.paths import Paths
from src.core.mod.mod_provenance_registry import ModProvenanceRegistry
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.optifine.optifine_jar_inspector import OptiFineJarInspector
from src.core.optifine.optifine_profile_installer import OptiFineProfileInstaller
from src.core.optifine.optifine_registry import OptiFineRegistry
from src.core.optifine.optifine_transaction import OptiFineTransaction
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.minecraft.version import Version
from src.models.optifine.optifine_models import OptiFineCompatibilityResult, OptiFineCompatibilityState, OptiFineInstallMode, OptiFineInstallResult, OptiFineState, OptiFineVersion
from src.models.progress.progress_stage import ProgressStage


class OptiFineManager:
    @staticmethod
    def inspect_file(source_jar: Path) -> OptiFineVersion:
        return OptiFineJarInspector.inspect(Path(source_jar)).version

    @staticmethod
    def state(instance: Instance) -> OptiFineState:
        OptiFineTransaction.recover(instance)
        return OptiFineRegistry.state(instance)

    @staticmethod
    def compatibility(instance: Instance, selected: OptiFineVersion, requested: str | OptiFineInstallMode = OptiFineInstallMode.AUTO) -> OptiFineCompatibilityResult:
        loader, _loader_version = ModLoaderManager.normalize(instance.mod_loader)
        requested_value = str(getattr(requested, "value", requested) or OptiFineInstallMode.AUTO).casefold()
        if selected.minecraft_version != instance.version_id:
            return OptiFineCompatibilityResult(
                OptiFineCompatibilityState.BLOCKED,
                requested_value,
                f"OptiFine {selected.display_name} targets Minecraft {selected.minecraft_version}, not {instance.version_id}.",
            )
        if requested_value == OptiFineInstallMode.AUTO:
            requested_value = OptiFineInstallMode.STANDALONE if loader == ModLoaderManager.VANILLA else OptiFineInstallMode.FORGE_MOD
        if requested_value == OptiFineInstallMode.STANDALONE:
            if loader != ModLoaderManager.VANILLA:
                return OptiFineCompatibilityResult(OptiFineCompatibilityState.BLOCKED, requested_value, "Standalone OptiFine can only be installed on a Vanilla instance.")
            return OptiFineCompatibilityResult(OptiFineCompatibilityState.COMPATIBLE, requested_value, "The imported OptiFine JAR matches this Minecraft version and can be installed as a standalone profile.")
        if requested_value != OptiFineInstallMode.FORGE_MOD:
            return OptiFineCompatibilityResult(OptiFineCompatibilityState.BLOCKED, requested_value, f"Unsupported OptiFine installation mode: {requested_value}")
        if loader != ModLoaderManager.FORGE:
            return OptiFineCompatibilityResult(OptiFineCompatibilityState.BLOCKED, requested_value, "OptiFine mod mode currently supports Minecraft Forge instances only.")
        return OptiFineCompatibilityResult(
            OptiFineCompatibilityState.COMPATIBLE,
            requested_value,
            "The imported OptiFine JAR matches this Minecraft version and can be installed as a Forge mod.",
        )

    @staticmethod
    def resolve_mode(instance: Instance, requested: str | OptiFineInstallMode = OptiFineInstallMode.AUTO) -> OptiFineInstallMode:
        value = str(getattr(requested, "value", requested) or OptiFineInstallMode.AUTO).casefold()
        loader, _version = ModLoaderManager.normalize(instance.mod_loader)
        if value == OptiFineInstallMode.AUTO:
            value = OptiFineInstallMode.STANDALONE if loader == ModLoaderManager.VANILLA else OptiFineInstallMode.FORGE_MOD
        try:
            mode = OptiFineInstallMode(value)
        except ValueError as error:
            raise RuntimeError(f"Unsupported OptiFine installation mode: {value}") from error
        if mode is OptiFineInstallMode.STANDALONE and loader != ModLoaderManager.VANILLA:
            raise RuntimeError("Standalone OptiFine can only be installed on a Vanilla instance.")
        if mode is OptiFineInstallMode.FORGE_MOD and loader != ModLoaderManager.FORGE:
            raise RuntimeError("OptiFine mod mode currently supports Minecraft Forge instances only.")
        return mode

    @classmethod
    def install(cls, instance: Instance, source_jar: Path, mode: str | OptiFineInstallMode = OptiFineInstallMode.AUTO, reporter: ProgressReporter | None = None) -> OptiFineInstallResult:
        inspected = OptiFineJarInspector.inspect(Path(source_jar), instance.version_id)
        selected = inspected.version
        compatibility = cls.compatibility(instance, selected, mode)
        if compatibility.blocked:
            raise RuntimeError(compatibility.message)
        resolved_mode = cls.resolve_mode(instance, mode)
        cached_source = Paths.optifine_source_cache(inspected.sha256, inspected.filename)
        cached_source.parent.mkdir(parents=True, exist_ok=True)
        if not cached_source.is_file() or cached_source.stat().st_size != inspected.size:
            temporary = cached_source.with_suffix(cached_source.suffix + ".part")
            try:
                shutil.copy2(inspected.path, temporary)
                temporary.replace(cached_source)
            finally:
                temporary.unlink(missing_ok=True)
        if reporter is not None:
            reporter.status(ProgressStage.INSTALLING_MOD_LOADER, "optifine.progress.installing")
        OptiFineTransaction.recover(instance)
        previous = OptiFineRegistry.state(instance)
        transaction = OptiFineTransaction.begin(instance)
        try:
            transaction.mark_applying()
            if resolved_mode is OptiFineInstallMode.FORGE_MOD:
                target = Paths.instance_mods_dir(instance) / inspected.filename
                transaction.register_output(target)
                allowed_existing = {previous.filename.casefold()} if previous.installed and previous.managed and previous.mode == OptiFineInstallMode.FORGE_MOD and previous.filename else set()
                installed_path = cls._install_forge_mod(instance, cached_source, inspected.filename, allowed_existing)
                if cls._sha256(installed_path) != inspected.sha256:
                    raise RuntimeError("The installed OptiFine mod failed integrity verification.")
                profile_path = ""
            else:
                profile = Paths.optifine_profile(instance)
                transaction.register_output(profile)
                version = OptiFineProfileInstaller.install(instance, cached_source, selected.version_id, reporter)
                installed_path = Path(version.path)
                profile_path = str(version.path)
                OptiFineProfileInstaller.load(instance)
            OptiFineRegistry.save(instance, {
                "installed": True,
                "status": "installed",
                "minecraftVersion": selected.minecraft_version,
                "versionId": selected.version_id,
                "fileName": inspected.filename,
                "mode": resolved_mode.value,
                "managed": True,
                "sha256": inspected.sha256,
                "sha1": inspected.sha1,
                "size": inspected.size,
                "sourcePath": str(cached_source),
                "installedPath": str(installed_path),
                "profilePath": profile_path,
                "preview": selected.preview,
                "forgeVersion": "",
                "compatibilityState": compatibility.state.value,
                "officialPage": selected.download_page_url,
            })
            cls._cleanup_previous_managed(instance, previous, {Path(installed_path).resolve(strict=False), Paths.optifine_profile(instance).resolve(strict=False) if profile_path else Path(installed_path).resolve(strict=False)})
            transaction.commit()
        except Exception:
            transaction.rollback()
            raise
        if reporter is not None:
            reporter.status(ProgressStage.FINISHED, "optifine.progress.installed")
        return OptiFineInstallResult(instance.name, resolved_mode.value, selected.version_id, installed_path)

    @classmethod
    def repair(cls, instance: Instance, reporter: ProgressReporter | None = None) -> OptiFineInstallResult:
        state = cls.state(instance)
        if not state.installed or not state.managed:
            raise RuntimeError("This instance has no MCW-managed OptiFine installation to repair.")
        source = Path(state.source_path)
        if not source.is_file() or cls._sha256(source) != state.sha256:
            raise RuntimeError("The cached OptiFine installer is missing or modified. Select the official OptiFine JAR again.")
        result = cls.install(instance, source, state.mode, reporter)
        return OptiFineInstallResult(result.instance_name, result.mode, result.version_id, result.installed_path, repaired=True)

    @classmethod
    def uninstall(cls, instance: Instance) -> bool:
        state = cls.state(instance)
        if not state.installed:
            return False
        if not state.managed:
            raise RuntimeError("MCW will not delete an OptiFine file it does not manage.")
        transaction = OptiFineTransaction.begin(instance)
        try:
            transaction.mark_applying()
            cls._cleanup_previous_managed(instance, state, set())
            OptiFineRegistry.clear(instance)
            transaction.commit()
            return True
        except Exception:
            transaction.rollback()
            raise

    @staticmethod
    def apply_to_version(instance: Instance, base_version: Version) -> Version:
        OptiFineTransaction.recover(instance)
        state = OptiFineRegistry.state(instance)
        if not state.installed:
            return base_version
        if state.minecraft_version != instance.version_id:
            raise RuntimeError("The installed OptiFine component targets a different Minecraft version. Repair or uninstall OptiFine before launching.")
        if state.mode == OptiFineInstallMode.STANDALONE:
            return OptiFineProfileInstaller.load(instance)
        if state.mode == OptiFineInstallMode.FORGE_MOD:
            path = Path(state.installed_path)
            if not path.is_file() or (state.sha256 and OptiFineManager._sha256(path) != state.sha256):
                raise RuntimeError("The managed OptiFine mod is missing or modified. Use Repair OptiFine before launching.")
        return base_version

    @staticmethod
    def _install_forge_mod(instance: Instance, source: Path, filename: str, allowed_existing: set[str] | None = None) -> Path:
        mods = Paths.instance_mods_dir(instance)
        allowed = {str(item).casefold() for item in (allowed_existing or set())}
        target = mods / filename
        if target.is_file() and target.name.casefold() not in allowed:
            raise RuntimeError("An unmanaged OptiFine JAR with the selected filename already exists. Remove it manually before installing a managed copy.")
        unmanaged = [
            path
            for path in mods.glob("*.jar")
            if path.name.casefold().startswith(("optifine_", "preview_optifine_"))
            and path.name.casefold() != filename.casefold()
            and path.name.casefold() not in allowed
        ]
        if unmanaged:
            raise RuntimeError("Another unmanaged OptiFine JAR already exists in this instance. Remove it manually before installing a managed OptiFine version.")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".part")
        try:
            shutil.copy2(source, temporary)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        digest = hashlib.sha1(target.read_bytes()).hexdigest()
        ModProvenanceRegistry.record_many(instance, [{
            "fileName": target.name,
            "path": f"mods/{target.name}",
            "provider": "optifine",
            "versionNumber": target.stem,
            "sha1": digest,
            "size": target.stat().st_size,
            "downloadUrls": [],
            "projectUrl": "https://optifine.net/downloads",
            "redistributionAllowed": False,
            "managedByModpack": False,
        }])
        return target

    @staticmethod
    def _cleanup_previous_managed(instance: Instance, previous: OptiFineState, keep_paths: set[Path]) -> None:
        if not previous.installed or not previous.managed:
            return
        keep = {Path(item).resolve(strict=False) for item in keep_paths}
        if previous.mode == OptiFineInstallMode.FORGE_MOD and previous.installed_path:
            path = Path(previous.installed_path).resolve(strict=False)
            mods = Paths.instance_mods_dir(instance).resolve(strict=False)
            if path.parent == mods and path not in keep:
                if path.is_file() and (not previous.sha256 or OptiFineManager._sha256(path) == previous.sha256):
                    path.unlink(missing_ok=True)
                ModProvenanceRegistry.remove_by_filenames(instance, {previous.filename})
        if previous.mode == OptiFineInstallMode.STANDALONE:
            profile = Paths.optifine_profile(instance).resolve(strict=False)
            if profile not in keep:
                profile.unlink(missing_ok=True)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _edition_from_version_id(value: str) -> str:
        parts = str(value).split("_")
        return "_".join(parts[1:3]) if len(parts) >= 4 else "HD_U"

    @staticmethod
    def _build_from_version_id(value: str) -> str:
        parts = str(value).split("_")
        return "_".join(parts[3:]) if len(parts) >= 4 else str(value)
