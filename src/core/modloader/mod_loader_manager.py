from src.core.instance.settings_manager import SettingsManager
from src.core.minecraft.version_manager import VersionManager
from src.core.modloader.fabric.fabric_version_manager import FabricVersionManager
from src.core.modloader.forge.forge_version_manager import ForgeVersionManager
from src.core.modloader.neoforge.neoforge_version_manager import NeoForgeVersionManager
from src.core.modloader.quilt.quilt_version_manager import QuiltVersionManager
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.minecraft.version import Version


class ModLoaderManager:
    VANILLA = "vanilla"
    FABRIC = "fabric"
    FORGE = "forge"
    NEOFORGE = "neoforge"
    QUILT = "quilt"
    AUTO = "auto"
    MODDED_LOADERS = frozenset({FABRIC, FORGE, NEOFORGE, QUILT})
    FORGE_FAMILY = frozenset({FORGE, NEOFORGE})

    @staticmethod
    def load(instance: Instance, reporter: ProgressReporter | None = None, preferred_java_path: str | None = None) -> Version:
        loader_name, loader_version = ModLoaderManager.normalize(getattr(instance, "mod_loader", (ModLoaderManager.VANILLA, "-1")))
        if loader_name != ModLoaderManager.VANILLA:
            clean_version = loader_version
            if clean_version.casefold().startswith(f"{loader_name}-"):
                clean_version = clean_version[len(loader_name) + 1:].strip()
            gv = str(getattr(instance, "version_id", "") or "").strip()
            if gv and clean_version.startswith(f"{gv}-"):
                clean_version = clean_version[len(gv) + 1:].strip()
            if clean_version != loader_version:
                loader_version = clean_version
                try:
                    instance.mod_loader = (loader_name, loader_version)
                    from src.core.instance.instance_manager import InstanceManager
                    InstanceManager.save(instance)
                except Exception:
                    pass
        if loader_name == ModLoaderManager.VANILLA:
            return VersionManager.load(instance.version_id)
        if loader_name == ModLoaderManager.FABRIC:
            return FabricVersionManager.load(instance.version_id, loader_version, reporter)
        if loader_name == ModLoaderManager.FORGE:
            if preferred_java_path:
                return ForgeVersionManager.load(instance.version_id, loader_version, reporter, preferred_java_path=preferred_java_path)
            return ForgeVersionManager.load(instance.version_id, loader_version, reporter)
        if loader_name == ModLoaderManager.NEOFORGE:
            if preferred_java_path:
                return NeoForgeVersionManager.load(instance.version_id, loader_version, reporter, preferred_java_path=preferred_java_path)
            return NeoForgeVersionManager.load(instance.version_id, loader_version, reporter)
        if loader_name == ModLoaderManager.QUILT:
            return QuiltVersionManager.load(instance.version_id, loader_version, reporter)
        raise RuntimeError(f"Unsupported mod loader: {loader_name}")

    @staticmethod
    def prepare(version: Version, loader_name: str, loader_version: str, reporter: ProgressReporter | None = None, preferred_java_path: str | None = None) -> Version:
        loader_name, loader_version = ModLoaderManager.normalize((loader_name, loader_version))
        if loader_name != ModLoaderManager.VANILLA:
            if loader_version.casefold().startswith(f"{loader_name}-"):
                loader_version = loader_version[len(loader_name) + 1:].strip()
            gv = str(getattr(version, "id", "") or "").strip()
            if gv and loader_version.startswith(f"{gv}-"):
                loader_version = loader_version[len(gv) + 1:].strip()
        if loader_name == ModLoaderManager.VANILLA:
            return version
        if loader_name == ModLoaderManager.FABRIC:
            return FabricVersionManager.install(version, loader_version, reporter)
        if loader_name == ModLoaderManager.FORGE:
            if preferred_java_path:
                return ForgeVersionManager.install(version, loader_version, reporter, preferred_java_path=preferred_java_path)
            return ForgeVersionManager.install(version, loader_version, reporter)
        if loader_name == ModLoaderManager.NEOFORGE:
            if preferred_java_path:
                return NeoForgeVersionManager.install(version, loader_version, reporter, preferred_java_path=preferred_java_path)
            return NeoForgeVersionManager.install(version, loader_version, reporter)
        if loader_name == ModLoaderManager.QUILT:
            return QuiltVersionManager.install(version, loader_version, reporter)
        raise RuntimeError(f"Unsupported mod loader: {loader_name}")

    @staticmethod
    def repair(instance: Instance, reporter: ProgressReporter | None = None, preferred_java_path: str | None = None) -> Version:
        loader_name, loader_version = ModLoaderManager.normalize(getattr(instance, "mod_loader", (ModLoaderManager.VANILLA, "-1")))
        if loader_name not in ModLoaderManager.MODDED_LOADERS:
            raise RuntimeError("Only Fabric, Quilt, Forge, or NeoForge instances can be repaired.")
        if loader_version.casefold().startswith(f"{loader_name}-"):
            loader_version = loader_version[len(loader_name) + 1:].strip()
        gv = str(getattr(instance, "version_id", "") or "").strip()
        if gv and loader_version.startswith(f"{gv}-"):
            loader_version = loader_version[len(gv) + 1:].strip()
        base_version = VersionManager.load(instance.version_id)
        if preferred_java_path is None and loader_name in ModLoaderManager.FORGE_FAMILY and hasattr(instance, "instance_dir"):
            preferred_java_path = str(getattr(SettingsManager.load(instance), "java_path", "") or "").strip()
        if loader_name == ModLoaderManager.FABRIC:
            return FabricVersionManager.repair(base_version, loader_version, reporter)
        if loader_name == ModLoaderManager.FORGE:
            if preferred_java_path:
                return ForgeVersionManager.repair(base_version, loader_version, reporter, preferred_java_path=preferred_java_path)
            return ForgeVersionManager.repair(base_version, loader_version, reporter)
        if loader_name == ModLoaderManager.NEOFORGE:
            if preferred_java_path:
                return NeoForgeVersionManager.repair(base_version, loader_version, reporter, preferred_java_path=preferred_java_path)
            return NeoForgeVersionManager.repair(base_version, loader_version, reporter)
        return QuiltVersionManager.repair(base_version, loader_version, reporter)

    @staticmethod
    def resolve(game_version: str, loader_name: str, loader_version: str = AUTO) -> tuple[str, str]:
        loader_name, loader_version = ModLoaderManager.normalize((loader_name, loader_version))
        automatic = loader_version.casefold() in {"", "-1", ModLoaderManager.AUTO, "latest", "recommended"}
        if loader_name == ModLoaderManager.VANILLA:
            return ModLoaderManager.VANILLA, "-1"
        if not automatic:
            if loader_version.casefold().startswith(f"{loader_name}-"):
                loader_version = loader_version[len(loader_name) + 1:].strip()
            prefix = f"{str(game_version).strip()}-"
            if prefix != "-" and loader_version.startswith(prefix):
                loader_version = loader_version[len(prefix):].strip()
            if loader_name in {ModLoaderManager.FABRIC, ModLoaderManager.QUILT} and loader_version.casefold().startswith("loader-"):
                loader_version = loader_version[7:].strip()
        if loader_name == ModLoaderManager.FABRIC:
            return ModLoaderManager.FABRIC, FabricVersionManager.recommended_loader_version(game_version) if automatic else loader_version
        if loader_name == ModLoaderManager.FORGE:
            return ModLoaderManager.FORGE, ForgeVersionManager.recommended_loader_version(game_version) if automatic else loader_version
        if loader_name == ModLoaderManager.NEOFORGE:
            return ModLoaderManager.NEOFORGE, NeoForgeVersionManager.recommended_loader_version(game_version) if automatic else loader_version
        if loader_name == ModLoaderManager.QUILT:
            return ModLoaderManager.QUILT, QuiltVersionManager.recommended_loader_version(game_version) if automatic else loader_version
        raise RuntimeError(f"Unsupported mod loader: {loader_name}")

    @staticmethod
    def normalize(mod_loader: object) -> tuple[str, str]:
        if not isinstance(mod_loader, (tuple, list)) or not mod_loader:
            return ModLoaderManager.VANILLA, "-1"
        name = str(mod_loader[0]).strip().lower() or ModLoaderManager.VANILLA
        version = str(mod_loader[1]).strip() if len(mod_loader) > 1 else "-1"
        if name == ModLoaderManager.VANILLA:
            version = "-1"
        return name, version
