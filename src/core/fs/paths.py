from pathlib import Path
from contextlib import contextmanager
from collections.abc import Iterator
from src.models.minecraft.version import Version
from src.models.minecraft.assets import DownloadAsset
from src.models.instance.instance import Instance
import json
import os
import shutil
import sys
import tempfile
from uuid import uuid4
def _default_short_workspace_root() -> Path:
    if sys.platform == "win32":
        local_app_data = str(os.environ.get("LOCALAPPDATA") or "").strip()
        if local_app_data:
            return Path(local_app_data) / "MCW" / "t"
    return Path(tempfile.gettempdir()) / "MCW" / "t"


if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Paths:
    PROJECT_ROOT = PROJECT_ROOT
    CACHE_ROOT = PROJECT_ROOT / "cache" # place that saves minecraft contents
    INSTANCES_ROOT = PROJECT_ROOT / "instances"
    ACCOUNTS_ROOT = PROJECT_ROOT / "accounts"
    CONFIG_ROOT = PROJECT_ROOT / "config"
    LOGS_ROOT = PROJECT_ROOT / "logs"
    BACKUPS_ROOT = PROJECT_ROOT / "backups"
    THEME_ROOT = PROJECT_ROOT / "themes"
    RUNTIMES_ROOT = PROJECT_ROOT / "runtimes"
    INSTANCE_LOCKS_ROOT = INSTANCES_ROOT / ".runtime" / "locks"
    SHORT_WORKSPACE_ROOT = _default_short_workspace_root()
    
    @staticmethod
    def initialize() -> None:
        directories = [
            Paths.CACHE_ROOT,
            Paths.INSTANCES_ROOT,
            Paths.ACCOUNTS_ROOT,
            Paths.CONFIG_ROOT,
            Paths.LOGS_ROOT,
            Paths.BACKUPS_ROOT,
            Paths.THEME_ROOT,
            Paths.RUNTIMES_ROOT,
            Paths.INSTANCE_LOCKS_ROOT,
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)


    @staticmethod
    def backups_root() -> Path:
        Paths.BACKUPS_ROOT.mkdir(parents=True, exist_ok=True)
        return Paths.BACKUPS_ROOT

    @staticmethod
    def instance_backups_dir(instance: Instance) -> Path:
        directory = Paths.backups_root() / instance.instance_id
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def backup_staging_root() -> Path:
        directory = Paths.CACHE_ROOT / "backups" / "staging"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def theme_asset(theme: str, *paths: str) -> Path:
        return Paths.theme_dir(theme).joinpath(*paths)

    @staticmethod
    def theme_dir(name:str) -> Path:
        directory  = Path(Paths.THEME_ROOT / name)
        directory.mkdir(parents=True, exist_ok=True)
        """
        Choosing theme pack.
        """
        return directory
    @staticmethod
    def root() -> Path:
        return Path(Paths.PROJECT_ROOT)

    @staticmethod
    def snapshot() -> dict[str, Path]:
        return {
            "PROJECT_ROOT": Path(Paths.PROJECT_ROOT),
            "CACHE_ROOT": Path(Paths.CACHE_ROOT),
            "INSTANCES_ROOT": Path(Paths.INSTANCES_ROOT),
            "ACCOUNTS_ROOT": Path(Paths.ACCOUNTS_ROOT),
            "CONFIG_ROOT": Path(Paths.CONFIG_ROOT),
            "LOGS_ROOT": Path(Paths.LOGS_ROOT),
            "BACKUPS_ROOT": Path(Paths.BACKUPS_ROOT),
            "THEME_ROOT": Path(Paths.THEME_ROOT),
            "RUNTIMES_ROOT": Path(Paths.RUNTIMES_ROOT),
            "INSTANCE_LOCKS_ROOT": Path(Paths.INSTANCE_LOCKS_ROOT),
        }

    @staticmethod
    def restore(snapshot: dict[str, Path], initialize: bool = False) -> None:
        required = {
            "PROJECT_ROOT", "CACHE_ROOT", "INSTANCES_ROOT", "ACCOUNTS_ROOT",
            "CONFIG_ROOT", "LOGS_ROOT", "BACKUPS_ROOT", "THEME_ROOT",
            "RUNTIMES_ROOT", "INSTANCE_LOCKS_ROOT",
        }
        missing = required.difference(snapshot)
        if missing:
            raise ValueError(f"Path snapshot is missing: {', '.join(sorted(missing))}")
        for name in required:
            setattr(Paths, name, Path(snapshot[name]).expanduser().resolve(strict=False))
        if initialize:
            Paths.initialize()

    @staticmethod
    def configure(
        root: Path | str | None = None,
        *,
        cache_root: Path | str | None = None,
        instances_root: Path | str | None = None,
        accounts_root: Path | str | None = None,
        config_root: Path | str | None = None,
        logs_root: Path | str | None = None,
        backups_root: Path | str | None = None,
        theme_root: Path | str | None = None,
        runtimes_root: Path | str | None = None,
        initialize: bool = True,
    ) -> dict[str, Path]:
        previous = Paths.snapshot()
        base = Path(root if root is not None else Paths.PROJECT_ROOT).expanduser().resolve(strict=False)
        Paths.PROJECT_ROOT = base
        Paths.CACHE_ROOT = Path(cache_root).expanduser().resolve(strict=False) if cache_root is not None else base / "cache"
        Paths.INSTANCES_ROOT = Path(instances_root).expanduser().resolve(strict=False) if instances_root is not None else base / "instances"
        Paths.ACCOUNTS_ROOT = Path(accounts_root).expanduser().resolve(strict=False) if accounts_root is not None else base / "accounts"
        Paths.CONFIG_ROOT = Path(config_root).expanduser().resolve(strict=False) if config_root is not None else base / "config"
        Paths.LOGS_ROOT = Path(logs_root).expanduser().resolve(strict=False) if logs_root is not None else base / "logs"
        Paths.BACKUPS_ROOT = Path(backups_root).expanduser().resolve(strict=False) if backups_root is not None else base / "backups"
        Paths.THEME_ROOT = Path(theme_root).expanduser().resolve(strict=False) if theme_root is not None else base / "themes"
        Paths.RUNTIMES_ROOT = Path(runtimes_root).expanduser().resolve(strict=False) if runtimes_root is not None else base / "runtimes"
        Paths.INSTANCE_LOCKS_ROOT = Paths.INSTANCES_ROOT / ".runtime" / "locks"
        if initialize:
            Paths.initialize()
        return previous

    @staticmethod
    @contextmanager
    def configured(root: Path | str | None = None, **overrides: object) -> Iterator[None]:
        previous = Paths.configure(root, **overrides)
        try:
            yield
        finally:
            Paths.restore(previous)

    @staticmethod
    def short_workspace_root() -> Path:
        root = Path(Paths.SHORT_WORKSPACE_ROOT)
        root.mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def create_short_workspace(purpose: str) -> Path:
        prefix = str(purpose or "").strip().casefold()
        if len(prefix) != 3 or not prefix.isalnum():
            raise ValueError("Short workspace purpose must be exactly three alphanumeric characters.")
        parent = Paths.short_workspace_root() / prefix
        parent.mkdir(parents=True, exist_ok=True)
        for _ in range(32):
            workspace = parent / uuid4().hex[:8]
            try:
                workspace.mkdir(parents=False, exist_ok=False)
                return workspace
            except FileExistsError:
                continue
        raise RuntimeError(f"Could not allocate a short MCW workspace for {prefix}.")

    @staticmethod
    def cleanup_short_workspace(workspace: Path) -> None:
        path = Path(workspace)
        try:
            path.relative_to(Paths.short_workspace_root())
        except ValueError as error:
            raise ValueError(f"Refusing to clean a path outside the MCW short workspace root: {path}") from error
        shutil.rmtree(path, ignore_errors=True)

    @staticmethod
    def microsoft_config_root()->Path:
        return Paths.CONFIG_ROOT / "microsoft.json"

    @staticmethod
    def launcher_settings_path() -> Path:
        return Paths.CONFIG_ROOT / "launcher_settings.json"

    @staticmethod
    def logs_root() -> Path:
        Paths.LOGS_ROOT.mkdir(parents=True, exist_ok=True)
        return Paths.LOGS_ROOT

    @staticmethod
    def updater_log_path() -> Path:
        return Paths.logs_root() / "updater.log"

    @staticmethod
    def diagnostics_default_path() -> Path:
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return Paths.logs_root() / f"MCW-Diagnostics-{timestamp}.zip"

    @staticmethod
    def download_journal_path() -> Path:
        directory = Paths.CACHE_ROOT / "downloads"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / "journal.json"

    @staticmethod
    def content_store_root() -> Path:
        directory = Paths.CACHE_ROOT / "content-store" / "sha256"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def content_store_blob(sha256: str) -> Path:
        digest = str(sha256 or "").strip().casefold()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("Content store SHA-256 must contain exactly 64 hexadecimal characters.")
        return Paths.content_store_root() / digest[:2] / digest

    @staticmethod
    def update_root() -> Path:
        directory = Paths.CACHE_ROOT / "updates"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def update_release_cache() -> Path:
        return Paths.update_root() / "releases.json"

    @staticmethod
    def update_download_path(tag_name: str, asset_name: str) -> Path:
        from urllib.parse import quote

        tag = quote(str(tag_name).strip(), safe="") or "unknown-release"
        filename = Path(str(asset_name)).name or "update.zip"
        return Paths.update_root() / "downloads" / tag / filename

    @staticmethod
    def update_staging_root() -> Path:
        directory = Paths.update_root() / "staging"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def account_database_path():
        return Paths.ACCOUNTS_ROOT / "accounts.db"

    @staticmethod
    def account_skins_root() -> Path:
        directory = Paths.ACCOUNTS_ROOT / "skins"
        directory.mkdir(parents=True, exist_ok=True)
        return directory


    @staticmethod
    def accounts_path() -> Path:
        return Paths.ACCOUNTS_ROOT / "accounts.json"




    @staticmethod
    def instance_metadata(instance_name: str) -> Path:
        return Paths.load_instance_dir(instance_name) / "instance.json"




    @staticmethod
    def instance_settings_path(instance:Instance) -> Path:
        instance_settings_path = Path(instance.instance_dir) / "settings.json"
        if not instance_settings_path.exists():
            Paths.instance_settings_create(instance)
        return instance_settings_path
        


    @staticmethod
    def instance_settings_create(instance:Instance) -> Path:
        """
        Default settings.
        """
        instance_settings_path = Path(instance.instance_dir) / "settings.json"
        return instance_settings_path


    @staticmethod
    def instances_root() -> Path:
        instance_dir = Paths.INSTANCES_ROOT
        instance_dir.mkdir(parents=True, exist_ok=True)
        return instance_dir

    @staticmethod
    def instance_runtime_root() -> Path:
        directory = Paths.instances_root() / ".runtime"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def instance_operations_root() -> Path:
        directory = Paths.instance_runtime_root() / "operations"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def instance_staging_root() -> Path:
        directory = Paths.instance_runtime_root() / "staging"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def process_sessions_root() -> Path:
        directory = Paths.instance_runtime_root() / "process-sessions"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def process_session_history_root() -> Path:
        directory = Paths.process_sessions_root() / "history"
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    
    @staticmethod
    def load_instance_dir(name: str) -> Path:
        return Paths.instances_root() / name


    @staticmethod
    def create_instance_dir(name: str) -> Path:
        path = Paths.load_instance_dir(name)
        path.mkdir(parents=True, exist_ok=False)
        return path
    

    
    @staticmethod
    def instance_data_path_create():
        instance_path = Paths.instances_root() / "instances.json"
        if not instance_path.exists():
            instance_path.write_text(
                json.dumps({"instances": []}, indent=4),
                encoding="utf-8"
            )
        return instance_path
    @staticmethod
    def instance_data_path():
        instance_path = Paths.instances_root() / "instances.json"
        return instance_path

    @staticmethod
    def version_dir(version:Version):
        return Paths.CACHE_ROOT / "versions" / version.id

    @staticmethod
    def client(version:Version):
        raw_json = getattr(version, "raw_json", {}) or {}
        inherited_version = str(raw_json.get("inheritsFrom") or version.id)
        return Paths.CACHE_ROOT / "versions" / inherited_version / f"{inherited_version}.jar"

    @staticmethod
    def fabric_version_dir(game_version: str, loader_version: str) -> Path:
        profile_id = f"fabric-loader-{loader_version}-{game_version}"
        return Paths.CACHE_ROOT / "versions" / profile_id

    @staticmethod
    def fabric_version_json(game_version: str, loader_version: str) -> Path:
        directory = Paths.fabric_version_dir(game_version, loader_version)
        return directory / f"{directory.name}.json"

    @staticmethod
    def fabric_metadata_root() -> Path:
        return Paths.CACHE_ROOT / "modloaders" / "fabric"

    @staticmethod
    def fabric_catalog_json(game_version: str) -> Path:
        from urllib.parse import quote

        filename = quote(game_version, safe="") or "unknown"
        return Paths.fabric_metadata_root() / "catalogs" / f"{filename}.json"

    @staticmethod
    def fabric_install_metadata_json(game_version: str, loader_version: str) -> Path:
        from urllib.parse import quote

        game = quote(game_version, safe="") or "unknown"
        loader = quote(loader_version, safe="") or "unknown"
        return Paths.fabric_metadata_root() / "install" / game / f"{loader}.json"

    @staticmethod
    def fabric_profile_json(game_version: str, loader_version: str) -> Path:
        from urllib.parse import quote

        game = quote(game_version, safe="") or "unknown"
        loader = quote(loader_version, safe="") or "unknown"
        return Paths.fabric_metadata_root() / "profiles" / game / f"{loader}.json"

    @staticmethod
    def quilt_version_dir(game_version: str, loader_version: str) -> Path:
        profile_id = f"quilt-loader-{loader_version}-{game_version}"
        return Paths.CACHE_ROOT / "versions" / profile_id

    @staticmethod
    def quilt_version_json(game_version: str, loader_version: str) -> Path:
        directory = Paths.quilt_version_dir(game_version, loader_version)
        return directory / f"{directory.name}.json"

    @staticmethod
    def quilt_metadata_root() -> Path:
        return Paths.CACHE_ROOT / "modloaders" / "quilt"

    @staticmethod
    def quilt_catalog_json(game_version: str) -> Path:
        from urllib.parse import quote

        filename = quote(game_version, safe="") or "unknown"
        return Paths.quilt_metadata_root() / "catalogs" / f"{filename}.json"

    @staticmethod
    def quilt_install_metadata_json(game_version: str, loader_version: str) -> Path:
        from urllib.parse import quote

        game = quote(game_version, safe="") or "unknown"
        loader = quote(loader_version, safe="") or "unknown"
        return Paths.quilt_metadata_root() / "install" / game / f"{loader}.json"

    @staticmethod
    def quilt_profile_json(game_version: str, loader_version: str) -> Path:
        from urllib.parse import quote

        game = quote(game_version, safe="") or "unknown"
        loader = quote(loader_version, safe="") or "unknown"
        return Paths.quilt_metadata_root() / "profiles" / game / f"{loader}.json"

    @staticmethod
    def neoforge_root() -> Path:
        directory = Paths.CACHE_ROOT / "modloaders" / "neoforge"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def neoforge_version_dir(game_version: str, neoforge_version: str) -> Path:
        directory = Paths.CACHE_ROOT / "versions" / f"neoforge-{game_version}-{neoforge_version}"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def neoforge_version_json(game_version: str, neoforge_version: str) -> Path:
        directory = Paths.neoforge_version_dir(game_version, neoforge_version)
        return directory / f"{directory.name}.json"

    @staticmethod
    def neoforge_installer_path(game_version: str, neoforge_version: str) -> Path:
        directory = Paths.neoforge_root() / "installers" / game_version
        directory.mkdir(parents=True, exist_ok=True)
        if str(game_version).strip() == "1.20.1":
            artifact = "forge"
            prefix = f"{game_version}-"
            coordinate_version = neoforge_version if str(neoforge_version).startswith(prefix) else f"{prefix}{neoforge_version}"
        else:
            artifact = "neoforge"
            coordinate_version = neoforge_version
        return directory / f"{artifact}-{coordinate_version}-installer.jar"

    @staticmethod
    def neoforge_staging_dir(game_version: str, neoforge_version: str) -> Path:
        directory = Paths.short_workspace_root() / "neo" / f"{game_version}-{neoforge_version}"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def forge_root() -> Path:
        directory = Paths.CACHE_ROOT / "modloaders" / "forge"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def forge_version_dir(game_version: str, forge_version: str) -> Path:
        directory = Paths.CACHE_ROOT / "versions" / f"forge-{game_version}-{forge_version}"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def forge_version_json(game_version: str, forge_version: str) -> Path:
        directory = Paths.forge_version_dir(game_version, forge_version)
        return directory / f"{directory.name}.json"

    @staticmethod
    def forge_installer_path(game_version: str, forge_version: str) -> Path:
        directory = Paths.forge_root() / "installers" / game_version
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"forge-{game_version}-{forge_version}-installer.jar"

    @staticmethod
    def forge_staging_dir(game_version: str, forge_version: str) -> Path:
        directory = Paths.short_workspace_root() / "frg" / f"{game_version}-{forge_version}"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def forge_instance_root(instance: Instance) -> Path:
        directory = Path(instance.instance_dir) / ".mcw" / "forge"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def forge_rollback_path(instance: Instance) -> Path:
        return Paths.forge_instance_root(instance) / "previous-installation.json"

    @staticmethod
    def forge_instance_log_path(instance: Instance) -> Path:
        directory = Paths.forge_instance_root(instance) / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / "forge-change.log"

    @staticmethod
    def forge_diagnostics_default_path(instance: Instance) -> Path:
        from datetime import datetime

        raw_loader = getattr(instance, "mod_loader", None)
        loader_name = str(raw_loader[0] if isinstance(raw_loader, (tuple, list)) and raw_loader else raw_loader or "").strip().casefold()
        loader_title = {"neoforge": "NeoForge", "quilt": "Quilt"}.get(loader_name, "Forge")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_name = "".join(character if character.isalnum() or character in {"-", "_"} else "-" for character in instance.name).strip("-") or "instance"
        return Paths.logs_root() / f"MCW-{loader_title}-Diagnostics-{safe_name}-{timestamp}.zip"

    @staticmethod
    def ftb_root() -> Path:
        directory = Paths.CACHE_ROOT / "content" / "ftb"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def ftb_api_cache_root() -> Path:
        directory = Paths.ftb_root() / "api-v1"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def ftb_artifact_cache_root() -> Path:
        directory = Paths.ftb_root() / "files"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def ftb_file_cache(project_id: int | str, version_id: int | str, filename: str) -> Path:
        safe_name = Path(str(filename)).name or "download.bin"
        return Paths.ftb_artifact_cache_root() / str(project_id) / str(version_id) / safe_name

    @staticmethod
    def ftb_pack_registry(instance: Instance) -> Path:
        return Path(instance.instance_dir) / ".mcw" / "ftb-pack.json"

    @staticmethod
    def atlauncher_root() -> Path:
        directory = Paths.CACHE_ROOT / "content" / "atlauncher"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def atlauncher_api_cache_root() -> Path:
        directory = Paths.atlauncher_root() / "api"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def atlauncher_pack_registry(instance: Instance) -> Path:
        return Path(instance.instance_dir) / ".mcw" / "atlauncher-pack.json"

    @staticmethod
    def curseforge_root() -> Path:
        directory = Paths.CACHE_ROOT / "content" / "curseforge"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def curseforge_api_cache_root() -> Path:
        directory = Paths.curseforge_root() / "api-v2"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def curseforge_artifact_cache_root() -> Path:
        directory = Paths.curseforge_root() / "files"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def curseforge_api_cache(cache_key: str) -> Path:
        return Paths.curseforge_api_cache_root() / "entries" / f"{cache_key}.json"

    @staticmethod
    def curseforge_file_cache(project_id: int | str, file_id: int | str, filename: str) -> Path:
        safe_name = Path(str(filename)).name or "download.bin"
        return Paths.curseforge_artifact_cache_root() / str(project_id) / str(file_id) / safe_name

    @staticmethod
    def curseforge_pack_cache(project_id: int | str, file_id: int | str, filename: str) -> Path:
        return Paths.curseforge_file_cache(project_id, file_id, filename)

    @staticmethod
    def instance_artwork_cache(provider: str, project_id: str, artwork_url: str) -> Path:
        import hashlib
        from urllib.parse import quote

        provider_name = quote(str(provider).strip().casefold(), safe="") or "provider"
        project_name = quote(str(project_id).strip(), safe="") or "unknown"
        digest = hashlib.sha256(str(artwork_url).strip().encode("utf-8")).hexdigest()
        directory = Paths.CACHE_ROOT / "content" / "artwork" / provider_name / project_name
        directory.mkdir(parents=True, exist_ok=True)
        return directory / digest

    @staticmethod
    def curseforge_instance_registry(instance: Instance) -> Path:
        return Path(instance.instance_dir) / ".mcw" / "curseforge.json"

    @staticmethod
    def curseforge_instance_transaction_root(instance: Instance) -> Path:
        directory = Path(instance.instance_dir) / ".mcw" / "transactions" / "curseforge"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def curseforge_pack_registry(instance: Instance) -> Path:
        return Path(instance.instance_dir) / ".mcw" / "curseforge-pack.json"


    @staticmethod
    def instance_logs_dir(instance: Instance) -> Path:
        directory = Paths.load_instance_dir(instance.name) / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def instance_crash_reports_dir(instance: Instance) -> Path:
        directory = Paths.load_instance_dir(instance.name) / "crash-reports"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def instance_runtime_history(instance: Instance) -> Path:
        return Paths.load_instance_dir(instance.name) / ".mcw" / "runtime-history.json"

    @staticmethod
    def instance_repair_report(instance: Instance) -> Path:
        return Paths.load_instance_dir(instance.name) / ".mcw" / "last-repair.json"

    @staticmethod
    def instance_repair_cache(instance: Instance) -> Path:
        instance_dir = Path(getattr(instance, "instance_dir", Paths.load_instance_dir(instance.name)))
        return instance_dir / ".mcw" / "repair-verification-cache.json"

    @staticmethod
    def instance_repair_scan_report(instance: Instance) -> Path:
        instance_dir = Path(getattr(instance, "instance_dir", Paths.load_instance_dir(instance.name)))
        return instance_dir / ".mcw" / "last-repair-scan.json"

    @staticmethod
    def instance_repair_execution_report(instance: Instance) -> Path:
        instance_dir = Path(getattr(instance, "instance_dir", Paths.load_instance_dir(instance.name)))
        return instance_dir / ".mcw" / "last-repair-execution.json"

    @staticmethod
    def instance_mods_dir(instance: Instance) -> Path:
        directory = Path(instance.instance_dir) / "mods"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def mod_provenance_registry(instance: Instance) -> Path:
        return Path(instance.instance_dir) / ".mcw" / "mod-provenance.json"

    @staticmethod
    def optifine_root() -> Path:
        directory = Paths.CACHE_ROOT / "content" / "optifine"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def optifine_metadata_cache() -> Path:
        return Paths.optifine_root() / "metadata" / "downloads.json"

    @staticmethod
    def optifine_source_cache(sha256: str, filename: str = "OptiFine.jar") -> Path:
        digest = str(sha256 or "").strip().casefold() or "unknown"
        safe_name = Path(str(filename)).name or "OptiFine.jar"
        return Paths.optifine_root() / "files" / digest[:2] / digest / safe_name

    @staticmethod
    def optifine_staging_dir(instance: Instance) -> Path:
        identity = str(getattr(instance, "instance_id", getattr(instance, "name", "unknown")))
        directory = Paths.optifine_root() / "staging" / identity
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def optifine_registry(instance: Instance) -> Path:
        instance_dir = Path(getattr(instance, "instance_dir", Paths.load_instance_dir(str(getattr(instance, "name", "")))))
        return instance_dir / ".mcw" / "optifine.json"

    @staticmethod
    def optifine_profile(instance: Instance) -> Path:
        instance_dir = Path(getattr(instance, "instance_dir", Paths.load_instance_dir(str(getattr(instance, "name", "")))))
        return instance_dir / ".mcw" / "optifine-profile.json"

    @staticmethod
    def modrinth_root() -> Path:
        directory = Paths.CACHE_ROOT / "content" / "modrinth"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def modrinth_api_cache_root() -> Path:
        directory = Paths.modrinth_root() / "api"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def modrinth_artifact_cache_root() -> Path:
        directory = Paths.modrinth_root() / "files"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def modrinth_api_cache(cache_key: str) -> Path:
        return Paths.modrinth_api_cache_root() / f"{cache_key}.json"

    @staticmethod
    def modrinth_file_cache(project_id: str, version_id: str, filename: str) -> Path:
        from urllib.parse import quote

        project = quote(str(project_id).strip(), safe="") or "unknown-project"
        version = quote(str(version_id).strip(), safe="") or "unknown-version"
        safe_name = Path(str(filename)).name or "download.bin"
        return Paths.modrinth_artifact_cache_root() / project / version / safe_name

    @staticmethod
    def modrinth_pack_cache(project_id: str, version_id: str, filename: str) -> Path:
        return Paths.modrinth_file_cache(project_id, version_id, filename)

    @staticmethod
    def modrinth_staging_root() -> Path:
        directory = Paths.short_workspace_root() / "mrd"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def modrinth_instance_registry(instance: Instance) -> Path:
        return Path(instance.instance_dir) / ".mcw" / "modrinth.json"

    @staticmethod
    def libraries():
        return Paths.CACHE_ROOT / "libraries"
    
    
    @staticmethod
    def version_manifest() -> Path:
        return Paths.CACHE_ROOT / "manifest" / "version_manifest_v2.json"


    @staticmethod
    def version_json(version:Version) -> Path:
        return Paths.version_dir(version) / f"{version.id}.json"
    
    @staticmethod
    def asset_index(version:Version):
        return Paths.CACHE_ROOT / "assets" / "indexes" / f"{version.assets}.json"
    
    @staticmethod
    def asset_index_dir():
        return Paths.CACHE_ROOT / "assets" / "objects" 


    @staticmethod
    def asset_object(asset: DownloadAsset):
        directory = Paths.CACHE_ROOT / "assets" / "objects" / asset.sha1[:2] 
        directory.mkdir(parents=True, exist_ok=True)
        return directory / asset.sha1
    
    @staticmethod
    def assets_dir():
        return Paths.CACHE_ROOT / "assets" 
    
    @staticmethod
    def natives(version:Version):
        return Paths.CACHE_ROOT / "natives" / version.id
