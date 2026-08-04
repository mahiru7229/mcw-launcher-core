# Tham chiếu API MCW Core 1.0.1

Tài liệu này liệt kê public re-export modules và signature được đọc trực tiếp từ source/wheel. Kiểu trả về `Any` nghĩa là source không khai báo annotation rõ ràng.

## Top-level `mcw_core`

`Account`, `Authentication`, `CorePaths`, `Instance`, instance state/health models, `LaunchRequest`, `LaunchResult`, `InstanceCreateRequest`, `MCWCore`, services, operation/progress/session models, cancellation helpers and default-core functions.

## `MCWCore` facade

| Call | Return | Notes |
|---|---|---|
| `MCWCore(paths=None)` | `MCWCore` | Applies the data root and creates services. |
| `MCWCore.create_default(root=None)` | `MCWCore` | Creates from a root or current path registry. |
| `core.launch(LaunchRequest)` | `LaunchResult` | Returns after process start; `on_exit` fires later. |
| `get_default_core()` | `MCWCore` | Process singleton. |
| `configure_default_core(paths)` | `MCWCore` | Replaces singleton and process-wide root. |

## Services

### `InstanceService`

`list`, `load`, `list_running`, `is_running`, `status`, `list_statuses`, `health`, `list_health`, `set_icon`, `reset_icon`, `create`, `change_loader`, `repair_loader`, `restore_previous_loader`, `export_loader_diagnostics`, `repair`, `scan_repair`, `execute_repair`, `rename`, `clone`, `delete`, instance package inspect/import/export, modpack package inspect/import/export and manual portable file installation.

### `LoaderService`

`normalize`, `resolve`, `prepare` plus loader constants.

### `JavaService`

`scan`, `latest_feature_release`, `normalize_feature_major`, `install`.

## Granular modules

### `mcw_core.api.account.account_manager`

Tài khoản, skin và account repository.  
Implementation tương thích hiện tại: `src/core/account/account_manager.py`

#### `AccountManager`

| Method | Return |
|---|---|
| `create_offline_account(username: str)` | `Account` |
| `create_microsoft_account(cancel_event: Event \| None=None)` | `Account` |
| `list_accounts()` | `list[Account]` |
| `get_account(account_id: str)` | `Account \| None` |
| `get_selected_account()` | `Account \| None` |
| `set_selected_account(account_id: str)` | `bool` |
| `synchronize_microsoft_profile(account_id: str)` | `Account` |
| `remove_account(account_id: str)` | `bool` |
| `is_account_exist(username: str)` | `bool` |


### `mcw_core.api.account.account_skin_manager`

Tài khoản, skin và account repository.  
Implementation tương thích hiện tại: `src/core/account/account_skin_manager.py`

#### `AccountSkinManager`
Cache Minecraft skin textures without making the GUI depend on network APIs.

| Method | Return |
|---|---|
| `cache_profile(cls, profile: MinecraftProfile)` | `Path \| None` |
| `cache_account(cls, account: Account)` | `Path \| None` |
| `cache_texture(cls, profile_uuid: str, skin_url: str)` | `Path` |
| `cached_texture(cls, account_or_uuid: Account \| str)` | `Path \| None` |
| `remove_cached_texture(cls, account_or_uuid: Account \| str)` | `None` |
| `texture_path(profile_uuid: str)` | `Path` |


### `mcw_core.api.auth.microsoft.microsoft_auth_gate`

Authentication Microsoft/OAuth.  
Implementation tương thích hiện tại: `src/core/auth/microsoft/microsoft_auth_gate.py`

#### `MicrosoftAuthenticationLockedError`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `MicrosoftAuthenticationAvailability`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `MicrosoftAuthenticationGate`

| Method | Return |
|---|---|
| `availability()` | `MicrosoftAuthenticationAvailability` |
| `require_enabled()` | `None` |


### `mcw_core.api.auth.microsoft.oauth_callback_server`

Authentication Microsoft/OAuth.  
Implementation tương thích hiện tại: `src/core/auth/microsoft/oauth_callback_server.py`

#### `MicrosoftAuthorizationCancelledError`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `OAuthCallbackHandler`

| Method | Return |
|---|---|
| `do_GET(self)` | `None` |
| `log_message(self, format: str, *args)` | `None` |

#### `ReusableOAuthHTTPServer`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `OAuthCallbackServer`

| Method | Return |
|---|---|
| `wait_for_callback(timeout: float=180.0, cancel_event: Event \| None=None)` | `tuple[str, str]` |


### `mcw_core.api.backup.instance_backup_manager`

Backup và restore instance.  
Implementation tương thích hiện tại: `src/core/backup/instance_backup_manager.py`

#### `InstanceBackupManager`

| Method | Return |
|---|---|
| `create(instance: Instance, scope: str=SCOPE_FULL, reason: str='manual', destination: Path \| None=None)` | `InstanceBackupResult` |
| `inspect(path: Path)` | `InstanceBackupInfo` |
| `list_backups(instance: Instance)` | `list[InstanceBackupInfo]` |
| `restore(instance: Instance, backup_path: Path, create_safety_backup: bool=True)` | `InstanceRestoreResult` |


### `mcw_core.api.bootstrap`

Implementation tương thích hiện tại: `src/core/bootstrap.py`

- `initialize_application(progress_callback: BootstrapProgressCallback | None=None) -> dict[str, Any]` — Prepare persistent application resources and report startup progress when requested.

### `mcw_core.api.config.curseforge_config_manager`

Launcher settings, CurseForge gateway và policy.  
Implementation tương thích hiện tại: `src/core/config/curseforge_config_manager.py`

#### `CurseForgeConfigManager`
Loads CurseForge gateway endpoints with safe local overrides.

| Method | Return |
|---|---|
| `path()` | `Path` |
| `legacy_path()` | `Path` |
| `gateway_urls(cls)` | `tuple[str, ...]` |
| `gateway_url(cls)` | `str` |
| `client_token(cls)` | `str` |
| `is_configured(cls)` | `bool` |
| `save_local(cls, gateway_urls: Iterable[str] \| str, client_token: str \| None=None)` | `Path` |


### `mcw_core.api.config.launcher_settings_manager`

Launcher settings, CurseForge gateway và policy.  
Implementation tương thích hiện tại: `src/core/config/launcher_settings_manager.py`

#### `LauncherSettingsManager`

| Method | Return |
|---|---|
| `initialize(self)` | `Path` |
| `load(self)` | `dict[str, Any]` |
| `save(self, settings: dict[str, Any])` | `dict[str, Any]` |
| `update_section(self, section: str, values: dict[str, Any])` | `dict[str, Any]` |
| `reset(self)` | `dict[str, Any]` |
| `load_window_geometry(self)` | `bytes \| None` |
| `save_window_geometry(self, geometry: bytes \| bytearray \| memoryview)` | `None` |


### `mcw_core.api.config.managed_content_policy`

Launcher settings, CurseForge gateway và policy.  
Implementation tương thích hiện tại: `src/core/config/managed_content_policy.py`

#### `ManagedContentPolicy`

| Method | Return |
|---|---|
| `normalize_instance(cls, value: object, default: str=INHERIT)` | `str` |
| `normalize_global(cls, value: object, default: str=BLOCK)` | `str` |
| `from_legacy_bool(cls, value: object, default: bool=True)` | `str` |
| `resolve(cls, instance_settings: object, launcher_settings: dict[str, Any], provider: str)` | `str` |
| `blocks_launch(cls, instance_settings: object, launcher_settings: dict[str, Any], provider: str)` | `bool` |


### `mcw_core.api.content.content_pack_manager`

Resource pack, shader pack và Content Library.  
Implementation tương thích hiện tại: `src/core/content/content_pack_manager.py`

#### `ContentPackManager`

| Method | Return |
|---|---|
| `list_entries(cls, instance: Instance, content_type: str='')` | `list[ContentPackEntry]` |
| `install_modrinth(cls, instance: Instance, content_type: str, version_id: str, reporter: ProgressReporter \| None=None)` | `ContentPackInstallResult` |
| `install_curseforge(cls, instance: Instance, content_type: str, file: CurseForgeFile, project_name: str='', project_url: str='', reporter: ProgressReporter \| None=None)` | `ContentPackInstallResult` |
| `import_local(cls, instance: Instance, content_type: str, source: Path)` | `ContentPackInstallResult` |
| `set_enabled(cls, instance: Instance, entry_id: str, enabled: bool)` | `ContentPackEntry` |
| `remove(cls, instance: Instance, entry_id: str)` | `ContentPackEntry` |
| `destination_dir(cls, instance: Instance, content_type: str)` | `Path` |
| `validate_archive(cls, source: Path, content_type: str)` | `dict[str, object]` |
| `normalize_type(cls, value: str)` | `str` |
| `display_name(cls, content_type: str)` | `str` |
| `curseforge_project_url(cls, content_type: str, project_id: int \| str)` | `str` |


### `mcw_core.api.content.content_pack_registry`

Resource pack, shader pack và Content Library.  
Implementation tương thích hiện tại: `src/core/content/content_pack_registry.py`

#### `ContentPackRegistry`

| Method | Return |
|---|---|
| `path(cls, instance: Instance)` | `Path` |
| `load(cls, instance: Instance)` | `dict` |
| `save(cls, instance: Instance, payload: dict)` | `Path` |
| `entries(cls, instance: Instance, content_type: str='')` | `list[ContentPackEntry]` |
| `upsert(cls, instance: Instance, entry: ContentPackEntry)` | `None` |
| `remove(cls, instance: Instance, entry_id: str)` | `ContentPackEntry \| None` |


### `mcw_core.api.content.installed_content_library`

Resource pack, shader pack và Content Library.  
Implementation tương thích hiện tại: `src/core/content/installed_content_library.py`

#### `InstalledContentLibraryManager`

| Method | Return |
|---|---|
| `scan(cls, instance: Instance)` | `InstalledContentLibrary` |
| `set_enabled(cls, instance: Instance, item_ids: list[str] \| tuple[str, ...], enabled: bool)` | `tuple[str, ...]` |
| `remove(cls, instance: Instance, item_ids: list[str] \| tuple[str, ...])` | `tuple[str, ...]` |
| `set_pinned(instance: Instance, item_ids: list[str] \| tuple[str, ...], pinned: bool)` | `tuple[str, ...]` |
| `set_ignored_update(instance: Instance, item_ids: list[str] \| tuple[str, ...], ignored: bool)` | `tuple[str, ...]` |
| `destination_folder(cls, instance: Instance, content_type: str)` | `Path` |


### `mcw_core.api.curseforge.curseforge_client`

Search, metadata, download và installer CurseForge.  
Implementation tương thích hiện tại: `src/core/curseforge/curseforge_client.py`

#### `CurseForgeClient`

| Method | Return |
|---|---|
| `is_available()` | `bool` |
| `gateway_urls()` | `tuple[str, ...]` |
| `gateway_url()` | `str` |
| `cache_status()` | `CurseForgeCacheInfo` |
| `clear_cache()` | `None` |
| `manual_refresh_remaining_seconds()` | `int` |
| `search_projects(project_type: str, query: str='', game_version: str='', loader: str='forge', index: int=0, page_size: int=25, sort: str='popularity', force_refresh: bool=False, manual_refresh: bool=False)` | `CurseForgeSearchResult` |
| `get_project(project_id: int \| str, force_refresh: bool=False)` | `CurseForgeProject` |
| `get_project_details(project_id: int \| str, force_refresh: bool=False)` | `CurseForgeProject` |
| `get_projects_batch(project_ids: list[int] \| tuple[int, ...] \| set[int])` | `dict[int, CurseForgeProject]` |
| `list_files_result(project_id: int \| str, game_version: str='', loader: str='forge', release_types: tuple[str, ...] \| list[str] \| set[str] \| None=None, page_size: int=50, force_refresh: bool=False, manual_refresh: bool=False)` | `CurseForgeFileListResult` |
| `list_files(project_id: int \| str, game_version: str='', loader: str='forge', release_types: tuple[str, ...] \| list[str] \| set[str] \| None=None, page_size: int=50, force_refresh: bool=False)` | `list[CurseForgeFile]` |
| `get_file(project_id: int \| str, file_id: int \| str, force_refresh: bool=False)` | `CurseForgeFile` |
| `get_files_batch(file_ids: list[int] \| tuple[int, ...] \| set[int])` | `dict[int, CurseForgeFile]` |
| `get_download_url(project_id: int \| str, file_id: int \| str, force_refresh: bool=False)` | `str` |
| `latest_compatible_file(project_id: int \| str, game_version: str, loader: str='forge', release_types: tuple[str, ...] \| list[str] \| set[str] \| None=None)` | `CurseForgeFile` |
| `normalize_loader(loader: str)` | `str` |
| `loader_compatibility(file: CurseForgeFile, loader: str)` | `str` |
| `is_permanent_error(error: BaseException)` | `bool` |
| `normalize_release_types(release_types: tuple[str, ...] \| list[str] \| set[str] \| None=None)` | `tuple[str, ...]` |


### `mcw_core.api.curseforge.curseforge_errors`

Search, metadata, download và installer CurseForge.  
Implementation tương thích hiện tại: `src/core/curseforge/curseforge_errors.py`

#### `CurseForgeManagedFilesRequired`
Raised when managed CurseForge files require user-assisted recovery.
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `CurseForgeModpackManualDownloadRequired`
Raised when a CurseForge modpack archive must be downloaded manually.
- Exception/data class; xem field trong source hoặc typed exception handler.


### `mcw_core.api.curseforge.curseforge_manual_installer`

Search, metadata, download và installer CurseForge.  
Implementation tương thích hiện tại: `src/core/curseforge/curseforge_manual_installer.py`

#### `CurseForgeManualInstaller`

| Method | Return |
|---|---|
| `install(instance: Instance, requirement: CurseForgeManualDownload, source: Path)` | `str` |
| `install_many(instance: Instance, requirements: tuple[CurseForgeManualDownload, ...] \| list[CurseForgeManualDownload], sources: tuple[Path, ...] \| list[Path])` | `CurseForgeManualImportResult` |
| `copy_to_cache(source: Path, destination: Path)` | `Path` |


### `mcw_core.api.curseforge.curseforge_mod_installer`

Search, metadata, download và installer CurseForge.  
Implementation tương thích hiện tại: `src/core/curseforge/curseforge_mod_installer.py`

#### `CurseForgeModInstaller`

| Method | Return |
|---|---|
| `install(instance: Instance, project_id: int, file_id: int, install_dependencies: bool=True, allowed_release_types: tuple[str, ...] \| list[str] \| set[str] \| None=None, reporter: ProgressReporter \| None=None, allow_unverified: bool=False)` | `CurseForgeModInstallResult` |


### `mcw_core.api.curseforge.curseforge_pack_installer`

Search, metadata, download và installer CurseForge.  
Implementation tương thích hiện tại: `src/core/curseforge/curseforge_pack_installer.py`

#### `CurseForgePackInstaller`

| Method | Return |
|---|---|
| `install(project_id: int, file_id: int, instance_name: str, install_optional_files: bool=True, allowed_release_types: tuple[str, ...] \| list[str] \| set[str] \| None=None, reporter: ProgressReporter \| None=None, expected_loader: str='', settings_override: dict \| None=None)` | `CurseForgeModpackInstallResult` |
| `install_local_archive(pack_path: Path, instance_name: str='', install_optional_files: bool=True, reporter: ProgressReporter \| None=None, settings_override: dict \| None=None)` | `CurseForgeModpackInstallResult` |
| `install_manual_archive(request: CurseForgeModpackManualDownloadRequired, source: Path, reporter: ProgressReporter \| None=None)` | `CurseForgeModpackInstallResult` |


### `mcw_core.api.curseforge.curseforge_registry`

Search, metadata, download và installer CurseForge.  
Implementation tương thích hiện tại: `src/core/curseforge/curseforge_registry.py`

#### `CurseForgeRegistry`

| Method | Return |
|---|---|
| `empty()` | `dict` |
| `load(instance: Instance)` | `dict` |
| `save(instance: Instance, data: dict)` | `None` |
| `remove_by_filenames(instance: Instance, filenames: list[str] \| tuple[str, ...] \| set[str])` | `tuple[str, ...]` |
| `safe_tracked_path(instance: Instance, filename: str)` | `Path \| None` |


### `mcw_core.api.diagnostics.diagnostics_manager`

Diagnostic report/bundle.  
Implementation tương thích hiện tại: `src/core/diagnostics/diagnostics_manager.py`

#### `DiagnosticsManager`

| Method | Return |
|---|---|
| `build_report(cls, launcher_version: str, settings: dict[str, Any] \| None=None, activity_log: str='')` | `str` |
| `write_report(cls, path: Path, launcher_version: str, settings: dict[str, Any] \| None=None, activity_log: str='')` | `Path` |
| `write_bundle(cls, path: Path, launcher_version: str, settings: dict[str, Any] \| None=None, activity_log: str='')` | `Path` |


### `mcw_core.api.fs.paths`

Đường dẫn và filesystem root.  
Implementation tương thích hiện tại: `src/core/fs/paths.py`

#### `Paths`

| Method | Return |
|---|---|
| `initialize()` | `None` |
| `backups_root()` | `Path` |
| `instance_backups_dir(instance: Instance)` | `Path` |
| `backup_staging_root()` | `Path` |
| `theme_asset(theme: str, *paths: str)` | `Path` |
| `theme_dir(name: str)` | `Path` |
| `root()` | `Path` |
| `snapshot()` | `dict[str, Path]` |
| `restore(snapshot: dict[str, Path], initialize: bool=False)` | `None` |
| `configure(root: Path \| str \| None=None, *, cache_root: Path \| str \| None=None, instances_root: Path \| str \| None=None, accounts_root: Path \| str \| None=None, config_root: Path \| str \| None=None, logs_root: Path \| str \| None=None, backups_root: Path \| str \| None=None, theme_root: Path \| str \| None=None, runtimes_root: Path \| str \| None=None, initialize: bool=True)` | `dict[str, Path]` |
| `configured(root: Path \| str \| None=None, **overrides: object)` | `Iterator[None]` |
| `microsoft_config_root()` | `Path` |
| `launcher_settings_path()` | `Path` |
| `logs_root()` | `Path` |
| `updater_log_path()` | `Path` |
| `diagnostics_default_path()` | `Path` |
| `download_journal_path()` | `Path` |
| `update_root()` | `Path` |
| `update_release_cache()` | `Path` |
| `update_download_path(tag_name: str, asset_name: str)` | `Path` |
| `update_staging_root()` | `Path` |
| `account_database_path()` | `Any` |
| `account_skins_root()` | `Path` |
| `accounts_path()` | `Path` |
| `instance_metadata(instance_name: str)` | `Path` |
| `instance_settings_path(instance: Instance)` | `Path` |
| `instance_settings_create(instance: Instance)` | `Path` |
| `instances_root()` | `Path` |
| `instance_runtime_root()` | `Path` |
| `instance_operations_root()` | `Path` |
| `instance_staging_root()` | `Path` |
| `process_sessions_root()` | `Path` |
| `process_session_history_root()` | `Path` |
| `load_instance_dir(name: str)` | `Path` |
| `create_instance_dir(name: str)` | `Path` |
| `instance_data_path_create()` | `Any` |
| `instance_data_path()` | `Any` |
| `version_dir(version: Version)` | `Any` |
| `client(version: Version)` | `Any` |
| `fabric_version_dir(game_version: str, loader_version: str)` | `Path` |
| `fabric_version_json(game_version: str, loader_version: str)` | `Path` |
| `fabric_metadata_root()` | `Path` |
| `fabric_catalog_json(game_version: str)` | `Path` |
| `fabric_install_metadata_json(game_version: str, loader_version: str)` | `Path` |
| `fabric_profile_json(game_version: str, loader_version: str)` | `Path` |
| `quilt_version_dir(game_version: str, loader_version: str)` | `Path` |
| `quilt_version_json(game_version: str, loader_version: str)` | `Path` |
| `quilt_metadata_root()` | `Path` |
| `quilt_catalog_json(game_version: str)` | `Path` |
| `quilt_install_metadata_json(game_version: str, loader_version: str)` | `Path` |
| `quilt_profile_json(game_version: str, loader_version: str)` | `Path` |
| `neoforge_root()` | `Path` |
| `neoforge_version_dir(game_version: str, neoforge_version: str)` | `Path` |
| `neoforge_version_json(game_version: str, neoforge_version: str)` | `Path` |
| `neoforge_installer_path(game_version: str, neoforge_version: str)` | `Path` |
| `neoforge_staging_dir(game_version: str, neoforge_version: str)` | `Path` |
| `forge_root()` | `Path` |
| `forge_version_dir(game_version: str, forge_version: str)` | `Path` |
| `forge_version_json(game_version: str, forge_version: str)` | `Path` |
| `forge_installer_path(game_version: str, forge_version: str)` | `Path` |
| `forge_staging_dir(game_version: str, forge_version: str)` | `Path` |
| `forge_instance_root(instance: Instance)` | `Path` |
| `forge_rollback_path(instance: Instance)` | `Path` |
| `forge_instance_log_path(instance: Instance)` | `Path` |
| `forge_diagnostics_default_path(instance: Instance)` | `Path` |
| `ftb_root()` | `Path` |
| `ftb_file_cache(project_id: int \| str, version_id: int \| str, filename: str)` | `Path` |
| `ftb_pack_registry(instance: Instance)` | `Path` |
| `curseforge_root()` | `Path` |
| `curseforge_api_cache(cache_key: str)` | `Path` |
| `curseforge_file_cache(project_id: int \| str, file_id: int \| str, filename: str)` | `Path` |
| `curseforge_pack_cache(project_id: int \| str, file_id: int \| str, filename: str)` | `Path` |
| `instance_artwork_cache(provider: str, project_id: str, artwork_url: str)` | `Path` |
| `curseforge_instance_registry(instance: Instance)` | `Path` |
| `curseforge_instance_transaction_root(instance: Instance)` | `Path` |
| `curseforge_pack_registry(instance: Instance)` | `Path` |
| `instance_logs_dir(instance: Instance)` | `Path` |
| `instance_crash_reports_dir(instance: Instance)` | `Path` |
| `instance_runtime_history(instance: Instance)` | `Path` |
| `instance_repair_report(instance: Instance)` | `Path` |
| `instance_repair_cache(instance: Instance)` | `Path` |
| `instance_repair_scan_report(instance: Instance)` | `Path` |
| `instance_repair_execution_report(instance: Instance)` | `Path` |
| `instance_mods_dir(instance: Instance)` | `Path` |
| `mod_provenance_registry(instance: Instance)` | `Path` |
| `modrinth_root()` | `Path` |
| `modrinth_api_cache(cache_key: str)` | `Path` |
| `modrinth_file_cache(project_id: str, version_id: str, filename: str)` | `Path` |
| `modrinth_pack_cache(project_id: str, version_id: str, filename: str)` | `Path` |
| `modrinth_staging_root()` | `Path` |
| `modrinth_instance_registry(instance: Instance)` | `Path` |
| `libraries()` | `Any` |
| `version_manifest()` | `Path` |
| `version_json(version: Version)` | `Path` |
| `asset_index(version: Version)` | `Any` |
| `asset_index_dir()` | `Any` |
| `asset_object(asset: DownloadAsset)` | `Any` |
| `assets_dir()` | `Any` |
| `natives(version: Version)` | `Any` |


### `mcw_core.api.ftb.ftb_client`

FTB project/version/installer.  
Implementation tương thích hiện tại: `src/core/ftb/ftb_client.py`

#### `FTBClient`
Small public FTB modpack API adapter.

| Method | Return |
|---|---|
| `cache_status()` | `FTBCacheInfo` |
| `clear_cache()` | `None` |
| `search_projects(query: str='', index: int=0, page_size: int=25, sort: str='popularity', force_refresh: bool=False)` | `FTBSearchResult` |
| `get_project(project_id: int \| str, force_refresh: bool=False)` | `FTBProject` |
| `get_project_details(project_id: int \| str, force_refresh: bool=False)` | `FTBProject` |
| `list_versions(project_id: int \| str, release_types: Iterable[str] \| None=None, force_refresh: bool=False)` | `tuple[FTBVersionSummary, ...]` |
| `get_version(project_id: int \| str, version_id: int \| str, force_refresh: bool=False)` | `FTBVersion` |
| `normalize_release_type(value: object)` | `str` |
| `normalize_loader(value: object)` | `str` |


### `mcw_core.api.ftb.ftb_content_manager`

FTB project/version/installer.  
Implementation tương thích hiện tại: `src/core/ftb/ftb_content_manager.py`

#### `FTBContentManager`
Materialize deferred FTB modpack files immediately before launch.

| Method | Return |
|---|---|
| `ensure(instance: Instance, reporter: ProgressReporter \| None=None, launch_lock_token: str \| None=None)` | `tuple[str, ...]` |


### `mcw_core.api.ftb.ftb_pack_installer`

FTB project/version/installer.  
Implementation tương thích hiện tại: `src/core/ftb/ftb_pack_installer.py`

#### `FTBPackInstaller`

| Method | Return |
|---|---|
| `install(project_id: int, version_id: int, instance_name: str, install_optional_files: bool=True, allowed_release_types: tuple[str, ...] \| list[str] \| set[str] \| None=None, reporter: ProgressReporter \| None=None, settings_override: dict \| None=None)` | `FTBModpackInstallResult` |


### `mcw_core.api.ftb.ftb_pack_registry`

FTB project/version/installer.  
Implementation tương thích hiện tại: `src/core/ftb/ftb_pack_registry.py`

#### `FTBPackRegistry`

| Method | Return |
|---|---|
| `load(instance: Instance \| Path)` | `dict` |
| `save(instance: Instance \| Path, data: dict)` | `None` |
| `safe_relative_path(value: str, fallback_filename: str)` | `str` |


### `mcw_core.api.hardware.gpu_preference_manager`

GPU detection và Windows preference.  
Implementation tương thích hiện tại: `src/core/hardware/gpu_preference_manager.py`

#### `GraphicsAdapter`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `GraphicsDetectionResult`

| Method | Return |
|---|---|
| `dedicated_adapters(self)` | `tuple[GraphicsAdapter, ...]` |
| `has_dedicated_gpu(self)` | `bool` |

#### `GpuPreferenceManager`
Best-effort Windows graphics preference integration.

| Method | Return |
|---|---|
| `detect(cls)` | `GraphicsDetectionResult` |
| `apply_for_executable(cls, executable: Path \| str, enabled: bool)` | `bool` |
| `apply_to_java(cls, java_path: Path \| str, enabled: bool)` | `bool` |
| `adapter_summary(cls, adapters: Iterable[GraphicsAdapter])` | `str` |


### `mcw_core.api.instance.errors`

Instance lifecycle, status, health, journal và settings.  
Implementation tương thích hiện tại: `src/core/instance/errors.py`

#### `InstanceAlreadyRunningError`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `InstanceModChangeBlockedError`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `InstanceDeletionError`
Structured failure raised when an instance cannot be removed safely.
- Exception/data class; xem field trong source hoặc typed exception handler.


### `mcw_core.api.instance.instance_health_manager`

Instance lifecycle, status, health, journal và settings.  
Implementation tương thích hiện tại: `src/core/instance/instance_health_manager.py`

#### `InstanceHealthManager`
Run a fast, non-networked health check suitable for launcher startup.

| Method | Return |
|---|---|
| `scan(cls, instance: Instance)` | `InstanceHealthReport` |
| `list(cls, instances: list[Instance])` | `list[InstanceHealthReport]` |


### `mcw_core.api.instance.instance_manager`

Instance lifecycle, status, health, journal và settings.  
Implementation tương thích hiện tại: `src/core/instance/instance_manager.py`

#### `InstanceManager`

| Method | Return |
|---|---|
| `validate_name(value: str)` | `str` |
| `list_instances()` | `list[Instance]` |
| `clone(source_name: str, new_name: str, include_saves: bool=False)` | `Instance` |
| `export(instance_name: str, output_path: Path, include_saves: bool=False, on_progress: ProgressCallback \| None=None)` | `Path` |
| `set_icon(instance_name: str, source_path: Path, origin: dict \| None=None)` | `Instance` |
| `reset_icon(instance_name: str)` | `Instance` |
| `resolve_icon_path(instance: Instance)` | `Path \| None` |
| `inspect_import(package_path: Path)` | `InstancePackagePreview` |
| `import_instance(package_path: Path, on_progress: ProgressCallback \| None=None, settings_override: dict \| InstanceSettings \| None=None)` | `Instance` |
| `rename(instance_name: str, new_name: str)` | `Path` |
| `load(name: str)` | `Instance` |
| `create(name: str, version: Version, mod_loader=('vanilla', '-1'), settings: dict \| InstanceSettings \| None=None)` | `Instance` |
| `default_instance_settings()` | `dict` |
| `set_runtime_profile(name: str, version: Version, mod_loader: tuple[str, str])` | `Instance` |
| `set_mod_loader(name: str, mod_loader: tuple[str, str])` | `Instance` |
| `delete_instance(name: str)` | `bool` |
| `reconcile_registry()` | `dict` |
| `next_available_name(preferred_name: str)` | `str` |
| `is_instance_exist(name: str)` | `bool` |


### `mcw_core.api.instance.instance_operation_journal`

Instance lifecycle, status, health, journal và settings.  
Implementation tương thích hiện tại: `src/core/instance/instance_operation_journal.py`

#### `InstanceRecoveryRecord`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `InstanceOperationJournal`

| Method | Return |
|---|---|
| `begin(cls, operation: str, instance_name: str, *, source_path: Path \| None=None, target_path: Path \| None=None, staging_path: Path \| None=None)` | `InstanceOperationJournal` |
| `update(self, phase: str, **updates: Any)` | `None` |
| `complete(self)` | `None` |
| `abandon(self)` | `None` |
| `recover_all(cls)` | `tuple[InstanceRecoveryRecord, ...]` |


### `mcw_core.api.instance.instance_run_lock`

Instance lifecycle, status, health, journal và settings.  
Implementation tương thích hiện tại: `src/core/instance/instance_run_lock.py`

#### `RunningInstanceInfo`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `InstanceRunLock`

| Method | Return |
|---|---|
| `acquire(cls, instance: Instance)` | `InstanceRunLock` |
| `track_process(self, process: Any)` | `bool` |
| `release(self)` | `None` |
| `is_active(cls, instance: Instance)` | `bool` |
| `owns_preparing_lock(cls, instance: Instance, token: str \| None)` | `bool` |
| `active_for(cls, instance: Instance)` | `RunningInstanceInfo \| None` |
| `remove_for(cls, instance: Instance, force: bool=False)` | `bool` |
| `reconcile(cls)` | `tuple[str, ...]` |
| `list_active(cls)` | `list[RunningInstanceInfo]` |
| `lock_path_for(cls, instance: Instance)` | `Path` |


### `mcw_core.api.instance.settings_manager`

Instance lifecycle, status, health, journal và settings.  
Implementation tương thích hiện tại: `src/core/instance/settings_manager.py`

- `default_instance_settings() -> dict[str, Any]`
#### `SettingsManager`

| Method | Return |
|---|---|
| `load(instance: Instance)` | `InstanceSettings` |
| `save(instance: Instance, settings: InstanceSettings)` | `None` |
| `save_default(instance: Instance)` | `None` |
| `default_dict(cls)` | `dict[str, Any]` |
| `from_dict(data: dict[str, Any] \| InstanceSettings \| None)` | `InstanceSettings` |
| `to_dict(settings: InstanceSettings)` | `dict[str, Any]` |
| `normalize_dict(data: dict[str, Any] \| InstanceSettings \| None)` | `dict[str, Any]` |
| `save_dict(instance: Instance, data: dict[str, Any] \| InstanceSettings \| None)` | `None` |
| `update_memory(instance: Instance, min_memory: int, max_memory: int)` | `InstanceSettings` |
| `update_java_path(instance: Instance, java_path: str)` | `InstanceSettings` |
| `update_window(instance: Instance, width: int, height: int, fullscreen: bool)` | `InstanceSettings` |
| `update_jvm_arguments(instance: Instance, arguments: list[str])` | `InstanceSettings` |
| `update_game_arguments(instance: Instance, arguments: list[str])` | `InstanceSettings` |


### `mcw_core.api.java.java_major_policy`

Java policy/metadata.  
Implementation tương thích hiện tại: `src/core/java/java_major_policy.py`

#### `JavaMajorPolicy`

| Method | Return |
|---|---|
| `resolve(cls, required_major: int \| None)` | `int` |
| `accepted_majors(cls, required_major: int \| None)` | `tuple[int, ...]` |


### `mcw_core.api.lan.lan_agent_manager`

LAN agent và hosting.  
Implementation tương thích hiện tại: `src/core/lan/lan_agent_manager.py`

#### `LanAgentInstallResult`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `LanAgentManager`
Install and attach the bundled host-side LAN agent.

| Method | Return |
|---|---|
| `is_enabled(cls, auth_mode: object)` | `bool` |
| `install(cls)` | `LanAgentInstallResult` |
| `runtime_arguments(cls, version: Version, auth_mode: object, instance: Instance, reporter: ProgressReporter \| None=None)` | `list[str]` |
| `log_path(cls, instance: Instance)` | `Path` |
| `prepare_log(cls, instance: Instance, auth_mode: object='unknown')` | `Path` |
| `append_log(cls, instance: Instance, message: str)` | `None` |
| `append_log_path(path: Path, message: str)` | `None` |
| `read_log(cls, instance: Instance)` | `str` |
| `sanitize_user_jvm_arguments(cls, arguments: list[str])` | `list[str]` |
| `runtime_agent_path(cls)` | `Path` |


### `mcw_core.api.lan.lan_hosting_manager`

LAN agent và hosting.  
Implementation tương thích hiện tại: `src/core/lan/lan_hosting_manager.py`

#### `LanHostingManager`
Prepare per-instance LAN hosting support.

| Method | Return |
|---|---|
| `normalize_auth_mode(value: object)` | `str` |
| `normalize_connection_provider(value: object)` | `str` |
| `plan(instance: Instance, auth_mode: object, connection_provider: object)` | `LanHostingPlan` |
| `prepare(instance: Instance, auth_mode: object, connection_provider: object, reporter: ProgressReporter \| None=None)` | `LanHostingPrepareResult` |
| `disable_legacy_auth_bridges(instance: Instance)` | `tuple[str, ...]` |


### `mcw_core.api.language.language_manager`

Language pack và translation.  
Implementation tương thích hiện tại: `src/core/language/language_manager.py`

#### `LanguageInfo`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `LanguageManager`

| Method | Return |
|---|---|
| `current_locale(self)` | `str` |
| `language_dir(self)` | `Path` |
| `language_dirs(self)` | `tuple[Path, ...]` |
| `reload(self)` | `list[LanguageInfo]` |
| `available_languages(self)` | `list[LanguageInfo]` |
| `set_language(self, locale: str, notify: bool=True)` | `bool` |
| `resolve_key(self, key: str)` | `str` |
| `translate(self, key: str, default: str \| None=None, **values: object)` | `str` |
| `has_key(self, key: str)` | `bool` |
| `missing_keys(self, locale: str \| None=None)` | `list[str]` |
| `placeholder_mismatches(self, locale: str \| None=None)` | `dict[str, tuple[set[str], set[str]]]` |
| `subscribe(self, listener: Callable[[str], None])` | `None` |
| `unsubscribe(self, listener: Callable[[str], None])` | `None` |

- `tr(key: str, default: str | None=None, **values: object) -> str`

### `mcw_core.api.minecraft.version_manifest_manager`

Minecraft version manifest.  
Implementation tương thích hiện tại: `src/core/minecraft/version_manifest_manager.py`

#### `VersionManifestManager`

| Method | Return |
|---|---|
| `get()` | `list[VersionManifest]` |
| `latest_version(is_snapshot: bool=False)` | `str` |


### `mcw_core.api.mod.mod_compatibility_manager`

Mod files, compatibility và provenance.  
Implementation tương thích hiện tại: `src/core/mod/mod_compatibility_manager.py`

#### `ModCompatibilityManager`

| Method | Return |
|---|---|
| `scan(instance: Instance, mods: list[ModInfo] \| None=None)` | `ModHealthReport` |


### `mcw_core.api.mod.mod_manager`

Mod files, compatibility và provenance.  
Implementation tương thích hiện tại: `src/core/mod/mod_manager.py`

#### `ModManager`

| Method | Return |
|---|---|
| `mods_dir(instance: Instance)` | `Path` |
| `list_mods(instance: Instance)` | `list[ModInfo]` |
| `add_mods(instance: Instance, source_paths: Iterable[Path], replace: bool=False, launch_lock_token: str \| None=None, allow_unverified: bool=False)` | `list[ModInfo]` |
| `remove_mods(instance: Instance, paths: Iterable[Path])` | `None` |
| `set_enabled(instance: Instance, paths: Iterable[Path], enabled: bool)` | `list[ModInfo]` |
| `read_mod(path: Path, preferred_loader: str='', provider_version: str='')` | `ModInfo` |
| `validate_mod_for_instance(instance: Instance, mod: ModInfo, allow_unverified: bool=False)` | `None` |
| `compatibility_warning(instance: Instance, mod: ModInfo)` | `str` |
| `ensure_modifiable(instance: Instance, launch_lock_token: str \| None=None)` | `None` |


### `mcw_core.api.mod.mod_provenance_registry`

Mod files, compatibility và provenance.  
Implementation tương thích hiện tại: `src/core/mod/mod_provenance_registry.py`

#### `ModProvenanceRegistry`
Unified source identity for installed and manifest-managed mod files.

| Method | Return |
|---|---|
| `empty()` | `dict` |
| `load(instance: Instance)` | `dict` |
| `save(instance: Instance, data: dict)` | `None` |
| `synchronize(instance: Instance)` | `dict[str, dict]` |
| `entries_by_file(instance: Instance, synchronize: bool=True)` | `dict[str, dict]` |
| `entry_for_file(instance: Instance, filename: str)` | `dict \| None` |
| `record_many(instance: Instance, entries: list[dict] \| tuple[dict, ...])` | `None` |
| `remove_by_filenames(instance: Instance, filenames: list[str] \| tuple[str, ...] \| set[str])` | `tuple[str, ...]` |


### `mcw_core.api.modloader.fabric.fabric_meta_client`

Fabric/Quilt/Forge/NeoForge.  
Implementation tương thích hiện tại: `src/core/modloader/fabric/fabric_meta_client.py`

#### `FabricMetaClient`

| Method | Return |
|---|---|
| `list_loader_versions(game_version: str, force_refresh: bool=False)` | `list[FabricLoaderVersion]` |
| `get_install_metadata(game_version: str, loader_version: str, force_refresh: bool=False)` | `FabricInstallMetadata` |
| `get_profile(game_version: str, loader_version: str, force_refresh: bool=False)` | `dict` |
| `clear_cached_install(game_version: str, loader_version: str)` | `None` |


### `mcw_core.api.modloader.forge.forge_metadata_client`

Fabric/Quilt/Forge/NeoForge.  
Implementation tương thích hiện tại: `src/core/modloader/forge/forge_metadata_client.py`

#### `ForgeMetadataClient`

| Method | Return |
|---|---|
| `list_versions(game_version: str, force_refresh: bool=False)` | `list[ForgeLoaderVersion]` |
| `recommended_version(game_version: str)` | `str` |
| `installer_url(game_version: str, forge_version: str)` | `str` |
| `installer_sha1(game_version: str, forge_version: str)` | `str` |


### `mcw_core.api.modloader.mod_loader_manager`

Fabric/Quilt/Forge/NeoForge.  
Implementation tương thích hiện tại: `src/core/modloader/mod_loader_manager.py`

#### `ModLoaderManager`

| Method | Return |
|---|---|
| `load(instance: Instance, reporter: ProgressReporter \| None=None)` | `Version` |
| `prepare(version: Version, loader_name: str, loader_version: str, reporter: ProgressReporter \| None=None)` | `Version` |
| `repair(instance: Instance, reporter: ProgressReporter \| None=None)` | `Version` |
| `resolve(game_version: str, loader_name: str, loader_version: str=AUTO)` | `tuple[str, str]` |
| `normalize(mod_loader: object)` | `tuple[str, str]` |


### `mcw_core.api.modloader.neoforge.neoforge_metadata_client`

Fabric/Quilt/Forge/NeoForge.  
Implementation tương thích hiện tại: `src/core/modloader/neoforge/neoforge_metadata_client.py`

#### `NeoForgeMetadataClient`

| Method | Return |
|---|---|
| `list_versions(game_version: str, force_refresh: bool=False)` | `list[NeoForgeLoaderVersion]` |
| `recommended_version(game_version: str)` | `str` |
| `coordinate(game_version: str, neoforge_version: str)` | `tuple[str, str]` |
| `installer_url(game_version: str, neoforge_version: str)` | `str` |
| `installer_sha1(game_version: str, neoforge_version: str)` | `str` |


### `mcw_core.api.modloader.quilt.quilt_meta_client`

Fabric/Quilt/Forge/NeoForge.  
Implementation tương thích hiện tại: `src/core/modloader/quilt/quilt_meta_client.py`

#### `QuiltMetaClient`

| Method | Return |
|---|---|
| `list_loader_versions(game_version: str, force_refresh: bool=False)` | `list[QuiltLoaderVersion]` |
| `version_sort_key(version: str)` | `tuple` |
| `get_install_metadata(game_version: str, loader_version: str, force_refresh: bool=False)` | `QuiltInstallMetadata` |
| `get_profile(game_version: str, loader_version: str, force_refresh: bool=False)` | `dict` |
| `clear_cached_install(game_version: str, loader_version: str)` | `None` |


### `mcw_core.api.modrinth.modrinth_client`

Search, metadata, installer và repair/update Modrinth.  
Implementation tương thích hiện tại: `src/core/modrinth/modrinth_client.py`

#### `ModrinthClient`

| Method | Return |
|---|---|
| `search_projects(project_type: str, query: str='', game_version: str='', loader: str='fabric', index: str='relevance', offset: int=0, limit: int=25, force_refresh: bool=False)` | `ModrinthSearchResult` |
| `get_project(project_id: str, force_refresh: bool=False)` | `ModrinthProject` |
| `list_project_versions(project_id: str, loader: str='fabric', game_version: str='', version_types: tuple[str, ...] \| list[str] \| set[str] \| None=None, force_refresh: bool=False)` | `list[ModrinthVersion]` |
| `get_version(version_id: str, force_refresh: bool=False)` | `ModrinthVersion` |
| `select_version(project_id: str, game_version: str, loader: str='fabric', version_types: tuple[str, ...] \| list[str] \| set[str] \| None=None)` | `ModrinthVersion` |
| `compatible_loaders(loader: str)` | `tuple[str, ...]` |
| `normalize_version_types(version_types: tuple[str, ...] \| list[str] \| set[str] \| None=None)` | `tuple[str, ...]` |


### `mcw_core.api.modrinth.modrinth_errors`

Search, metadata, installer và repair/update Modrinth.  
Implementation tương thích hiện tại: `src/core/modrinth/modrinth_errors.py`

#### `ModrinthManagedFilesRequired`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `ModrinthModpackManualDownloadRequired`
- Exception/data class; xem field trong source hoặc typed exception handler.


### `mcw_core.api.modrinth.modrinth_manual_installer`

Search, metadata, installer và repair/update Modrinth.  
Implementation tương thích hiện tại: `src/core/modrinth/modrinth_manual_installer.py`

#### `ModrinthManualInstaller`

| Method | Return |
|---|---|
| `install(instance: Instance, requirement: ModrinthManualDownload, source: Path)` | `str` |
| `install_many(instance: Instance, requirements: tuple[ModrinthManualDownload, ...] \| list[ModrinthManualDownload], sources: tuple[Path, ...] \| list[Path])` | `ModrinthManualImportResult` |


### `mcw_core.api.modrinth.modrinth_mod_installer`

Search, metadata, installer và repair/update Modrinth.  
Implementation tương thích hiện tại: `src/core/modrinth/modrinth_mod_installer.py`

#### `ModrinthModInstaller`

| Method | Return |
|---|---|
| `install(instance: Instance, version_id: str, install_dependencies: bool=True, allowed_version_types: tuple[str, ...] \| list[str] \| set[str] \| None=None, reporter: ProgressReporter \| None=None)` | `ModrinthModInstallResult` |


### `mcw_core.api.modrinth.modrinth_mod_update_manager`

Search, metadata, installer và repair/update Modrinth.  
Implementation tương thích hiện tại: `src/core/modrinth/modrinth_mod_update_manager.py`

#### `ModrinthModUpdateManager`

| Method | Return |
|---|---|
| `check(instance: Instance, allowed_version_types: tuple[str, ...] \| list[str] \| set[str] \| None=None, force_refresh: bool=False, reporter: ProgressReporter \| None=None)` | `ModrinthModUpdateReport` |
| `update(instance: Instance, project_ids: list[str] \| tuple[str, ...] \| set[str], allowed_version_types: tuple[str, ...] \| list[str] \| set[str] \| None=None, reporter: ProgressReporter \| None=None)` | `ModrinthModUpdateResult` |
| `update_all(instance: Instance, allowed_version_types: tuple[str, ...] \| list[str] \| set[str] \| None=None, reporter: ProgressReporter \| None=None)` | `ModrinthModUpdateResult` |
| `set_locked(instance: Instance, project_ids: list[str] \| tuple[str, ...] \| set[str], locked: bool)` | `tuple[str, ...]` |


### `mcw_core.api.modrinth.modrinth_pack_installer`

Search, metadata, installer và repair/update Modrinth.  
Implementation tương thích hiện tại: `src/core/modrinth/modrinth_pack_installer.py`

#### `ModrinthPackInstaller`

| Method | Return |
|---|---|
| `install(project_id: str, version_id: str, instance_name: str, install_optional_files: bool=True, allowed_version_types: tuple[str, ...] \| list[str] \| set[str] \| None=None, reporter: ProgressReporter \| None=None, expected_loader: str='', settings_override: dict \| None=None)` | `ModrinthModpackInstallResult` |
| `install_local_archive(pack_path: Path, instance_name: str='', install_optional_files: bool=True, reporter: ProgressReporter \| None=None, settings_override: dict \| None=None)` | `ModrinthModpackInstallResult` |
| `install_manual_archive(request: ModrinthModpackManualDownloadRequired, source: Path, reporter: ProgressReporter \| None=None)` | `ModrinthModpackInstallResult` |
| `inspect(pack_path: Path)` | `dict` |


### `mcw_core.api.modrinth.modrinth_pack_registry`

Search, metadata, installer và repair/update Modrinth.  
Implementation tương thích hiện tại: `src/core/modrinth/modrinth_pack_registry.py`

#### `ModrinthPackRegistry`

| Method | Return |
|---|---|
| `path(instance_dir: Path)` | `Path` |
| `load(instance: Instance)` | `dict` |
| `load_from_dir(instance_dir: Path)` | `dict` |
| `save(instance_dir: Path, data: dict)` | `None` |
| `scan(instance: Instance, reporter: ProgressReporter \| None=None, force_hash: bool=False)` | `ModrinthPackStateReport` |
| `verify_entry(instance_dir: Path, entry: dict, cache: dict \| None=None, force_hash: bool=False)` | `tuple[bool, bool, int]` |
| `build_verification_cache(instance_dir: Path, managed_files: list[dict])` | `dict` |


### `mcw_core.api.modrinth.modrinth_pack_repair_manager`

Search, metadata, installer và repair/update Modrinth.  
Implementation tương thích hiện tại: `src/core/modrinth/modrinth_pack_repair_manager.py`

#### `ModrinthPackRepairManager`

| Method | Return |
|---|---|
| `repair(instance: Instance, reporter: ProgressReporter \| None=None)` | `ModrinthPackRepairResult` |


### `mcw_core.api.modrinth.modrinth_pack_update_manager`

Search, metadata, installer và repair/update Modrinth.  
Implementation tương thích hiện tại: `src/core/modrinth/modrinth_pack_update_manager.py`

#### `ModrinthPackUpdateManager`

| Method | Return |
|---|---|
| `check(instance: Instance, allowed_version_types: tuple[str, ...] \| list[str] \| set[str] \| None=None, force_refresh: bool=False, reporter: ProgressReporter \| None=None)` | `ModrinthPackUpdateInfo \| None` |
| `preview(instance: Instance, target_version_id: str='', allowed_version_types: tuple[str, ...] \| list[str] \| set[str] \| None=None, reporter: ProgressReporter \| None=None)` | `ModrinthPackUpdatePlan` |
| `update(instance: Instance, target_version_id: str='', allowed_version_types: tuple[str, ...] \| list[str] \| set[str] \| None=None, reporter: ProgressReporter \| None=None)` | `ModrinthPackUpdateResult` |


### `mcw_core.api.modrinth.modrinth_registry`

Search, metadata, installer và repair/update Modrinth.  
Implementation tương thích hiện tại: `src/core/modrinth/modrinth_registry.py`

#### `ModrinthRegistry`

| Method | Return |
|---|---|
| `load(instance: Instance)` | `dict` |
| `empty()` | `dict` |
| `save(instance: Instance, data: dict)` | `None` |
| `set_locked(instance: Instance, project_ids: list[str] \| tuple[str, ...] \| set[str], locked: bool)` | `tuple[str, ...]` |
| `remove_by_filenames(instance: Instance, filenames: list[str] \| tuple[str, ...] \| set[str])` | `tuple[str, ...]` |
| `entries_by_file(instance: Instance)` | `dict[str, dict]` |
| `safe_tracked_path(instance: Instance, filename: str)` | `Path \| None` |


### `mcw_core.api.network.download_bandwidth_limiter`

Download, bandwidth, pause/cancel và sessions.  
Implementation tương thích hiện tại: `src/core/network/download_bandwidth_limiter.py`

#### `DownloadBandwidthLimiter`

| Method | Return |
|---|---|
| `limit_mbps(self)` | `float` |
| `is_enabled(self)` | `bool` |
| `configure_mbps(self, value: object)` | `float` |
| `throttle(self, byte_count: int)` | `None` |


### `mcw_core.api.network.download_manager`

Download, bandwidth, pause/cancel và sessions.  
Implementation tương thích hiện tại: `src/core/network/download_manager.py`

#### `DownloadManager`

| Method | Return |
|---|---|
| `max_concurrent_downloads(self)` | `int` |
| `per_host_limit(self)` | `int` |
| `configure(self, max_concurrent_downloads: object=DEFAULT_MAX_CONCURRENT_DOWNLOADS, per_host_limit: object \| None=None)` | `tuple[int, int]` |
| `get_path_lock(self, path: Path)` | `RLock` |
| `download(self, request: DownloadRequest, reporter: ProgressReporter \| None=None, progress_stage: ProgressStage \| None=None, progress_message: str \| None=None, client_provider=None)` | `DownloadResult` |
| `download_and_hash(self, url: str, path: Path, max_attempts: int=2, timeout: float=20.0, force: bool=False, reporter: ProgressReporter \| None=None, progress_stage: ProgressStage \| None=None, progress_message: str \| None=None, client_provider=None)` | `tuple[Path, str, int]` |
| `verify(self, path: Path, expected_size: int, hashes: dict \| object)` | `bool` |
| `calculate_hash(path: Path, algorithm: str)` | `str` |
| `calculate_hashes(self, path: Path, expected: dict \| object)` | `dict[str, str]` |
| `content_length(response: httpx.Response, fallback: int)` | `int` |
| `parse_content_range(response: httpx.Response)` | `tuple[int, int, int \| None] \| None` |
| `valid_content_range(cls, response: httpx.Response, expected_start: int, expected_size: int)` | `bool` |
| `content_range_total(cls, response: httpx.Response)` | `int` |
| `partial_size(cls, path: Path, expected_size: int)` | `int` |
| `delete_file(path: Path)` | `None` |
| `describe_error(error: Exception \| None)` | `str` |


### `mcw_core.api.network.download_pause`

Download, bandwidth, pause/cancel và sessions.  
Implementation tương thích hiện tại: `src/core/network/download_pause.py`

#### `DownloadInterruptedError`
Base class for cooperative download interruption requests.
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `DownloadPausedError`
Legacy terminal pause error kept for compatibility with older callers.
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `DownloadCancelledError`
Raised when the user cancels the active launcher download session.
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `DownloadPauseController`

| Method | Return |
|---|---|
| `is_active(self)` | `bool` |
| `is_pause_requested(self)` | `bool` |
| `is_paused(self)` | `bool` |
| `is_cancel_requested(self)` | `bool` |
| `begin(self)` | `None` |
| `finish(self)` | `None` |
| `request_pause(self)` | `bool` |
| `request_resume(self)` | `bool` |
| `request_cancel(self)` | `bool` |
| `raise_if_requested(self)` | `None` |
| `wait(self, seconds: float)` | `None` |

- `is_download_paused(error: BaseException | None) -> bool` — Compatibility helper; cancellation is also an interrupted download.
- `is_download_cancelled(error: BaseException | None) -> bool`

### `mcw_core.api.network.network_session`

Download, bandwidth, pause/cancel và sessions.  
Implementation tương thích hiện tại: `src/core/network/network_session.py`

#### `NetworkSession`

| Method | Return |
|---|---|
| `max_concurrent_downloads(self)` | `int` |
| `configure(self, max_concurrent_downloads: object=DEFAULT_MAX_CONCURRENT_DOWNLOADS)` | `int` |
| `get_client(self)` | `httpx.Client` |
| `close(self)` | `None` |


### `mcw_core.api.package.portable_content_manager`

Portable content/manual files.  
Implementation tương thích hiện tại: `src/core/package/portable_content_manager.py`

#### `PortableManualDownloadRequired`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `PortableContentManager`

| Method | Return |
|---|---|
| `ensure(instance: Instance)` | `None` |
| `prefetch_referenced(instance: Instance, reporter: ProgressReporter \| None=None)` | `None` |
| `finalize_disabled(instance: Instance)` | `None` |
| `install_many(instance: Instance, requirements: tuple[PortableManualDownload, ...] \| list[PortableManualDownload], sources: tuple[Path, ...] \| list[Path])` | `tuple[str, ...]` |


### `mcw_core.api.progress.progress_reporter`

ProgressReporter.  
Implementation tương thích hiện tại: `src/core/progress/progress_reporter.py`

#### `ProgressReporter`

| Method | Return |
|---|---|
| `report(self, stage: ProgressStage, message: str, current: int \| None=None, total: int \| None=None, unit: ProgressUnit=ProgressUnit.NONE, bytes_per_second: float \| None=None, state: ProgressState=ProgressState.RUNNING, detail: str='')` | `None` |
| `status(self, stage: ProgressStage, message: str)` | `None` |
| `bytes(self, stage: ProgressStage, message: str, current: int, total: int, bytes_per_second: float \| None=None)` | `None` |
| `files(self, stage: ProgressStage, message: str, current: int, total: int, bytes_per_second: float \| None=None)` | `None` |
| `steps(self, stage: ProgressStage, message: str, current: int, total: int)` | `None` |
| `succeeded(self, stage: ProgressStage, message: str, detail: str='')` | `None` |
| `failed(self, stage: ProgressStage, message: str, detail: str='')` | `None` |
| `cancelled(self, stage: ProgressStage, message: str, detail: str='')` | `None` |
| `task(self, stage: ProgressStage, start_message: str, success_message: str, failure_message: str)` | `Iterator[None]` |


### `mcw_core.api.repair.repair_service`

Repair scan/plan/execute.  
Implementation tương thích hiện tại: `src/core/repair/repair_service.py`

#### `RepairService`

| Method | Return |
|---|---|
| `scan(cls, instance: Instance, mode: RepairMode \| str=RepairMode.QUICK, components: Iterable[RepairComponent \| str] \| None=None, on_progress: ProgressCallback \| None=None)` | `RepairReport` |
| `build_plan(cls, report: RepairReport, components: Iterable[RepairComponent \| str] \| None=None)` | `RepairPlan` |
| `repair(cls, instance: Instance, plan: RepairPlan, on_progress: ProgressCallback \| None=None)` | `RepairExecutionResult` |


### `mcw_core.api.runtime.game_runtime_manager`

Process supervisor và recovery.  
Implementation tương thích hiện tại: `src/core/runtime/game_runtime_manager.py`

#### `GameRuntimeManager`

| Method | Return |
|---|---|
| `watch(cls, process: object, instance: Instance, minecraft_version: str, started_at: datetime, on_exit: GameExitCallback \| None=None, session_id: str \| None=None, crash_report_snapshot: Mapping[str, tuple[int, int]] \| None=None)` | `bool` |
| `stop(cls, instance: Instance, graceful_timeout: float=2.5)` | `bool` |
| `latest_game_log(instance: Instance)` | `Path \| None` |
| `crash_report_snapshot(instance: Instance)` | `dict[str, tuple[int, int]]` |
| `latest_crash_report(instance: Instance, since: datetime \| None=None, previous: Mapping[str, tuple[int, int]] \| None=None)` | `Path \| None` |
| `record_start(cls, instance: Instance, started_at: datetime, session_id: str \| None)` | `None` |


### `mcw_core.api.runtime.process_supervisor`

Process supervisor và recovery.  
Implementation tương thích hiện tại: `src/core/runtime/process_supervisor.py`

#### `ProcessSupervisor`
Persist and supervise Minecraft process sessions without touching unrelated Java processes.

| Method | Return |
|---|---|
| `begin(cls, instance: Instance)` | `ProcessSession` |
| `attach(cls, session_id: str, process: object)` | `ProcessSession` |
| `register_child(cls, session_id: str, pid: int)` | `ProcessSession` |
| `finish(cls, session_id: str, exit_code: int, crashed: bool, detail: str='')` | `ProcessSession \| None` |
| `abort(cls, session_id: str, detail: str='')` | `ProcessSession \| None` |
| `stop_requested(cls, session_id: str \| None)` | `bool` |
| `active_for(cls, instance: Instance)` | `ProcessSession \| None` |
| `list_active(cls)` | `tuple[ProcessSession, ...]` |
| `stop_process(cls, process: object, graceful_timeout: float=2.5)` | `bool` |
| `stop_instance(cls, instance: Instance, graceful_timeout: float=2.5)` | `bool` |
| `reconcile(cls)` | `tuple[str, ...]` |
| `load(cls, session_id: str)` | `ProcessSession` |


### `mcw_core.api.runtime.startup_recovery_manager`

Process supervisor và recovery.  
Implementation tương thích hiện tại: `src/core/runtime/startup_recovery_manager.py`

#### `StartupRecoveryReport`

| Method | Return |
|---|---|
| `recovered_item_count(self)` | `int` |

#### `StartupRecoveryManager`

| Method | Return |
|---|---|
| `reconcile()` | `StartupRecoveryReport` |


### `mcw_core.api.security.account_security_manager`

Account security và redaction.  
Implementation tương thích hiện tại: `src/core/security/account_security_manager.py`

#### `AccountSecurityManager`

| Method | Return |
|---|---|
| `audit(cls)` | `AccountSecurityReport` |
| `migrate_if_needed(cls)` | `AccountSecurityReport` |
| `migrate_and_reprotect(cls)` | `AccountSecurityReport` |


### `mcw_core.api.security.sensitive_data_redactor`

Account security và redaction.  
Implementation tương thích hiện tại: `src/core/security/sensitive_data_redactor.py`

#### `SensitiveDataRedactor`

| Method | Return |
|---|---|
| `redact_text(cls, value: object)` | `str` |
| `redact_value(cls, value: Any, key: str='')` | `Any` |
| `redact_json(cls, value: Any)` | `str` |


### `mcw_core.api.startup_runner`

Implementation tương thích hiện tại: `src/core/startup_runner.py`

#### `StartupTimeoutError`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `StartupWorkerError`
- Exception/data class; xem field trong source hoặc typed exception handler.

- `run_startup_task(task: StartupTask, on_progress: StartupProgressHandler, pump_events: EventPump, timeout_seconds: float=45.0) -> Any` — Run blocking startup I/O away from the Qt thread while keeping the splash responsive.

### `mcw_core.api.system.memory`

System memory.  
Implementation tương thích hiện tại: `src/core/system/memory.py`

#### `SystemMemory`

| Method | Return |
|---|---|
| `total_physical_memory_mb(cls)` | `int` |

#### `MemoryAllocationPolicy`

| Method | Return |
|---|---|
| `physical_limit_mb(cls, total_memory_mb: int \| None=None)` | `int` |
| `normalize(cls, min_memory_mb: object, max_memory_mb: object, total_memory_mb: int \| None=None)` | `tuple[int, int]` |
| `is_valid(cls, min_memory_mb: object, max_memory_mb: object, total_memory_mb: int \| None=None)` | `bool` |
| `snap_mb(cls, memory_mb: object, upper_bound_mb: int)` | `int` |
| `format_mb(memory_mb: int)` | `str` |


### `mcw_core.api.theme.theme_animation`

Theme definition/palette/authoring.  
Implementation tương thích hiện tại: `src/core/theme/theme_animation.py`

#### `ThemeAnimationDefinition`

| Method | Return |
|---|---|
| `rows(self)` | `int` |

#### `ResolvedThemeAnimation`

| Method | Return |
|---|---|
| `key(self)` | `str` |


### `mcw_core.api.theme.theme_authoring`

Theme definition/palette/authoring.  
Implementation tương thích hiện tại: `src/core/theme/theme_authoring.py`

#### `ThemeAuthoringError`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `ThemeAuthoringService`

| Method | Return |
|---|---|
| `validate(self, theme_id: str)` | `ThemeValidationReport` |
| `validate_directory(self, root: Path)` | `ThemeValidationReport` |
| `duplicate(self, theme_id: str, new_id: str, new_name: str \| None=None)` | `ThemeDefinition` |
| `export(self, theme_id: str, destination: Path)` | `Path` |
| `import_archive(self, archive_path: Path, overwrite: bool=False)` | `ThemeDefinition` |


### `mcw_core.api.theme.theme_font`

Theme definition/palette/authoring.  
Implementation tương thích hiện tại: `src/core/theme/theme_font.py`

#### `ThemeFontDefinition`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `ResolvedThemeFont`
- Exception/data class; xem field trong source hoặc typed exception handler.


### `mcw_core.api.theme.theme_manager`

Theme definition/palette/authoring.  
Implementation tương thích hiện tại: `src/core/theme/theme_manager.py`

#### `ThemeError`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `ThemeManifestError`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `ThemeAssetError`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `ThemeDefinition`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `ThemeManager`

| Method | Return |
|---|---|
| `current(self)` | `ThemeDefinition` |
| `reload(self)` | `tuple[ThemeDefinition, ...]` |
| `available_themes(self)` | `tuple[ThemeDefinition, ...]` |
| `select(self, theme_id: str)` | `ThemeDefinition` |
| `resolve_asset(self, key: str, theme: ThemeDefinition \| None=None, fallback_to_default: bool=False)` | `Path \| None` |
| `resolve_text_asset(self, role: str, theme: ThemeDefinition \| None=None, fallback_to_default: bool=False)` | `Path \| None` |
| `resolve_animation(self, key: str, theme: ThemeDefinition \| None=None, fallback_to_default: bool=True)` | `ResolvedThemeAnimation \| None` |
| `resolve_animation_fallback(self, key: str, theme: ThemeDefinition \| None=None, fallback_to_default: bool=True)` | `Path \| None` |
| `resolve_font(self, theme: ThemeDefinition \| None=None, fallback_to_default: bool=True)` | `ResolvedThemeFont \| None` |
| `resolve_palette(self, theme: ThemeDefinition \| None=None)` | `ThemePaletteDefinition` |
| `is_accent_asset(self, key: str, theme: ThemeDefinition \| None=None)` | `bool` |
| `resolve_stylesheet(self, theme: ThemeDefinition \| None=None)` | `str` |
| `asset_status(self, theme: ThemeDefinition \| None=None)` | `dict[str, bool]` |
| `animation_status(self, theme: ThemeDefinition \| None=None)` | `dict[str, bool]` |
| `font_status(self, theme: ThemeDefinition \| None=None)` | `bool` |


### `mcw_core.api.theme.theme_motion`

Theme definition/palette/authoring.  
Implementation tương thích hiện tại: `src/core/theme/theme_motion.py`

#### `MotionTransitionDefinition`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `ButtonMotionDefinition`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `SidebarMotionDefinition`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `ToastMotionDefinition`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `MotionPerformanceDefinition`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `ThemeMotionDefinition`
- Exception/data class; xem field trong source hoặc typed exception handler.


### `mcw_core.api.theme.theme_palette`

Theme definition/palette/authoring.  
Implementation tương thích hiện tại: `src/core/theme/theme_palette.py`

#### `ThemePaletteDefinition`

| Method | Return |
|---|---|
| `to_dict(self)` | `dict[str, str]` |

- `normalize_hex_color(value: object, label: str='color') -> str`
- `derive_custom_accent(theme_palette: ThemePaletteDefinition, accent: str) -> ThemePaletteDefinition`

### `mcw_core.api.update.update_applier`

Update discovery/download/apply.  
Implementation tương thích hiện tại: `src/core/update/update_applier.py`

#### `UpdateApplyRequest`

| Method | Return |
|---|---|
| `load(cls, path: Path)` | `'UpdateApplyRequest'` |
| `validate(self)` | `None` |

#### `UpdateApplier`

| Method | Return |
|---|---|
| `run(self)` | `int` |

- `run_update_applier(request_path: Path) -> int`

### `mcw_core.api.update.update_cleanup`

Update discovery/download/apply.  
Implementation tương thích hiện tại: `src/core/update/update_cleanup.py`

#### `UpdateCleanupRequest`

| Method | Return |
|---|---|
| `validate(self)` | `None` |

#### `UpdateCleanupWorker`

| Method | Return |
|---|---|
| `start(self)` | `threading.Thread` |
| `run(self)` | `None` |

- `consume_update_cleanup_arguments(arguments: list[str]) -> tuple[list[str], UpdateCleanupRequest | None]`

### `mcw_core.api.update.update_manager`

Update discovery/download/apply.  
Implementation tương thích hiện tại: `src/core/update/update_manager.py`

#### `UpdateManager`

| Method | Return |
|---|---|
| `check_for_update(self, force_refresh: bool=False)` | `UpdateInfo \| None` |
| `prepare_update(self, info: UpdateInfo, reporter: ProgressReporter \| None=None)` | `PreparedUpdate` |


### `mcw_core.api.update.windows_update_installer`

Update discovery/download/apply.  
Implementation tương thích hiện tại: `src/core/update/windows_update_installer.py`

#### `AutomaticUpdateUnsupportedError`
- Exception/data class; xem field trong source hoặc typed exception handler.

#### `WindowsUpdateInstaller`

| Method | Return |
|---|---|
| `is_supported()` | `bool` |
| `launch(cls, prepared: PreparedUpdate, install_directory: Path \| None=None, executable_path: Path \| None=None, parent_pid: int \| None=None, persistent_log_path: Path \| None=None)` | `Path` |


## Tóm tắt model trả về

| Model | Main fields |
|---|---|
| `LaunchResult` | java_path, minecraft_java_major_version, minecraft_version, warnings |
| `ProgressEvent` | stage, message, current, total, unit, bytes_per_second, state, detail |
| `Instance` | instance_id, name, version_id, instance_dir, mod_loader, icon, launch history |
| `JavaDiagnostic` | major_version, version_string, vendor, architecture, java_home, executable, source, valid |
| `ModInfo` | file metadata, loader, dependencies, licenses, provider provenance |
| `ProviderModpackPreview` | provider, package_format, name, Minecraft/loader, settings, native member |
| `ModpackExportResult` | output_path, mode, referenced_files, embedded_files, manual_files, native_package_included |
| `RepairReport / RepairPlan / RepairExecutionResult` | scan results, chosen plan, execution/rollback result |
| `GameExitResult` | exit_code, duration, crashed, log/crash report paths |
