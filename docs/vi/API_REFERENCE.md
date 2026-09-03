# MCW Core v1.5.0 API Reference

Tài liệu này được sinh trực tiếp từ source public của MCW Core v1.5.0. Public boundary được hỗ trợ là `mcw_core` và `mcw_core.api.*`.

> Không import `src.core.*` hoặc `src.models.*` từ application bên ngoài.

## Stable facade and models

### `mcw_core/facade.py`

#### `MCWCore`

Public, GUI-independent facade for MCW Launcher core operations.

Methods:

```python
create_default(root: Path | str | None = None) -> 'MCWCore'
``` *(classmethod)*

```python
launch(request: LaunchRequest) -> LaunchResult
```

#### `get_default_core`

```python
get_default_core() -> MCWCore
```

#### `configure_default_core`

```python
configure_default_core(paths: CorePaths | Path | str) -> MCWCore
```

### `mcw_core/models.py`

#### `LaunchRequest`

Headless launch request accepted by the public MCW Core API.

Fields / public attributes:

- `instance: Instance | str`
- `account: Account | None = None`
- `authentication: Authentication | None = None`
- `offline_username: str = ''`
- `debug_mode: bool = False`
- `on_progress: ProgressCallback | None = None`
- `on_exit: Callable[[GameExitResult], None] | None = None`
- `on_manual_content_required: Callable[[Exception], None] | None = None`
- `on_compatibility_confirmation: Callable[[Exception], bool] | None = None`
- `allow_compatibility_issues_once: bool = False`

#### `LaunchResult`

Bases: `Mapping[str, Any]`

Fields / public attributes:

- `java_path: Path`
- `minecraft_java_major_version: int`
- `minecraft_version: str`
- `warnings: tuple[str, ...] = field(default_factory=tuple)`

Methods:

```python
as_dict() -> dict[str, Any]
```

```python
from_legacy(result: Mapping[str, Any]) -> 'LaunchResult'
``` *(classmethod)*

#### `InstanceRuntimeProfile`

Fields / public attributes:

- `instance_name: str`
- `minecraft_version: str`
- `loader_name: str`
- `loader_version: str`
- `required_java_major: int`
- `managed_java_major: int`
- `java_automatic: bool`
- `configured_java_path: str = ''`

#### `InstanceCreateRequest`

Fields / public attributes:

- `name: str`
- `version_id: str`
- `loader_name: str = 'vanilla'`
- `loader_version: str = 'auto'`
- `on_progress: ProgressCallback | None = None`

### `mcw_core/operations.py`

#### `OperationState`

Fields / public attributes:

- `active: bool`
- `paused: bool`
- `cancel_requested: bool`

#### `OperationHandle`

GUI-independent cooperative pause, resume and cancel controls.

Methods:

```python
state() -> OperationState
``` *(property)*

```python
begin() -> None
```

```python
finish() -> None
```

```python
pause() -> bool
```

```python
resume() -> bool
```

```python
cancel() -> bool
```

```python
checkpoint() -> None
```

### `mcw_core/paths.py`

#### `CorePaths`

Filesystem roots used by MCW Core.

Fields / public attributes:

- `root: Path`
- `cache: Path | None = None`
- `instances: Path | None = None`
- `accounts: Path | None = None`
- `config: Path | None = None`
- `logs: Path | None = None`
- `backups: Path | None = None`
- `themes: Path | None = None`
- `runtimes: Path | None = None`

Methods:

```python
from_root(root: Path | str) -> 'CorePaths'
``` *(classmethod)*

```python
current() -> 'CorePaths'
``` *(classmethod)*

```python
apply(initialize: bool = True) -> dict[str, Path]
```

### `mcw_core/services.py`

#### `LoaderService`

Public constants:

- `VANILLA = ModLoaderManager.VANILLA`
- `FABRIC = ModLoaderManager.FABRIC`
- `FORGE = ModLoaderManager.FORGE`
- `NEOFORGE = ModLoaderManager.NEOFORGE`
- `QUILT = ModLoaderManager.QUILT`
- `AUTO = ModLoaderManager.AUTO`
- `MODDED_LOADERS = ModLoaderManager.MODDED_LOADERS`
- `FORGE_FAMILY = ModLoaderManager.FORGE_FAMILY`

Methods:

```python
normalize(loader: object) -> tuple[str, str]
``` *(staticmethod)*

```python
resolve(game_version: str, loader_name: str, loader_version: str = AUTO) -> tuple[str, str]
``` *(staticmethod)*

```python
prepare(game_version: str, loader_name: str, loader_version: str = AUTO, on_progress: ProgressCallback | None = None)
``` *(staticmethod)*

#### `InstanceService`

Methods:

```python
list() -> list[Instance]
``` *(staticmethod)*

```python
load(name: str) -> Instance
``` *(staticmethod)*

```python
list_running() -> list[object]
``` *(staticmethod)*

```python
is_running(instance: Instance) -> bool
``` *(staticmethod)*

```python
kill(name: str) -> bool
``` *(staticmethod)*

```python
status(instance: Instance | str) -> InstanceStatus
``` *(staticmethod)*

```python
list_statuses() -> list[InstanceStatus]
``` *(staticmethod)*

```python
health(instance: Instance | str) -> InstanceHealthReport
``` *(staticmethod)*

```python
list_health() -> list[InstanceHealthReport]
``` *(staticmethod)*

```python
set_icon(name: str, source_path: Path) -> Instance
``` *(staticmethod)*

```python
reset_icon(name: str) -> Instance
``` *(staticmethod)*

```python
set_library_metadata(name: str, *, favorite: bool | None = None, group: str | None = None, tags: object | None = None) -> Instance
``` *(staticmethod)*

```python
runtime_profile(name: str) -> InstanceRuntimeProfile
``` *(staticmethod)*

```python
set_java_runtime(name: str, java_path: str | Path | None) -> InstanceRuntimeProfile
``` *(staticmethod)*

```python
create(request: InstanceCreateRequest) -> Instance
```

```python
create_with_optifine(request: InstanceCreateRequest, source_path: Path, mode: str | OptiFineInstallMode = OptiFineInstallMode.AUTO, on_optifine_progress: ProgressCallback | None = None) -> Instance
```

```python
change_loader(name: str, loader_name: str, loader_version: str, on_progress: ProgressCallback | None = None) -> Instance
```

```python
repair_loader(name: str, on_progress: ProgressCallback | None = None) -> Instance
```

```python
restore_previous_loader(name: str, on_progress: ProgressCallback | None = None) -> Instance
```

```python
export_loader_diagnostics(name: str, output_path: Path) -> Path
```

```python
repair(name: str, on_progress: ProgressCallback | None = None)
``` *(staticmethod)*

```python
scan_repair(name: str, mode: str, on_progress: ProgressCallback | None = None)
``` *(staticmethod)*

```python
execute_repair(name: str, plan: object, on_progress: ProgressCallback | None = None)
``` *(staticmethod)*

```python
rename(source_name: str, target_name: str) -> Path
``` *(staticmethod)*

```python
clone(source_name: str, target_name: str, include_saves: bool = False) -> Instance
``` *(staticmethod)*

```python
delete(name: str) -> bool
``` *(staticmethod)*

```python
inspect_package(package_path: Path)
``` *(staticmethod)*

```python
import_package(package_path: Path, on_progress: ProgressCallback | None = None, settings_override: dict | None = None) -> Instance
``` *(staticmethod)*

```python
export_package(name: str, output_path: Path, include_saves: bool = False, on_progress: ProgressCallback | None = None) -> Path
``` *(staticmethod)*

```python
inspect_modpack_package(package_path: Path)
``` *(staticmethod)*

```python
import_modpack_package(package_path: Path, on_progress: ProgressCallback | None = None, settings_override: dict | None = None, install_optional_files: bool = True, instance_name: str = '') -> Instance
``` *(staticmethod)*

```python
export_modpack(name: str, output_path: Path, mode: str, portable_mode: str = 'smart', include_saves: bool = False, on_progress: ProgressCallback | None = None)
``` *(staticmethod)*

```python
install_portable_manual_files(name: str, requirements: object, sources: object) -> dict[str, object]
``` *(staticmethod)*

#### `OptiFineService`

Public constants:

- `OFFICIAL_DOWNLOADS_URL = 'https://optifine.net/downloads'`

Methods:

```python
inspect_file(source_path: Path) -> OptiFineVersion
``` *(staticmethod)*

```python
state(instance: Instance | str) -> OptiFineState
``` *(staticmethod)*

```python
compatibility(instance: Instance | str, version: OptiFineVersion, mode: str | OptiFineInstallMode = OptiFineInstallMode.AUTO) -> OptiFineCompatibilityResult
``` *(staticmethod)*

```python
install(instance: Instance | str, source_path: Path, mode: str | OptiFineInstallMode = OptiFineInstallMode.AUTO, on_progress: ProgressCallback | None = None) -> OptiFineInstallResult
``` *(staticmethod)*

```python
repair(instance: Instance | str, on_progress: ProgressCallback | None = None) -> OptiFineInstallResult
``` *(staticmethod)*

```python
uninstall(instance: Instance | str) -> bool
``` *(staticmethod)*

#### `JavaService`

Methods:

```python
scan(on_progress: ProgressCallback | None = None) -> list[object]
``` *(staticmethod)*

```python
latest_feature_release() -> int
``` *(staticmethod)*

```python
normalize_feature_major(major: int | str | None) -> int
``` *(staticmethod)*

```python
install(major: int, on_progress: ProgressCallback | None = None, force: bool = True) -> Path
``` *(staticmethod)*

## Granular `mcw_core.api.*` modules

### `mcw_core.api.account.account_manager`

Source re-export: `src.core.account.account_manager`

#### `AccountManager`

Methods:

```python
create_offline_account(username: str) -> Account
``` *(staticmethod)*

```python
create_microsoft_account(cancel_event: Event | None = None) -> Account
``` *(staticmethod)*

```python
list_accounts() -> list[Account]
``` *(staticmethod)*

```python
get_account(account_id: str) -> Account | None
``` *(staticmethod)*

```python
get_selected_account() -> Account | None
``` *(staticmethod)*

```python
set_selected_account(account_id: str) -> bool
``` *(staticmethod)*

```python
synchronize_microsoft_profile(account_id: str) -> Account
``` *(staticmethod)*

```python
remove_account(account_id: str) -> bool
``` *(staticmethod)*

```python
is_account_exist(username: str) -> bool
``` *(staticmethod)*

### `mcw_core.api.account.account_skin_manager`

Source re-export: `src.core.account.account_skin_manager`

#### `AccountSkinManager`

Cache Minecraft skin textures without making the GUI depend on network APIs.

Public constants:

- `MAX_TEXTURE_BYTES = 4 * 1024 * 1024`
- `REQUEST_TIMEOUT_SECONDS = 20.0`
- `PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'`

Methods:

```python
cache_profile(profile: MinecraftProfile) -> Path | None
``` *(classmethod)*

```python
cache_account(account: Account) -> Path | None
``` *(classmethod)*

```python
cache_texture(profile_uuid: str, skin_url: str) -> Path
``` *(classmethod)*

```python
cached_texture(account_or_uuid: Account | str) -> Path | None
``` *(classmethod)*

```python
remove_cached_texture(account_or_uuid: Account | str) -> None
``` *(classmethod)*

```python
texture_path(profile_uuid: str) -> Path
``` *(staticmethod)*

### `mcw_core.api.atlauncher.atlauncher_client`

Source re-export: `src.core.atlauncher.atlauncher_client`

#### `ATLauncherClient`

ATLauncher metadata adapter with public V2, V1, and CDN fallbacks.

Public constants:

- `GRAPHQL_URL = 'https://api.atlauncher.com/v2/graphql'`
- `V1_BASE_URL = 'https://api.atlauncher.com/v1/'`
- `CDN_BASE_URL = 'https://download.nodecdn.net/containers/atl/'`
- `WEBSITE_BASE_URL = 'https://atlauncher.com/pack/'`
- `SEARCH_TTL_SECONDS = 5 * 60`
- `PROJECT_TTL_SECONDS = 15 * 60`
- `VERSION_TTL_SECONDS = 30 * 60`
- `REQUEST_TIMEOUT_SECONDS = 25.0`
- `MAX_PAGE_SIZE = 50`
- `MAX_SEARCH_WINDOW = 250`

Methods:

```python
api_cache_status() -> ATLauncherCacheInfo
``` *(staticmethod)*

```python
clear_api_cache() -> None
``` *(staticmethod)*

```python
cache_status() -> ATLauncherCacheInfo
``` *(staticmethod)*

```python
clear_cache() -> None
``` *(staticmethod)*

```python
search_projects(query: str = '', index: int = 0, page_size: int = 25, sort: str = 'popularity', force_refresh: bool = False) -> ATLauncherSearchResult
``` *(staticmethod)*

```python
get_project(safe_name: str, force_refresh: bool = False) -> ATLauncherPack
``` *(staticmethod)*

```python
get_project_details(safe_name: str, force_refresh: bool = False) -> ATLauncherPack
``` *(staticmethod)*

```python
list_versions(safe_name: str, release_types: Iterable[str] | None = None, force_refresh: bool = False) -> tuple[ATLauncherVersionSummary, ...]
``` *(staticmethod)*

```python
get_version(safe_name: str, version: str, force_refresh: bool = False) -> ATLauncherVersion
``` *(staticmethod)*

```python
normalize_loader(value: object) -> str
``` *(staticmethod)*

### `mcw_core.api.atlauncher.atlauncher_content_manager`

Source re-export: `src.core.atlauncher.atlauncher_content_manager`

#### `ATLauncherContentManager`

Materialize deferred ATLauncher pack files before the first launch.

Public constants:

- `PROGRESS_EMIT_INTERVAL_SECONDS = 0.08`
- `MAX_CONFIG_ENTRIES = 100000`
- `MAX_CONFIG_BYTES = 10 * 1024 * 1024 * 1024`

Methods:

```python
ensure(instance: Instance, reporter: ProgressReporter | None = None, launch_lock_token: str | None = None) -> tuple[str, ...]
``` *(staticmethod)*

### `mcw_core.api.atlauncher.atlauncher_pack_installer`

Source re-export: `src.core.atlauncher.atlauncher_pack_installer`

#### `ATLauncherPackInstaller`

Public constants:

- `MAX_FILES = 20000`
- `MAX_TOTAL_BYTES = 50 * 1024 * 1024 * 1024`
- `MAX_PATH_LENGTH = 240`
- `RESERVED_ROOT_NAMES = {'instance.json', 'settings.json', '.mcw'}`
- `INSTANCE_NAME_PATTERN = re.compile('^[^<>:"/\\\\|?*\\x00-\\x1F]{1,80}$')`
- `SUPPORTED_LOADERS = frozenset({ModLoaderManager.VANILLA, *ModLoaderManager.MODDED_LOADERS})`

Methods:

```python
install(safe_name: str, version_name: str, instance_name: str, install_optional_files: bool = True, allowed_release_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None, settings_override: dict | None = None) -> ATLauncherModpackInstallResult
``` *(staticmethod)*

### `mcw_core.api.atlauncher.atlauncher_pack_registry`

Source re-export: `src.core.atlauncher.atlauncher_pack_registry`

#### `ATLauncherPackRegistry`

Public constants:

- `SCHEMA_VERSION = 1`

Methods:

```python
load(instance: Instance | Path) -> dict
``` *(staticmethod)*

```python
save(instance: Instance | Path, data: dict) -> None
``` *(staticmethod)*

```python
is_managed(instance: Instance | Path) -> bool
``` *(staticmethod)*

### `mcw_core.api.auth.microsoft.microsoft_auth_gate`

Source re-export: `src.core.auth.microsoft.microsoft_auth_gate`

#### `MicrosoftAuthenticationLockedError`

Bases: `RuntimeError`

#### `MicrosoftAuthenticationAvailability`

Fields / public attributes:

- `enabled: bool`
- `status: str`
- `message: str`

#### `MicrosoftAuthenticationGate`

Methods:

```python
availability() -> MicrosoftAuthenticationAvailability
``` *(staticmethod)*

```python
require_enabled() -> None
``` *(staticmethod)*

### `mcw_core.api.auth.microsoft.oauth_callback_server`

Source re-export: `src.core.auth.microsoft.oauth_callback_server`

#### `MicrosoftAuthorizationCancelledError`

Bases: `RuntimeError`

#### `OAuthCallbackHandler`

Bases: `BaseHTTPRequestHandler`

Fields / public attributes:

- `authorization_code: str | None = None`
- `returned_state: str | None = None`
- `error: str | None = None`
- `error_description: str | None = None`

Methods:

```python
do_GET() -> None
```

```python
log_message(format: str, *args) -> None
```

#### `ReusableOAuthHTTPServer`

Bases: `HTTPServer`

#### `OAuthCallbackServer`

Public constants:

- `HOST = '127.0.0.1'`
- `PORT = 8400`
- `POLL_INTERVAL_SECONDS = 0.25`

Methods:

```python
wait_for_callback(timeout: float = 180.0, cancel_event: Event | None = None) -> tuple[str, str]
``` *(staticmethod)*

### `mcw_core.api.backup.instance_backup_manager`

Source re-export: `src.core.backup.instance_backup_manager`

#### `InstanceBackupManager`

Public constants:

- `MANIFEST_NAME = 'mcw-backup.json'`
- `FORMAT_VERSION = 1`
- `EXTENSION = '.mcwbackup'`
- `SCOPE_FULL = 'full'`
- `SCOPE_WORLDS = 'worlds'`
- `VALID_SCOPES = {SCOPE_FULL, SCOPE_WORLDS}`
- `MAX_FILES = 200000`
- `MAX_EXTRACT_BYTES = 200 * 1024 * 1024 * 1024`
- `PROTECTED_ROOTS = {'instance.json', '.mcw', 'logs', 'crash-reports'}`

Methods:

```python
create(instance: Instance, scope: str = SCOPE_FULL, reason: str = 'manual', destination: Path | None = None) -> InstanceBackupResult
``` *(staticmethod)*

```python
inspect(path: Path) -> InstanceBackupInfo
``` *(staticmethod)*

```python
list_backups(instance: Instance) -> list[InstanceBackupInfo]
``` *(staticmethod)*

```python
restore(instance: Instance, backup_path: Path, create_safety_backup: bool = True) -> InstanceRestoreResult
``` *(staticmethod)*

### `mcw_core.api.bootstrap`

Source re-export: `src.core.bootstrap`

#### `initialize_application`

```python
initialize_application(progress_callback: BootstrapProgressCallback | None = None) -> dict[str, Any]
```

### `mcw_core.api.config.curseforge_config_manager`

Source re-export: `src.core.config.curseforge_config_manager`

#### `CurseForgeConfigManager`

Loads CurseForge gateway endpoints with safe local overrides.

Public constants:

- `SCHEMA_VERSION = 3`
- `MAX_GATEWAYS = 5`
- `PURPOSE_PREFIX = 'curseforge:gateway'`
- `TOKEN_PURPOSE = 'curseforge:client-token'`
- `ENV_GATEWAY_URL = 'MCW_CURSEFORGE_GATEWAY_URL'`
- `ENV_GATEWAY_URL_PREFIX = 'MCW_CURSEFORGE_GATEWAY_URL_'`
- `ENV_CLIENT_TOKEN = 'MCW_CURSEFORGE_CLIENT_TOKEN'`
- `DEFAULT_GATEWAY_URLS = (CURSEFORGE_DEFAULT_GATEWAY_URL,)`

Methods:

```python
path() -> Path
``` *(staticmethod)*

```python
legacy_path() -> Path
``` *(staticmethod)*

```python
gateway_urls() -> tuple[str, ...]
``` *(classmethod)*

```python
gateway_url() -> str
``` *(classmethod)*

```python
client_token() -> str
``` *(classmethod)*

```python
is_configured() -> bool
``` *(classmethod)*

```python
save_local(gateway_urls: Iterable[str] | str, client_token: str | None = None) -> Path
``` *(classmethod)*

### `mcw_core.api.config.launcher_settings_manager`

Source re-export: `src.core.config.launcher_settings_manager`

#### `LauncherSettingsManager`

Public constants:

- `SCHEMA_VERSION = 19`
- `UPDATE_CHANNEL_POLICY_VERSION = 2`
- `DEFAULT_SETTINGS = {'schema_version': SCHEMA_VERSION, 'gui': {'start_page': 'instances', 'show_snapshots': False, 'remember_window_size': True, 'language': 'en-US', 'show_content_descriptions': False}, 'launch': {'debug_mode': False, 'prefer_dedicated_gpu': False}, 'onboarding': {'completed': False, 'version': 1}, 'window': {'geometry': None}, 'appearance': {'theme': 'mcw-default', 'show_static_text': False, 'motion_mode': 'full', 'live_theme_reload': False, 'accent_mode': 'theme', 'accent_color': '#8ed35b', 'text_color_mode': 'theme', 'text_color': '#f4f4f4'}, 'modrinth': {'include_beta': False, 'include_alpha': False}, 'managed_content': {'modrinth_failure_policy': 'block', 'curseforge_failure_policy': 'block', 'forge_preflight_failure_policy': 'ask'}, 'network': {'download_limit_mbps': 0.0, 'download_concurrency': 0, 'download_performance_mode': 'automatic'}, 'storage': {'notify_legacy_cache_cleanup': True, 'unused_version_retention_days': 14}, 'instance_defaults': default_instance_settings(), 'updates': {'auto_check': True, 'channel': 'stable', 'channel_policy_version': UPDATE_CHANNEL_POLICY_VERSION, 'last_checked_at': None}}`

Methods:

```python
initialize() -> Path
```

```python
load() -> dict[str, Any]
```

```python
save(settings: dict[str, Any]) -> dict[str, Any]
```

```python
update_section(section: str, values: dict[str, Any]) -> dict[str, Any]
```

```python
reset() -> dict[str, Any]
```

```python
load_window_geometry() -> bytes | None
```

```python
save_window_geometry(geometry: bytes | bytearray | memoryview) -> None
```

### `mcw_core.api.config.managed_content_policy`

Source re-export: `src.core.config.managed_content_policy`

#### `ManagedContentPolicy`

Public constants:

- `INHERIT = 'inherit'`
- `BLOCK = 'block'`
- `ALLOW = 'allow'`
- `ASK = 'ask'`
- `PROVIDERS = {'modrinth', 'curseforge', 'forge_preflight'}`

Methods:

```python
normalize_instance(value: object, default: str = INHERIT) -> str
``` *(classmethod)*

```python
normalize_global(value: object, default: str = BLOCK) -> str
``` *(classmethod)*

```python
from_legacy_bool(value: object, default: bool = True) -> str
``` *(classmethod)*

```python
resolve(instance_settings: object, launcher_settings: dict[str, Any], provider: str) -> str
``` *(classmethod)*

```python
blocks_launch(instance_settings: object, launcher_settings: dict[str, Any], provider: str) -> bool
``` *(classmethod)*

```python
asks_before_launch(instance_settings: object, launcher_settings: dict[str, Any], provider: str) -> bool
``` *(classmethod)*

### `mcw_core.api.content.content_pack_manager`

Source re-export: `src.core.content.content_pack_manager`

#### `ContentPackManager`

Public constants:

- `RESOURCE_PACK = 'resourcepack'`
- `SHADER_PACK = 'shader'`
- `SUPPORTED_TYPES = frozenset({RESOURCE_PACK, SHADER_PACK})`
- `MAX_ARCHIVE_ENTRIES = 20000`
- `MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024`

Methods:

```python
list_entries(instance: Instance, content_type: str = '') -> list[ContentPackEntry]
``` *(classmethod)*

```python
install_modrinth(instance: Instance, content_type: str, version_id: str, reporter: ProgressReporter | None = None) -> ContentPackInstallResult
``` *(classmethod)*

```python
install_curseforge(instance: Instance, content_type: str, file: CurseForgeFile, project_name: str = '', project_url: str = '', reporter: ProgressReporter | None = None) -> ContentPackInstallResult
``` *(classmethod)*

```python
import_local(instance: Instance, content_type: str, source: Path) -> ContentPackInstallResult
``` *(classmethod)*

```python
set_enabled(instance: Instance, entry_id: str, enabled: bool) -> ContentPackEntry
``` *(classmethod)*

```python
remove(instance: Instance, entry_id: str) -> ContentPackEntry
``` *(classmethod)*

```python
destination_dir(instance: Instance, content_type: str) -> Path
``` *(classmethod)*

```python
migrate_legacy_location(instance: Instance, content_type: str = '') -> dict[str, object]
``` *(classmethod)*

```python
validate_archive(source: Path, content_type: str) -> dict[str, object]
``` *(classmethod)*

```python
normalize_type(value: str) -> str
``` *(classmethod)*

```python
display_name(content_type: str) -> str
``` *(classmethod)*

```python
curseforge_project_url(content_type: str, project_id: int | str) -> str
``` *(classmethod)*

### `mcw_core.api.content.content_pack_registry`

Source re-export: `src.core.content.content_pack_registry`

#### `ContentPackRegistry`

Public constants:

- `SCHEMA_VERSION = 1`
- `REGISTRY_RELATIVE_PATH = Path('.mcw') / 'content-packs.json'`

Methods:

```python
path(instance: Instance) -> Path
``` *(classmethod)*

```python
load(instance: Instance) -> dict
``` *(classmethod)*

```python
save(instance: Instance, payload: dict) -> Path
``` *(classmethod)*

```python
entries(instance: Instance, content_type: str = '') -> list[ContentPackEntry]
``` *(classmethod)*

```python
upsert(instance: Instance, entry: ContentPackEntry) -> None
``` *(classmethod)*

```python
remove(instance: Instance, entry_id: str) -> ContentPackEntry | None
``` *(classmethod)*

### `mcw_core.api.content.installed_content_library`

Source re-export: `src.core.content.installed_content_library`

#### `InstalledContentLibraryManager`

Public constants:

- `MOD = 'mod'`
- `RESOURCE_PACK = ContentPackManager.RESOURCE_PACK`
- `SHADER_PACK = ContentPackManager.SHADER_PACK`
- `MODPACK = 'modpack'`
- `SUPPORTED_TYPES = frozenset({MOD, RESOURCE_PACK, SHADER_PACK, MODPACK})`

Methods:

```python
scan(instance: Instance) -> InstalledContentLibrary
``` *(classmethod)*

```python
import_local(instance: Instance, content_type: str, source_paths: list[Path] | tuple[Path, ...], *, replace: bool = False) -> tuple[str, ...]
``` *(classmethod)*

```python
detect_local_content_type(source: Path) -> str
``` *(classmethod)*

```python
set_enabled(instance: Instance, item_ids: list[str] | tuple[str, ...], enabled: bool) -> tuple[str, ...]
``` *(classmethod)*

```python
remove(instance: Instance, item_ids: list[str] | tuple[str, ...]) -> tuple[str, ...]
``` *(classmethod)*

```python
set_pinned(instance: Instance, item_ids: list[str] | tuple[str, ...], pinned: bool) -> tuple[str, ...]
``` *(staticmethod)*

```python
set_ignored_update(instance: Instance, item_ids: list[str] | tuple[str, ...], ignored: bool) -> tuple[str, ...]
``` *(staticmethod)*

```python
destination_folder(instance: Instance, content_type: str) -> Path
``` *(classmethod)*

Source re-export: `src.models.content.installed_content`

#### `InstalledContentItem`

Fields / public attributes:

- `item_id: str`
- `content_type: str`
- `name: str`
- `version: str`
- `provider: str`
- `project_id: str`
- `version_id: str`
- `file_id: str`
- `file_name: str`
- `target_path: str`
- `enabled: bool`
- `managed_by_modpack: bool`
- `source_pack_provider: str`
- `size: int`
- `sha1: str`
- `sha512: str`
- `project_url: str`
- `status: str`
- `pinned: bool = False`
- `ignored_update: bool = False`
- `toggleable: bool = False`
- `removable: bool = False`

#### `InstalledContentLibrary`

Fields / public attributes:

- `instance_name: str`
- `items: tuple[InstalledContentItem, ...]`

Methods:

```python
total_count() -> int
``` *(property)*

```python
enabled_count() -> int
``` *(property)*

```python
pending_count() -> int
``` *(property)*

```python
missing_count() -> int
``` *(property)*

```python
managed_count() -> int
``` *(property)*

```python
total_size() -> int
``` *(property)*

### `mcw_core.api.curseforge.curseforge_client`

Source re-export: `src.core.curseforge.curseforge_client`

#### `CurseForgeClient`

Public constants:

- `MINECRAFT_GAME_ID = 432`
- `CLASS_MODS = 6`
- `CLASS_RESOURCE_PACKS = 12`
- `CLASS_MODPACKS = 4471`
- `CLASS_SHADERS = 6552`
- `CLASS_IDS = {'mod': CLASS_MODS, 'modpack': CLASS_MODPACKS, 'resourcepack': CLASS_RESOURCE_PACKS, 'shader': CLASS_SHADERS}`
- `SEARCH_TTL_SECONDS = 2 * 60`
- `FILES_TTL_SECONDS = 5 * 60`
- `PROJECT_TTL_SECONDS = 10 * 60`
- `FILE_TTL_SECONDS = 30 * 60`
- `BATCH_TTL_SECONDS = 30 * 60`
- `REQUEST_TIMEOUT_SECONDS = 15.0`
- `FAILOVER_STATUS_CODES = frozenset({404, 408, 425, 429, *range(500, 600)})`
- `PERMANENT_GATEWAY_CODES = frozenset({'CURSEFORGE_CREDENTIALS_UNAVAILABLE', 'FILE_UNAVAILABLE', 'THIRD_PARTY_DISTRIBUTION_DISABLED', 'MANUAL_DOWNLOAD_REQUIRED', 'GATEWAY_CREDENTIALS_REJECTED', 'UPSTREAM_FORBIDDEN', 'UPSTREAM_REJECTED_REQUEST'})`

Methods:

```python
is_available() -> bool
``` *(staticmethod)*

```python
gateway_urls() -> tuple[str, ...]
``` *(staticmethod)*

```python
gateway_url() -> str
``` *(staticmethod)*

```python
api_cache_status() -> CurseForgeCacheInfo
``` *(staticmethod)*

```python
clear_api_cache() -> None
``` *(staticmethod)*

```python
cache_status() -> CurseForgeCacheInfo
``` *(staticmethod)*

```python
clear_cache() -> None
``` *(staticmethod)*

```python
manual_refresh_remaining_seconds() -> int
``` *(staticmethod)*

```python
search_projects(project_type: str, query: str = '', game_version: str = '', loader: str = 'forge', index: int = 0, page_size: int = 25, sort: str = 'popularity', force_refresh: bool = False, manual_refresh: bool = False) -> CurseForgeSearchResult
``` *(staticmethod)*

```python
get_project(project_id: int | str, force_refresh: bool = False) -> CurseForgeProject
``` *(staticmethod)*

```python
get_project_details(project_id: int | str, force_refresh: bool = False) -> CurseForgeProject
``` *(staticmethod)*

```python
get_projects_batch(project_ids: list[int] | tuple[int, ...] | set[int]) -> dict[int, CurseForgeProject]
``` *(staticmethod)*

```python
list_files_result(project_id: int | str, game_version: str = '', loader: str = 'forge', release_types: tuple[str, ...] | list[str] | set[str] | None = None, page_size: int = 50, force_refresh: bool = False, manual_refresh: bool = False) -> CurseForgeFileListResult
``` *(staticmethod)*

```python
list_files(project_id: int | str, game_version: str = '', loader: str = 'forge', release_types: tuple[str, ...] | list[str] | set[str] | None = None, page_size: int = 50, force_refresh: bool = False) -> list[CurseForgeFile]
``` *(staticmethod)*

```python
get_file(project_id: int | str, file_id: int | str, force_refresh: bool = False) -> CurseForgeFile
``` *(staticmethod)*

```python
get_files_batch(file_ids: list[int] | tuple[int, ...] | set[int]) -> dict[int, CurseForgeFile]
``` *(staticmethod)*

```python
get_download_url(project_id: int | str, file_id: int | str, force_refresh: bool = False) -> str
``` *(staticmethod)*

```python
latest_compatible_file(project_id: int | str, game_version: str, loader: str = 'forge', release_types: tuple[str, ...] | list[str] | set[str] | None = None) -> CurseForgeFile
``` *(staticmethod)*

```python
normalize_loader(loader: str) -> str
``` *(staticmethod)*

```python
loader_compatibility(file: CurseForgeFile, loader: str) -> str
``` *(staticmethod)*

```python
is_permanent_error(error: BaseException) -> bool
``` *(staticmethod)*

```python
normalize_release_types(release_types: tuple[str, ...] | list[str] | set[str] | None = None) -> tuple[str, ...]
``` *(staticmethod)*

### `mcw_core.api.curseforge.curseforge_errors`

Source re-export: `src.core.curseforge.curseforge_errors`

#### `CurseForgeManagedFilesRequired`

Raised when managed CurseForge files require user-assisted recovery.

Bases: `RuntimeError`

#### `CurseForgeModpackManualDownloadRequired`

Raised when a CurseForge modpack archive must be downloaded manually.

Bases: `RuntimeError`

### `mcw_core.api.curseforge.curseforge_links`

Source re-export: `src.core.curseforge.curseforge_links`

#### `normalize_project_page`

```python
normalize_project_page(url: object) -> str
```

#### `project_search_url`

```python
project_search_url(project_id: int | str) -> str
```

#### `file_page_url`

```python
file_page_url(project_url: object, file_id: int | str) -> str
```

#### `best_manual_download_url`

```python
best_manual_download_url(requirement: object) -> str
```

### `mcw_core.api.curseforge.curseforge_manual_installer`

Source re-export: `src.core.curseforge.curseforge_manual_installer`

#### `CurseForgeManualInstaller`

Methods:

```python
install(instance: Instance, requirement: CurseForgeManualDownload, source: Path, launch_lock_token: str | None = None) -> str
``` *(staticmethod)*

```python
install_many(instance: Instance, requirements: tuple[CurseForgeManualDownload, ...] | list[CurseForgeManualDownload], sources: tuple[Path, ...] | list[Path], launch_lock_token: str | None = None) -> CurseForgeManualImportResult
``` *(staticmethod)*

```python
copy_to_cache(source: Path, destination: Path) -> Path
``` *(staticmethod)*

### `mcw_core.api.curseforge.curseforge_mod_installer`

Source re-export: `src.core.curseforge.curseforge_mod_installer`

#### `CurseForgeModInstaller`

Public constants:

- `MAX_DEPENDENCIES = 64`

Methods:

```python
install(instance: Instance, project_id: int, file_id: int, install_dependencies: bool = True, allowed_release_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None, allow_unverified: bool = False) -> CurseForgeModInstallResult
``` *(staticmethod)*

### `mcw_core.api.curseforge.curseforge_pack_installer`

Source re-export: `src.core.curseforge.curseforge_pack_installer`

#### `CurseForgePackInstaller`

Public constants:

- `MANIFEST_NAME = 'manifest.json'`
- `MAX_MANIFEST_BYTES = 4 * 1024 * 1024`
- `MAX_FILES = 5000`
- `MAX_OVERRIDE_BYTES = 2 * 1024 * 1024 * 1024`
- `MAX_PATH_LENGTH = 240`
- `MAX_WORKERS = 8`
- `RESERVED_ROOT_NAMES = {'instance.json', 'settings.json', '.mcw'}`
- `INSTANCE_NAME_PATTERN = re.compile('^[^<>:"/\\\\|?*\\x00-\\x1F]{1,80}$')`
- `SUPPORTED_LOADERS = (ModLoaderManager.FABRIC, ModLoaderManager.QUILT, ModLoaderManager.FORGE, ModLoaderManager.NEOFORGE)`

Methods:

```python
install(project_id: int, file_id: int, instance_name: str, install_optional_files: bool = True, allowed_release_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None, expected_loader: str = '', settings_override: dict | None = None) -> CurseForgeModpackInstallResult
``` *(staticmethod)*

```python
install_local_archive(pack_path: Path, instance_name: str = '', install_optional_files: bool = True, reporter: ProgressReporter | None = None, settings_override: dict | None = None) -> CurseForgeModpackInstallResult
``` *(staticmethod)*

```python
install_manual_archive(request: CurseForgeModpackManualDownloadRequired, source: Path, reporter: ProgressReporter | None = None) -> CurseForgeModpackInstallResult
``` *(staticmethod)*

### `mcw_core.api.curseforge.curseforge_registry`

Source re-export: `src.core.curseforge.curseforge_registry`

#### `CurseForgeRegistry`

Public constants:

- `SCHEMA_VERSION = 1`

Methods:

```python
empty() -> dict
``` *(staticmethod)*

```python
load(instance: Instance) -> dict
``` *(staticmethod)*

```python
save(instance: Instance, data: dict) -> None
``` *(staticmethod)*

```python
remove_by_filenames(instance: Instance, filenames: list[str] | tuple[str, ...] | set[str]) -> tuple[str, ...]
``` *(staticmethod)*

```python
safe_tracked_path(instance: Instance, filename: str) -> Path | None
``` *(staticmethod)*

### `mcw_core.api.diagnostics.diagnostics_manager`

Source re-export: `src.core.diagnostics.diagnostics_manager`

#### `DiagnosticsManager`

Public constants:

- `REPORT_SCHEMA_VERSION = '2.1'`
- `BUNDLE_SCHEMA_VERSION = '2.1'`
- `MAX_LOG_FILES = 8`
- `MAX_LOG_BYTES = 256 * 1024`
- `MAX_TOTAL_LOG_BYTES = 2 * 1024 * 1024`

Methods:

```python
build_report(launcher_version: str, settings: dict[str, Any] | None = None, activity_log: str = '') -> str
``` *(classmethod)*

```python
write_report(path: Path, launcher_version: str, settings: dict[str, Any] | None = None, activity_log: str = '') -> Path
``` *(classmethod)*

```python
write_bundle(path: Path, launcher_version: str, settings: dict[str, Any] | None = None, activity_log: str = '', *, task_timeline: tuple[dict[str, object], ...] | list[dict[str, object]] = (), issue_context: dict[str, Any] | None = None) -> Path
``` *(classmethod)*

### `mcw_core.api.diagnostics.issue_report_builder`

Source re-export: `src.core.diagnostics.issue_report_builder`

#### `IssueReportBuilder`

Build a privacy-filtered GitHub issue draft from user-provided context.

Methods:

```python
normalize(details: dict[str, Any]) -> dict[str, str]
``` *(staticmethod)*

```python
build_body(details: dict[str, Any], *, launcher_version: str, diagnostics_path: Path | None = None) -> str
``` *(classmethod)*

```python
github_new_issue_url(repository: str, details: dict[str, Any], *, launcher_version: str, diagnostics_path: Path | None = None) -> str
``` *(classmethod)*

### `mcw_core.api.fs.paths`

Source re-export: `src.core.fs.paths`

#### `Paths`

Public constants:

- `PROJECT_ROOT = PROJECT_ROOT`
- `CACHE_ROOT = PROJECT_ROOT / 'cache'`
- `INSTANCES_ROOT = PROJECT_ROOT / 'instances'`
- `ACCOUNTS_ROOT = PROJECT_ROOT / 'accounts'`
- `CONFIG_ROOT = PROJECT_ROOT / 'config'`
- `LOGS_ROOT = PROJECT_ROOT / 'logs'`
- `BACKUPS_ROOT = PROJECT_ROOT / 'backups'`
- `THEME_ROOT = PROJECT_ROOT / 'themes'`
- `RUNTIMES_ROOT = PROJECT_ROOT / 'runtimes'`
- `INSTANCE_LOCKS_ROOT = INSTANCES_ROOT / '.runtime' / 'locks'`
- `SHORT_WORKSPACE_ROOT = _default_short_workspace_root()`

Methods:

```python
configure_application_defaults(*, platform_name: str | None = None, environ: dict[str, str] | None = None, home: Path | str | None = None, initialize: bool = False) -> bool
``` *(staticmethod)*

```python
uses_platform_storage() -> bool
``` *(staticmethod)*

```python
initialize() -> None
``` *(staticmethod)*

```python
backups_root() -> Path
``` *(staticmethod)*

```python
instance_backups_dir(instance: Instance) -> Path
``` *(staticmethod)*

```python
backup_staging_root() -> Path
``` *(staticmethod)*

```python
theme_asset(theme: str, *paths: str) -> Path
``` *(staticmethod)*

```python
theme_dir(name: str) -> Path
``` *(staticmethod)*

```python
root() -> Path
``` *(staticmethod)*

```python
snapshot() -> dict[str, Path]
``` *(staticmethod)*

```python
restore(snapshot: dict[str, Path], initialize: bool = False) -> None
``` *(staticmethod)*

```python
configure(root: Path | str | None = None, *, cache_root: Path | str | None = None, instances_root: Path | str | None = None, accounts_root: Path | str | None = None, config_root: Path | str | None = None, logs_root: Path | str | None = None, backups_root: Path | str | None = None, theme_root: Path | str | None = None, runtimes_root: Path | str | None = None, initialize: bool = True) -> dict[str, Path]
``` *(staticmethod)*

```python
configured(root: Path | str | None = None, **overrides: object) -> Iterator[None]
``` *(staticmethod)*

```python
short_workspace_root() -> Path
``` *(staticmethod)*

```python
create_short_workspace(purpose: str) -> Path
``` *(staticmethod)*

```python
cleanup_short_workspace(workspace: Path) -> None
``` *(staticmethod)*

```python
microsoft_config_root() -> Path
``` *(staticmethod)*

```python
launcher_settings_path() -> Path
``` *(staticmethod)*

```python
logs_root() -> Path
``` *(staticmethod)*

```python
updater_log_path() -> Path
``` *(staticmethod)*

```python
diagnostics_default_path() -> Path
``` *(staticmethod)*

```python
download_journal_path() -> Path
``` *(staticmethod)*

```python
content_store_root() -> Path
``` *(staticmethod)*

```python
content_store_blob(sha256: str) -> Path
``` *(staticmethod)*

```python
update_root() -> Path
``` *(staticmethod)*

```python
update_release_cache() -> Path
``` *(staticmethod)*

```python
update_download_path(tag_name: str, asset_name: str) -> Path
``` *(staticmethod)*

```python
update_staging_root() -> Path
``` *(staticmethod)*

```python
account_database_path()
``` *(staticmethod)*

```python
account_skins_root() -> Path
``` *(staticmethod)*

```python
accounts_path() -> Path
``` *(staticmethod)*

```python
instance_metadata(instance_name: str) -> Path
``` *(staticmethod)*

```python
instance_settings_path(instance: Instance) -> Path
``` *(staticmethod)*

```python
instance_settings_create(instance: Instance) -> Path
``` *(staticmethod)*

```python
instances_root() -> Path
``` *(staticmethod)*

```python
instance_runtime_root() -> Path
``` *(staticmethod)*

```python
instance_operations_root() -> Path
``` *(staticmethod)*

```python
instance_staging_root() -> Path
``` *(staticmethod)*

```python
process_sessions_root() -> Path
``` *(staticmethod)*

```python
process_session_history_root() -> Path
``` *(staticmethod)*

```python
load_instance_dir(name: str) -> Path
``` *(staticmethod)*

```python
create_instance_dir(name: str) -> Path
``` *(staticmethod)*

```python
instance_data_path_create()
``` *(staticmethod)*

```python
instance_data_path()
``` *(staticmethod)*

```python
version_dir(version: Version)
``` *(staticmethod)*

```python
client(version: Version)
``` *(staticmethod)*

```python
fabric_version_dir(game_version: str, loader_version: str) -> Path
``` *(staticmethod)*

```python
fabric_version_json(game_version: str, loader_version: str) -> Path
``` *(staticmethod)*

```python
fabric_metadata_root() -> Path
``` *(staticmethod)*

```python
fabric_catalog_json(game_version: str) -> Path
``` *(staticmethod)*

```python
fabric_install_metadata_json(game_version: str, loader_version: str) -> Path
``` *(staticmethod)*

```python
fabric_profile_json(game_version: str, loader_version: str) -> Path
``` *(staticmethod)*

```python
quilt_version_dir(game_version: str, loader_version: str) -> Path
``` *(staticmethod)*

```python
quilt_version_json(game_version: str, loader_version: str) -> Path
``` *(staticmethod)*

```python
quilt_metadata_root() -> Path
``` *(staticmethod)*

```python
quilt_catalog_json(game_version: str) -> Path
``` *(staticmethod)*

```python
quilt_install_metadata_json(game_version: str, loader_version: str) -> Path
``` *(staticmethod)*

```python
quilt_profile_json(game_version: str, loader_version: str) -> Path
``` *(staticmethod)*

```python
neoforge_root() -> Path
``` *(staticmethod)*

```python
neoforge_version_dir(game_version: str, neoforge_version: str) -> Path
``` *(staticmethod)*

```python
neoforge_version_json(game_version: str, neoforge_version: str) -> Path
``` *(staticmethod)*

```python
neoforge_installer_path(game_version: str, neoforge_version: str) -> Path
``` *(staticmethod)*

```python
neoforge_staging_dir(game_version: str, neoforge_version: str) -> Path
``` *(staticmethod)*

```python
forge_root() -> Path
``` *(staticmethod)*

```python
forge_version_dir(game_version: str, forge_version: str) -> Path
``` *(staticmethod)*

```python
forge_version_json(game_version: str, forge_version: str) -> Path
``` *(staticmethod)*

```python
forge_installer_path(game_version: str, forge_version: str) -> Path
``` *(staticmethod)*

```python
forge_staging_dir(game_version: str, forge_version: str) -> Path
``` *(staticmethod)*

```python
forge_instance_root(instance: Instance) -> Path
``` *(staticmethod)*

```python
forge_rollback_path(instance: Instance) -> Path
``` *(staticmethod)*

```python
forge_instance_log_path(instance: Instance) -> Path
``` *(staticmethod)*

```python
forge_diagnostics_default_path(instance: Instance) -> Path
``` *(staticmethod)*

```python
ftb_root() -> Path
``` *(staticmethod)*

```python
ftb_api_cache_root() -> Path
``` *(staticmethod)*

```python
ftb_artifact_cache_root() -> Path
``` *(staticmethod)*

```python
ftb_file_cache(project_id: int | str, version_id: int | str, filename: str) -> Path
``` *(staticmethod)*

```python
ftb_pack_registry(instance: Instance) -> Path
``` *(staticmethod)*

```python
atlauncher_root() -> Path
``` *(staticmethod)*

```python
atlauncher_api_cache_root() -> Path
``` *(staticmethod)*

```python
atlauncher_pack_registry(instance: Instance) -> Path
``` *(staticmethod)*

```python
curseforge_root() -> Path
``` *(staticmethod)*

```python
curseforge_api_cache_root() -> Path
``` *(staticmethod)*

```python
curseforge_artifact_cache_root() -> Path
``` *(staticmethod)*

```python
curseforge_api_cache(cache_key: str) -> Path
``` *(staticmethod)*

```python
curseforge_file_cache(project_id: int | str, file_id: int | str, filename: str) -> Path
``` *(staticmethod)*

```python
curseforge_pack_cache(project_id: int | str, file_id: int | str, filename: str) -> Path
``` *(staticmethod)*

```python
instance_artwork_cache(provider: str, project_id: str, artwork_url: str) -> Path
``` *(staticmethod)*

```python
curseforge_instance_registry(instance: Instance) -> Path
``` *(staticmethod)*

```python
curseforge_instance_transaction_root(instance: Instance) -> Path
``` *(staticmethod)*

```python
curseforge_pack_registry(instance: Instance) -> Path
``` *(staticmethod)*

```python
instance_logs_dir(instance: Instance) -> Path
``` *(staticmethod)*

```python
instance_crash_reports_dir(instance: Instance) -> Path
``` *(staticmethod)*

```python
instance_runtime_history(instance: Instance) -> Path
``` *(staticmethod)*

```python
instance_repair_report(instance: Instance) -> Path
``` *(staticmethod)*

```python
instance_repair_cache(instance: Instance) -> Path
``` *(staticmethod)*

```python
instance_repair_scan_report(instance: Instance) -> Path
``` *(staticmethod)*

```python
instance_repair_execution_report(instance: Instance) -> Path
``` *(staticmethod)*

```python
instance_mods_dir(instance: Instance) -> Path
``` *(staticmethod)*

```python
mod_provenance_registry(instance: Instance) -> Path
``` *(staticmethod)*

```python
optifine_root() -> Path
``` *(staticmethod)*

```python
optifine_metadata_cache() -> Path
``` *(staticmethod)*

```python
optifine_source_cache(sha256: str, filename: str = 'OptiFine.jar') -> Path
``` *(staticmethod)*

```python
optifine_staging_dir(instance: Instance) -> Path
``` *(staticmethod)*

```python
optifine_registry(instance: Instance) -> Path
``` *(staticmethod)*

```python
optifine_profile(instance: Instance) -> Path
``` *(staticmethod)*

```python
modrinth_root() -> Path
``` *(staticmethod)*

```python
modrinth_api_cache_root() -> Path
``` *(staticmethod)*

```python
modrinth_artifact_cache_root() -> Path
``` *(staticmethod)*

```python
modrinth_api_cache(cache_key: str) -> Path
``` *(staticmethod)*

```python
modrinth_file_cache(project_id: str, version_id: str, filename: str) -> Path
``` *(staticmethod)*

```python
modrinth_pack_cache(project_id: str, version_id: str, filename: str) -> Path
``` *(staticmethod)*

```python
modrinth_staging_root() -> Path
``` *(staticmethod)*

```python
modrinth_instance_registry(instance: Instance) -> Path
``` *(staticmethod)*

```python
libraries()
``` *(staticmethod)*

```python
version_manifest() -> Path
``` *(staticmethod)*

```python
version_json(version: Version) -> Path
``` *(staticmethod)*

```python
asset_index(version: Version)
``` *(staticmethod)*

```python
asset_index_dir()
``` *(staticmethod)*

```python
asset_object(asset: DownloadAsset)
``` *(staticmethod)*

```python
assets_dir()
``` *(staticmethod)*

```python
natives(version: Version)
``` *(staticmethod)*

### `mcw_core.api.ftb.ftb_client`

Source re-export: `src.core.ftb.ftb_client`

#### `FTBClient`

Small public FTB modpack API adapter.

Public constants:

- `PUBLIC_BASE_URL = 'https://api.feed-the-beast.com/v1/modpacks/public'`
- `DIRECT_BASE_URL = 'https://api.feed-the-beast.com/v1/modpacks'`
- `BASE_URLS = (PUBLIC_BASE_URL, DIRECT_BASE_URL)`
- `SEARCH_TTL_SECONDS = 5 * 60`
- `PROJECT_TTL_SECONDS = 15 * 60`
- `VERSION_TTL_SECONDS = 30 * 60`
- `REQUEST_TIMEOUT_SECONDS = 20.0`
- `MAX_SEARCH_FETCH = 100`
- `FAILOVER_STATUS_CODES = frozenset({404, 408, 425, 429, *range(500, 600)})`

Methods:

```python
api_cache_status() -> FTBCacheInfo
``` *(staticmethod)*

```python
clear_api_cache() -> None
``` *(staticmethod)*

```python
cache_status() -> FTBCacheInfo
``` *(staticmethod)*

```python
clear_cache() -> None
``` *(staticmethod)*

```python
search_projects(query: str = '', index: int = 0, page_size: int = 25, sort: str = 'popularity', force_refresh: bool = False) -> FTBSearchResult
``` *(staticmethod)*

```python
get_project(project_id: int | str, force_refresh: bool = False) -> FTBProject
``` *(staticmethod)*

```python
get_project_details(project_id: int | str, force_refresh: bool = False) -> FTBProject
``` *(staticmethod)*

```python
list_versions(project_id: int | str, release_types: Iterable[str] | None = None, force_refresh: bool = False) -> tuple[FTBVersionSummary, ...]
``` *(staticmethod)*

```python
get_version(project_id: int | str, version_id: int | str, force_refresh: bool = False) -> FTBVersion
``` *(staticmethod)*

```python
normalize_release_type(value: object) -> str
``` *(staticmethod)*

```python
normalize_loader(value: object) -> str
``` *(staticmethod)*

### `mcw_core.api.ftb.ftb_content_manager`

Source re-export: `src.core.ftb.ftb_content_manager`

#### `FTBContentManager`

Materialize deferred FTB modpack files immediately before launch.

Public constants:

- `PROGRESS_EMIT_INTERVAL_SECONDS = 0.08`

Methods:

```python
ensure(instance: Instance, reporter: ProgressReporter | None = None, launch_lock_token: str | None = None) -> tuple[str, ...]
``` *(staticmethod)*

### `mcw_core.api.ftb.ftb_pack_installer`

Source re-export: `src.core.ftb.ftb_pack_installer`

#### `FTBPackInstaller`

Public constants:

- `MAX_FILES = 20000`
- `MAX_TOTAL_BYTES = 50 * 1024 * 1024 * 1024`
- `MAX_PATH_LENGTH = 240`
- `RESERVED_ROOT_NAMES = {'instance.json', 'settings.json', '.mcw'}`
- `INSTANCE_NAME_PATTERN = re.compile('^[^<>:"/\\\\|?*\\x00-\\x1F]{1,80}$')`
- `SUPPORTED_LOADERS = frozenset(ModLoaderManager.MODDED_LOADERS)`

Methods:

```python
install(project_id: int, version_id: int, instance_name: str, install_optional_files: bool = True, allowed_release_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None, settings_override: dict | None = None) -> FTBModpackInstallResult
``` *(staticmethod)*

### `mcw_core.api.ftb.ftb_pack_registry`

Source re-export: `src.core.ftb.ftb_pack_registry`

#### `FTBPackRegistry`

Public constants:

- `SCHEMA_VERSION = 2`

Methods:

```python
load(instance: Instance | Path) -> dict
``` *(staticmethod)*

```python
save(instance: Instance | Path, data: dict) -> None
``` *(staticmethod)*

```python
safe_relative_path(value: str, fallback_filename: str) -> str
``` *(staticmethod)*

### `mcw_core.api.hardware.first_run_recommendation_service`

Source re-export: `src.core.hardware.first_run_recommendation_service`

#### `FirstRunRecommendationService`

Collect safe first-run defaults without depending on the GUI.

Methods:

```python
inspect() -> FirstRunRecommendation
``` *(classmethod)*

```python
fallback() -> FirstRunRecommendation
``` *(classmethod)*

```python
recommended_max_memory_mb(total_memory_mb: int, available_memory_mb: int = 0) -> int
``` *(classmethod)*

```python
available_physical_memory_mb() -> int
``` *(staticmethod)*

Source re-export: `src.models.hardware.first_run_recommendation`

#### `JavaRuntimeSummary`

Fields / public attributes:

- `major: int`
- `executable: Path`
- `source: str`

#### `FirstRunRecommendation`

Fields / public attributes:

- `total_memory_mb: int`
- `available_memory_mb: int`
- `recommended_min_memory_mb: int`
- `recommended_max_memory_mb: int`
- `java_installations: tuple[JavaRuntimeSummary, ...]`
- `recommended_java_path: str = ''`

Methods:

```python
java_majors() -> tuple[int, ...]
``` *(property)*

### `mcw_core.api.hardware.gpu_preference_manager`

Source re-export: `src.core.hardware.gpu_preference_manager`

#### `GraphicsAdapter`

Fields / public attributes:

- `name: str`
- `vendor: str = ''`
- `adapter_ram: int = 0`
- `pnp_device_id: str = ''`
- `dedicated: bool = False`

#### `GraphicsDetectionResult`

Fields / public attributes:

- `supported: bool`
- `adapters: tuple[GraphicsAdapter, ...] = ()`
- `error: str = ''`

Methods:

```python
dedicated_adapters() -> tuple[GraphicsAdapter, ...]
``` *(property)*

```python
has_dedicated_gpu() -> bool
``` *(property)*

#### `GpuPreferenceManager`

Best-effort Windows graphics preference integration.

Public constants:

- `REGISTRY_PATH = 'Software\\Microsoft\\DirectX\\UserGpuPreferences'`
- `HIGH_PERFORMANCE_VALUE = 'GpuPreference=2;'`
- `DETECTION_TIMEOUT_SECONDS = 8`

Methods:

```python
detect() -> GraphicsDetectionResult
``` *(classmethod)*

```python
apply_for_executable(executable: Path | str, enabled: bool) -> bool
``` *(classmethod)*

```python
apply_to_java(java_path: Path | str, enabled: bool) -> bool
``` *(classmethod)*

```python
adapter_summary(adapters: Iterable[GraphicsAdapter]) -> str
``` *(classmethod)*

### `mcw_core.api.instance.errors`

Source re-export: `src.core.instance.errors`

#### `InstanceAlreadyRunningError`

Bases: `RuntimeError`

#### `InstanceModChangeBlockedError`

Bases: `RuntimeError`

#### `InstanceDeletionError`

Structured failure raised when an instance cannot be removed safely.

Bases: `RuntimeError`

### `mcw_core.api.instance.instance_health_manager`

Source re-export: `src.core.instance.instance_health_manager`

#### `InstanceHealthManager`

Run a fast, non-networked health check suitable for launcher startup.

Methods:

```python
scan(instance: Instance) -> InstanceHealthReport
``` *(classmethod)*

```python
list(instances: list[Instance]) -> list[InstanceHealthReport]
``` *(classmethod)*

### `mcw_core.api.instance.instance_manager`

Source re-export: `src.core.instance.instance_manager`

#### `InstanceManager`

Public constants:

- `METADATA_VERSION = 3`
- `DEFAULT_ICON = 'grass_block'`
- `ICON_DIRECTORY = '.mcw'`
- `ICON_BASENAME = 'instance-icon'`
- `ICON_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.ico'}`
- `MAX_ICON_BYTES = 8 * 1024 * 1024`
- `DIRECTORY_COMMIT_ATTEMPTS = 8`
- `DIRECTORY_COMMIT_RETRY_SECONDS = 0.15`
- `INSTANCE_NAME_PATTERN = re.compile('^[^<>:"/\\\\|?*\\x00-\\x1F]{1,80}$')`
- `WINDOWS_RESERVED_NAMES = {'con', 'prn', 'aux', 'nul', *(f'com{index}' for index in range(1, 10)), *(f'lpt{index}' for index in range(1, 10))}`

Methods:

```python
validate_name(value: str) -> str
``` *(staticmethod)*

```python
set_library_metadata(name: str, *, favorite: bool | None = None, group: str | None = None, tags: object | None = None) -> Instance
``` *(staticmethod)*

```python
list_instances() -> list[Instance]
``` *(staticmethod)*

```python
clone(source_name: str, new_name: str, include_saves: bool = False) -> Instance
``` *(staticmethod)*

```python
export(instance_name: str, output_path: Path, include_saves: bool = False, on_progress: ProgressCallback | None = None) -> Path
``` *(staticmethod)*

```python
set_icon(instance_name: str, source_path: Path, origin: dict | None = None) -> Instance
``` *(staticmethod)*

```python
reset_icon(instance_name: str) -> Instance
``` *(staticmethod)*

```python
resolve_icon_path(instance: Instance) -> Path | None
``` *(staticmethod)*

```python
inspect_import(package_path: Path) -> InstancePackagePreview
``` *(staticmethod)*

```python
import_instance(package_path: Path, on_progress: ProgressCallback | None = None, settings_override: dict | InstanceSettings | None = None) -> Instance
``` *(staticmethod)*

```python
rename(instance_name: str, new_name: str) -> Path
``` *(staticmethod)*

```python
load(name: str) -> Instance
``` *(staticmethod)*

```python
create(name: str, version: Version, mod_loader = ('vanilla', '-1'), settings: dict | InstanceSettings | None = None) -> Instance
``` *(staticmethod)*

```python
default_instance_settings() -> dict
``` *(staticmethod)*

```python
set_runtime_profile(name: str, version: Version, mod_loader: tuple[str, str]) -> Instance
``` *(staticmethod)*

```python
set_mod_loader(name: str, mod_loader: tuple[str, str]) -> Instance
``` *(staticmethod)*

```python
delete_instance(name: str) -> bool
``` *(staticmethod)*

```python
reconcile_registry() -> dict
``` *(staticmethod)*

```python
next_available_name(preferred_name: str) -> str
``` *(staticmethod)*

```python
is_instance_exist(name: str) -> bool
``` *(staticmethod)*

### `mcw_core.api.instance.instance_operation_journal`

Source re-export: `src.core.instance.instance_operation_journal`

#### `InstanceRecoveryRecord`

Fields / public attributes:

- `operation_id: str`
- `operation: str`
- `result: str`
- `instance_name: str`

#### `InstanceOperationJournal`

Fields / public attributes:

- `operation_id: str`
- `operation: str`
- `instance_name: str`
- `path: Path`
- `payload: dict[str, Any]`

Public constants:

- `SCHEMA_VERSION = 1`

Methods:

```python
begin(operation: str, instance_name: str, *, source_path: Path | None = None, target_path: Path | None = None, staging_path: Path | None = None) -> InstanceOperationJournal
``` *(classmethod)*

```python
update(phase: str, **updates: Any) -> None
```

```python
complete() -> None
```

```python
abandon() -> None
```

```python
recover_all() -> tuple[InstanceRecoveryRecord, ...]
``` *(classmethod)*

### `mcw_core.api.instance.instance_run_lock`

Source re-export: `src.core.instance.instance_run_lock`

#### `RunningInstanceInfo`

Fields / public attributes:

- `instance_id: str | None`
- `name: str`
- `state: str`
- `launcher_pid: int | None`
- `minecraft_pid: int | None`
- `created_at: str`
- `updated_at: str`

#### `InstanceRunLock`

Fields / public attributes:

- `instance_name: str`
- `lock_path: Path`
- `token: str`

Public constants:

- `LOCK_FILENAME = '.mcw-launcher.lock'`
- `SCHEMA_VERSION = 1`
- `MALFORMED_LOCK_GRACE_SECONDS = 5.0`
- `ACQUIRE_ATTEMPTS = 5`

Methods:

```python
acquire(instance: Instance) -> InstanceRunLock
``` *(classmethod)*

```python
track_process(process: Any) -> bool
```

```python
release() -> None
```

```python
is_active(instance: Instance) -> bool
``` *(classmethod)*

```python
owns_preparing_lock(instance: Instance, token: str | None) -> bool
``` *(classmethod)*

```python
active_for(instance: Instance) -> RunningInstanceInfo | None
``` *(classmethod)*

```python
remove_for(instance: Instance, force: bool = False) -> bool
``` *(classmethod)*

```python
reconcile() -> tuple[str, ...]
``` *(classmethod)*

```python
list_active() -> list[RunningInstanceInfo]
``` *(classmethod)*

```python
lock_path_for(instance: Instance) -> Path
``` *(classmethod)*

### `mcw_core.api.instance.settings_manager`

Source re-export: `src.core.instance.settings_manager`

#### `default_instance_settings`

```python
default_instance_settings() -> dict[str, Any]
```

#### `SettingsManager`

Public constants:

- `DEFAULT_SETTINGS = {'java': {'path': '', 'min_memory': 1024, 'max_memory': 2048, 'arguments': []}, 'window': {'width': 1280, 'height': 720, 'fullscreen': False}, 'launch': {'game_arguments': [], 'offline_multiplayer_enabled': False, 'lan_auth_mode': 'microsoft_only', 'lan_connection_provider': 'manual', 'modrinth_failure_policy': 'inherit', 'curseforge_failure_policy': 'inherit', 'forge_preflight_failure_policy': 'inherit'}}`

Methods:

```python
load(instance: Instance) -> InstanceSettings
``` *(staticmethod)*

```python
save(instance: Instance, settings: InstanceSettings) -> None
``` *(staticmethod)*

```python
save_default(instance: Instance) -> None
``` *(staticmethod)*

```python
default_dict() -> dict[str, Any]
``` *(classmethod)*

```python
from_dict(data: dict[str, Any] | InstanceSettings | None) -> InstanceSettings
``` *(staticmethod)*

```python
to_dict(settings: InstanceSettings) -> dict[str, Any]
``` *(staticmethod)*

```python
normalize_dict(data: dict[str, Any] | InstanceSettings | None) -> dict[str, Any]
``` *(staticmethod)*

```python
save_dict(instance: Instance, data: dict[str, Any] | InstanceSettings | None) -> None
``` *(staticmethod)*

```python
update_memory(instance: Instance, min_memory: int, max_memory: int) -> InstanceSettings
``` *(staticmethod)*

```python
update_java_path(instance: Instance, java_path: str) -> InstanceSettings
``` *(staticmethod)*

```python
update_window(instance: Instance, width: int, height: int, fullscreen: bool) -> InstanceSettings
``` *(staticmethod)*

```python
update_jvm_arguments(instance: Instance, arguments: list[str]) -> InstanceSettings
``` *(staticmethod)*

```python
update_game_arguments(instance: Instance, arguments: list[str]) -> InstanceSettings
``` *(staticmethod)*

### `mcw_core.api.java.java_major_policy`

Source re-export: `src.core.java.java_major_policy`

#### `JavaMajorPolicy`

Public constants:

- `SUPPORTED_MAJORS = (8, 17, 21, 25)`

Methods:

```python
required_for_minecraft(game_version: str, metadata_major: object = None) -> int
``` *(classmethod)*

```python
resolve(required_major: int | None) -> int
``` *(classmethod)*

```python
accepted_majors(required_major: int | None) -> tuple[int, ...]
``` *(classmethod)*

### `mcw_core.api.lan.lan_agent_manager`

Source re-export: `src.core.lan.lan_agent_manager`

#### `LanAgentInstallResult`

Fields / public attributes:

- `path: Path`
- `installed: bool`

#### `LanAgentManager`

Install and attach the bundled host-side LAN agent.

Public constants:

- `AUTH_PRIVATE_OFFLINE = 'private_offline'`
- `AGENT_FILENAME = 'mcw-lan-agent.jar'`
- `AGENT_LOG_FILENAME = 'mcw-lan-agent.log'`
- `AGENT_SHA256 = 'c682cd51fbfc9b5e3ed34520eb38a667212c183a68e37ad17694f14f4eace4dc'`
- `TARGET_CLASS = 'net/minecraft/server/MinecraftServer'`
- `TARGET_METHOD = 'setUsesAuthentication'`
- `TARGET_DESCRIPTOR = '(Z)V'`
- `RESERVED_ARGUMENT_PREFIXES = ('-Dmcw.lan.', '-javaagent:')`

Methods:

```python
is_enabled(auth_mode: object) -> bool
``` *(classmethod)*

```python
install() -> LanAgentInstallResult
``` *(classmethod)*

```python
runtime_arguments(version: Version, auth_mode: object, instance: Instance, reporter: ProgressReporter | None = None) -> list[str]
``` *(classmethod)*

```python
log_path(instance: Instance) -> Path
``` *(classmethod)*

```python
prepare_log(instance: Instance, auth_mode: object = 'unknown') -> Path
``` *(classmethod)*

```python
append_log(instance: Instance, message: str) -> None
``` *(classmethod)*

```python
append_log_path(path: Path, message: str) -> None
``` *(staticmethod)*

```python
read_log(instance: Instance) -> str
``` *(classmethod)*

```python
sanitize_user_jvm_arguments(arguments: list[str]) -> list[str]
``` *(classmethod)*

```python
runtime_agent_path() -> Path
``` *(classmethod)*

### `mcw_core.api.lan.lan_hosting_manager`

Source re-export: `src.core.lan.lan_hosting_manager`

#### `LanHostingManager`

Prepare per-instance LAN hosting support.

Public constants:

- `AUTH_MICROSOFT_ONLY = 'microsoft_only'`
- `AUTH_PRIVATE_OFFLINE = 'private_offline'`
- `AUTH_FRIENDS_LEGACY = 'friends'`
- `CONNECTION_MANUAL = 'manual'`
- `CONNECTION_E4MC = 'e4mc'`
- `ROLE_AUTH_BRIDGE = 'auth_bridge'`
- `ROLE_CONNECTION = 'connection'`
- `MANAGED_BY = 'mcw_lan_hosting'`
- `LEGACY_LAN_WORLD_PNP = LanHostingComponent(role=ROLE_AUTH_BRIDGE, project_slug='mcwifipnp', title='LAN World Plug-n-Play')`
- `E4MC = LanHostingComponent(role=ROLE_CONNECTION, project_slug='e4mc', title='e4mc')`
- `SUPPORTED_LOADERS = ModLoaderManager.MODDED_LOADERS`

Methods:

```python
normalize_auth_mode(value: object) -> str
``` *(staticmethod)*

```python
normalize_connection_provider(value: object) -> str
``` *(staticmethod)*

```python
plan(instance: Instance, auth_mode: object, connection_provider: object) -> LanHostingPlan
``` *(staticmethod)*

```python
prepare(instance: Instance, auth_mode: object, connection_provider: object, reporter: ProgressReporter | None = None) -> LanHostingPrepareResult
``` *(staticmethod)*

```python
disable_legacy_auth_bridges(instance: Instance) -> tuple[str, ...]
``` *(staticmethod)*

### `mcw_core.api.language.language_manager`

Source re-export: `src.core.language.language_manager`

#### `LanguageInfo`

Fields / public attributes:

- `locale: str`
- `name: str`
- `path: Path`

#### `LanguageManager`

Public constants:

- `DEFAULT_LOCALE = 'en-US'`

Methods:

```python
current_locale() -> str
``` *(property)*

```python
language_dir() -> Path
``` *(property)*

```python
language_dirs() -> tuple[Path, ...]
``` *(property)*

```python
reload() -> list[LanguageInfo]
```

```python
available_languages() -> list[LanguageInfo]
```

```python
set_language(locale: str, notify: bool = True) -> bool
```

```python
resolve_key(key: str) -> str
```

```python
translate(key: str, default: str | None = None, **values: object) -> str
```

```python
has_key(key: str) -> bool
```

```python
missing_keys(locale: str | None = None) -> list[str]
```

```python
placeholder_mismatches(locale: str | None = None) -> dict[str, tuple[set[str], set[str]]]
```

```python
subscribe(listener: Callable[[str], None]) -> None
```

```python
unsubscribe(listener: Callable[[str], None]) -> None
```

#### `tr`

```python
tr(key: str, default: str | None = None, **values: object) -> str
```

### `mcw_core.api.minecraft.version_manifest_manager`

Source re-export: `src.core.minecraft.version_manifest_manager`

#### `VersionManifestManager`

Methods:

```python
get(*, force_refresh: bool = False) -> list[VersionManifest]
``` *(staticmethod)*

```python
latest_version(is_snapshot: bool = False, *, force_refresh: bool = False) -> str
``` *(staticmethod)*

### `mcw_core.api.mod.mod_compatibility_manager`

Source re-export: `src.core.mod.mod_compatibility_manager`

#### `ModCompatibilityManager`

Public constants:

- `SYSTEM_DEPENDENCY_IDS = {'minecraft', 'java', 'forge', 'neoforge', 'javafml', 'fml', 'fabric', 'fabricloader', 'quilt', 'quilt_loader', 'quiltloader'}`

Methods:

```python
scan(instance: Instance, mods: list[ModInfo] | None = None) -> ModHealthReport
``` *(staticmethod)*

### `mcw_core.api.mod.mod_manager`

Source re-export: `src.core.mod.mod_manager`

#### `ModManager`

Public constants:

- `DISABLED_SUFFIX = '.disabled'`
- `MAX_EMBEDDED_MOD_JARS = 64`
- `MAX_EMBEDDED_MOD_JAR_SIZE = 32 * 1024 * 1024`
- `MAX_EMBEDDED_MOD_DEPTH = 2`

Methods:

```python
mods_dir(instance: Instance) -> Path
``` *(staticmethod)*

```python
list_mods(instance: Instance) -> list[ModInfo]
``` *(staticmethod)*

```python
apply_verified_curseforge_identity(instance: Instance, mod: ModInfo, entry: dict) -> ModInfo
``` *(staticmethod)*

```python
add_mods(instance: Instance, source_paths: Iterable[Path], replace: bool = False, launch_lock_token: str | None = None, allow_unverified: bool = False, managed_source: bool = False) -> list[ModInfo]
``` *(staticmethod)*

```python
remove_mods(instance: Instance, paths: Iterable[Path]) -> None
``` *(staticmethod)*

```python
set_enabled(instance: Instance, paths: Iterable[Path], enabled: bool) -> list[ModInfo]
``` *(staticmethod)*

```python
read_mod(path: Path, preferred_loader: str = '', provider_version: str = '') -> ModInfo
``` *(staticmethod)*

```python
validate_mod_for_instance(instance: Instance, mod: ModInfo, allow_unverified: bool = False) -> None
``` *(staticmethod)*

```python
compatibility_warning(instance: Instance, mod: ModInfo) -> str
``` *(staticmethod)*

```python
ensure_modifiable(instance: Instance, launch_lock_token: str | None = None) -> None
``` *(staticmethod)*

### `mcw_core.api.mod.mod_provenance_registry`

Source re-export: `src.core.mod.mod_provenance_registry`

#### `ModProvenanceRegistry`

Unified source identity for installed and manifest-managed mod files.

Public constants:

- `SCHEMA_VERSION = 2`

Methods:

```python
empty() -> dict
``` *(staticmethod)*

```python
load(instance: Instance) -> dict
``` *(staticmethod)*

```python
save(instance: Instance, data: dict) -> None
``` *(staticmethod)*

```python
synchronize(instance: Instance) -> dict[str, dict]
``` *(staticmethod)*

```python
entries_by_file(instance: Instance, synchronize: bool = True) -> dict[str, dict]
``` *(staticmethod)*

```python
entry_for_file(instance: Instance, filename: str) -> dict | None
``` *(staticmethod)*

```python
record_many(instance: Instance, entries: list[dict] | tuple[dict, ...]) -> None
``` *(staticmethod)*

```python
remove_by_filenames(instance: Instance, filenames: list[str] | tuple[str, ...] | set[str]) -> tuple[str, ...]
``` *(staticmethod)*

### `mcw_core.api.modloader.fabric.fabric_meta_client`

Source re-export: `src.core.modloader.fabric.fabric_meta_client`

#### `FabricMetaClient`

Public constants:

- `BASE_URL = 'https://meta.fabricmc.net/v2'`
- `CATALOG_CACHE_SCHEMA = 1`
- `INSTALL_CACHE_SCHEMA = 1`
- `PROFILE_CACHE_SCHEMA = 1`
- `CATALOG_TTL_SECONDS = 6 * 60 * 60`

Methods:

```python
list_loader_versions(game_version: str, force_refresh: bool = False) -> list[FabricLoaderVersion]
``` *(staticmethod)*

```python
get_install_metadata(game_version: str, loader_version: str, force_refresh: bool = False) -> FabricInstallMetadata
``` *(staticmethod)*

```python
get_profile(game_version: str, loader_version: str, force_refresh: bool = False) -> dict
``` *(staticmethod)*

```python
clear_cached_install(game_version: str, loader_version: str) -> None
``` *(staticmethod)*

### `mcw_core.api.modloader.forge.compatibility_confirmation`

Source re-export: `src.core.modloader.forge.compatibility_confirmation`

#### `CompatibilityConfirmationRequired`

Raised when bypassable compatibility errors require user consent.

Bases: `RuntimeError`

### `mcw_core.api.modloader.forge.forge_metadata_client`

Source re-export: `src.core.modloader.forge.forge_metadata_client`

#### `ForgeMetadataClient`

Public constants:

- `MAVEN_ROOT = 'https://maven.minecraftforge.net/net/minecraftforge/forge'`
- `METADATA_URL = f'{MAVEN_ROOT}/maven-metadata.xml'`
- `CACHE_TTL_SECONDS = 6 * 60 * 60`

Methods:

```python
list_versions(game_version: str, force_refresh: bool = False) -> list[ForgeLoaderVersion]
``` *(staticmethod)*

```python
recommended_version(game_version: str) -> str
``` *(staticmethod)*

```python
installer_url(game_version: str, forge_version: str) -> str
``` *(staticmethod)*

```python
installer_sha1(game_version: str, forge_version: str) -> str
``` *(staticmethod)*

### `mcw_core.api.modloader.mod_loader_manager`

Source re-export: `src.core.modloader.mod_loader_manager`

#### `ModLoaderManager`

Public constants:

- `VANILLA = 'vanilla'`
- `FABRIC = 'fabric'`
- `FORGE = 'forge'`
- `NEOFORGE = 'neoforge'`
- `QUILT = 'quilt'`
- `AUTO = 'auto'`
- `MODDED_LOADERS = frozenset({FABRIC, FORGE, NEOFORGE, QUILT})`
- `FORGE_FAMILY = frozenset({FORGE, NEOFORGE})`

Methods:

```python
load(instance: Instance, reporter: ProgressReporter | None = None, preferred_java_path: str | None = None) -> Version
``` *(staticmethod)*

```python
prepare(version: Version, loader_name: str, loader_version: str, reporter: ProgressReporter | None = None, preferred_java_path: str | None = None) -> Version
``` *(staticmethod)*

```python
repair(instance: Instance, reporter: ProgressReporter | None = None, preferred_java_path: str | None = None) -> Version
``` *(staticmethod)*

```python
resolve(game_version: str, loader_name: str, loader_version: str = AUTO) -> tuple[str, str]
``` *(staticmethod)*

```python
normalize(mod_loader: object) -> tuple[str, str]
``` *(staticmethod)*

### `mcw_core.api.modloader.neoforge.neoforge_metadata_client`

Source re-export: `src.core.modloader.neoforge.neoforge_metadata_client`

#### `NeoForgeMetadataClient`

Public constants:

- `MAVEN_BASE = 'https://maven.neoforged.net/releases/net/neoforged'`
- `MODERN_ARTIFACT = 'neoforge'`
- `LEGACY_ARTIFACT = 'forge'`
- `MODERN_MAVEN_ROOT = f'{MAVEN_BASE}/{MODERN_ARTIFACT}'`
- `LEGACY_MAVEN_ROOT = f'{MAVEN_BASE}/{LEGACY_ARTIFACT}'`
- `MODERN_METADATA_URL = f'{MODERN_MAVEN_ROOT}/maven-metadata.xml'`
- `LEGACY_METADATA_URL = f'{LEGACY_MAVEN_ROOT}/maven-metadata.xml'`
- `CACHE_TTL_SECONDS = 6 * 60 * 60`

Methods:

```python
list_versions(game_version: str, force_refresh: bool = False) -> list[NeoForgeLoaderVersion]
``` *(staticmethod)*

```python
recommended_version(game_version: str) -> str
``` *(staticmethod)*

```python
coordinate(game_version: str, neoforge_version: str) -> tuple[str, str]
``` *(staticmethod)*

```python
installer_url(game_version: str, neoforge_version: str) -> str
``` *(staticmethod)*

```python
installer_sha1(game_version: str, neoforge_version: str) -> str
``` *(staticmethod)*

### `mcw_core.api.modloader.quilt.quilt_meta_client`

Source re-export: `src.core.modloader.quilt.quilt_meta_client`

#### `QuiltMetaClient`

Public constants:

- `BASE_URL = 'https://meta.quiltmc.org/v3'`
- `CATALOG_CACHE_SCHEMA = 2`
- `INSTALL_CACHE_SCHEMA = 1`
- `PROFILE_CACHE_SCHEMA = 1`
- `CATALOG_TTL_SECONDS = 6 * 60 * 60`

Methods:

```python
list_loader_versions(game_version: str, force_refresh: bool = False) -> list[QuiltLoaderVersion]
``` *(staticmethod)*

```python
version_sort_key(version: str) -> tuple
``` *(staticmethod)*

```python
get_install_metadata(game_version: str, loader_version: str, force_refresh: bool = False) -> QuiltInstallMetadata
``` *(staticmethod)*

```python
get_profile(game_version: str, loader_version: str, force_refresh: bool = False) -> dict
``` *(staticmethod)*

```python
clear_cached_install(game_version: str, loader_version: str) -> None
``` *(staticmethod)*

### `mcw_core.api.modrinth.modrinth_client`

Source re-export: `src.core.modrinth.modrinth_client`

#### `ModrinthClient`

Public constants:

- `BASE_URL = 'https://api.modrinth.com/v2'`
- `CACHE_SCHEMA = 4`
- `SEARCH_TTL_SECONDS = 10 * 60`
- `VERSIONS_TTL_SECONDS = 30 * 60`
- `PROJECT_TTL_SECONDS = 60 * 60`
- `USER_AGENT = MODRINTH_USER_AGENT`

Methods:

```python
search_projects(project_type: str, query: str = '', game_version: str = '', loader: str = 'fabric', index: str = 'relevance', offset: int = 0, limit: int = 25, force_refresh: bool = False) -> ModrinthSearchResult
``` *(staticmethod)*

```python
get_project(project_id: str, force_refresh: bool = False) -> ModrinthProject
``` *(staticmethod)*

```python
list_project_versions(project_id: str, loader: str = 'fabric', game_version: str = '', version_types: tuple[str, ...] | list[str] | set[str] | None = None, force_refresh: bool = False) -> list[ModrinthVersion]
``` *(staticmethod)*

```python
get_version(version_id: str, force_refresh: bool = False) -> ModrinthVersion
``` *(staticmethod)*

```python
get_version_from_hash(file_hash: str, algorithm: str = 'sha512', force_refresh: bool = False) -> ModrinthVersion | None
``` *(staticmethod)*

```python
select_version(project_id: str, game_version: str, loader: str = 'fabric', version_types: tuple[str, ...] | list[str] | set[str] | None = None) -> ModrinthVersion
``` *(staticmethod)*

```python
compatible_loaders(loader: str) -> tuple[str, ...]
``` *(staticmethod)*

```python
normalize_version_types(version_types: tuple[str, ...] | list[str] | set[str] | None = None) -> tuple[str, ...]
``` *(staticmethod)*

### `mcw_core.api.modrinth.modrinth_errors`

Source re-export: `src.core.modrinth.modrinth_errors`

#### `ModrinthManagedFilesRequired`

Bases: `RuntimeError`

#### `ModrinthModpackManualDownloadRequired`

Bases: `RuntimeError`

### `mcw_core.api.modrinth.modrinth_manual_installer`

Source re-export: `src.core.modrinth.modrinth_manual_installer`

#### `ModrinthManualInstaller`

Methods:

```python
install(instance: Instance, requirement: ModrinthManualDownload, source: Path, launch_lock_token: str | None = None) -> str
``` *(staticmethod)*

```python
install_many(instance: Instance, requirements: tuple[ModrinthManualDownload, ...] | list[ModrinthManualDownload], sources: tuple[Path, ...] | list[Path], launch_lock_token: str | None = None) -> ModrinthManualImportResult
``` *(staticmethod)*

### `mcw_core.api.modrinth.modrinth_mod_installer`

Source re-export: `src.core.modrinth.modrinth_mod_installer`

#### `ModrinthModInstaller`

Public constants:

- `MAX_DEPENDENCIES = 64`
- `SUPPORTED_LOADERS = ModLoaderManager.MODDED_LOADERS`

Methods:

```python
install(instance: Instance, version_id: str, install_dependencies: bool = True, allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None) -> ModrinthModInstallResult
``` *(staticmethod)*

### `mcw_core.api.modrinth.modrinth_mod_update_manager`

Source re-export: `src.core.modrinth.modrinth_mod_update_manager`

#### `ModrinthModUpdateManager`

Methods:

```python
check(instance: Instance, allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, force_refresh: bool = False, reporter: ProgressReporter | None = None) -> ModrinthModUpdateReport
``` *(staticmethod)*

```python
update(instance: Instance, project_ids: list[str] | tuple[str, ...] | set[str], allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None) -> ModrinthModUpdateResult
``` *(staticmethod)*

```python
update_all(instance: Instance, allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None) -> ModrinthModUpdateResult
``` *(staticmethod)*

```python
set_locked(instance: Instance, project_ids: list[str] | tuple[str, ...] | set[str], locked: bool) -> tuple[str, ...]
``` *(staticmethod)*

### `mcw_core.api.modrinth.modrinth_pack_installer`

Source re-export: `src.core.modrinth.modrinth_pack_installer`

#### `ModrinthPackInstaller`

Public constants:

- `INDEX_NAME = 'modrinth.index.json'`
- `FORMAT_VERSION = 1`
- `MAX_WORKERS = 8`
- `MAX_INDEX_BYTES = 8 * 1024 * 1024`
- `MAX_FILES = 20000`
- `MAX_TOTAL_DOWNLOAD_BYTES = 50 * 1024 * 1024 * 1024`
- `MAX_OVERRIDE_BYTES = 2 * 1024 * 1024 * 1024`
- `MAX_PATH_LENGTH = 240`
- `RESERVED_ROOT_NAMES = {'instance.json', 'settings.json', '.mcw'}`
- `INSTANCE_NAME_PATTERN = re.compile('^[^<>:"/\\\\|?*\\x00-\\x1F]{1,80}$')`

Methods:

```python
install(project_id: str, version_id: str, instance_name: str, install_optional_files: bool = True, allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None, expected_loader: str = '', settings_override: dict | None = None) -> ModrinthModpackInstallResult
``` *(staticmethod)*

```python
install_local_archive(pack_path: Path, instance_name: str = '', install_optional_files: bool = True, reporter: ProgressReporter | None = None, settings_override: dict | None = None) -> ModrinthModpackInstallResult
``` *(staticmethod)*

```python
install_manual_archive(request: ModrinthModpackManualDownloadRequired, source: Path, reporter: ProgressReporter | None = None) -> ModrinthModpackInstallResult
``` *(staticmethod)*

```python
inspect(pack_path: Path) -> dict
``` *(staticmethod)*

### `mcw_core.api.modrinth.modrinth_pack_registry`

Source re-export: `src.core.modrinth.modrinth_pack_registry`

#### `ModrinthPackRegistry`

Public constants:

- `SCHEMA_VERSION = 6`
- `FILE_NAME = 'modrinth-pack.json'`

Methods:

```python
path(instance_dir: Path) -> Path
``` *(staticmethod)*

```python
load(instance: Instance) -> dict
``` *(staticmethod)*

```python
load_from_dir(instance_dir: Path) -> dict
``` *(staticmethod)*

```python
save(instance_dir: Path, data: dict) -> None
``` *(staticmethod)*

```python
scan(instance: Instance, reporter: ProgressReporter | None = None, force_hash: bool = False) -> ModrinthPackStateReport
``` *(staticmethod)*

```python
verify_entry(instance_dir: Path, entry: dict, cache: dict | None = None, force_hash: bool = False) -> tuple[bool, bool, int]
``` *(staticmethod)*

```python
build_verification_cache(instance_dir: Path, managed_files: list[dict]) -> dict
``` *(staticmethod)*

### `mcw_core.api.modrinth.modrinth_pack_repair_manager`

Source re-export: `src.core.modrinth.modrinth_pack_repair_manager`

#### `ModrinthPackRepairManager`

Methods:

```python
repair(instance: Instance, reporter: ProgressReporter | None = None) -> ModrinthPackRepairResult
``` *(staticmethod)*

### `mcw_core.api.modrinth.modrinth_pack_update_manager`

Source re-export: `src.core.modrinth.modrinth_pack_update_manager`

#### `ModrinthPackUpdateManager`

Methods:

```python
check(instance: Instance, allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, force_refresh: bool = False, reporter: ProgressReporter | None = None) -> ModrinthPackUpdateInfo | None
``` *(staticmethod)*

```python
preview(instance: Instance, target_version_id: str = '', allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None) -> ModrinthPackUpdatePlan
``` *(staticmethod)*

```python
update(instance: Instance, target_version_id: str = '', allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None) -> ModrinthPackUpdateResult
``` *(staticmethod)*

### `mcw_core.api.modrinth.modrinth_registry`

Source re-export: `src.core.modrinth.modrinth_registry`

#### `ModrinthRegistry`

Public constants:

- `SCHEMA_VERSION = 2`

Methods:

```python
load(instance: Instance) -> dict
``` *(staticmethod)*

```python
empty() -> dict
``` *(staticmethod)*

```python
save(instance: Instance, data: dict) -> None
``` *(staticmethod)*

```python
set_locked(instance: Instance, project_ids: list[str] | tuple[str, ...] | set[str], locked: bool) -> tuple[str, ...]
``` *(staticmethod)*

```python
remove_by_filenames(instance: Instance, filenames: list[str] | tuple[str, ...] | set[str]) -> tuple[str, ...]
``` *(staticmethod)*

```python
entries_by_file(instance: Instance) -> dict[str, dict]
``` *(staticmethod)*

```python
safe_tracked_path(instance: Instance, filename: str) -> Path | None
``` *(staticmethod)*

### `mcw_core.api.network.connectivity_monitor`

Source re-export: `src.core.network.connectivity_monitor`

#### `ConnectivitySnapshot`

Fields / public attributes:

- `online: bool`
- `checked_at: float`
- `latency_ms: float`
- `detail: str = ''`

#### `ConnectivityMonitor`

Perform a bounded Internet reachability check without DNS lookups.

Public constants:

- `DEFAULT_TARGETS = (('1.1.1.1', 443), ('8.8.8.8', 443))`
- `DEFAULT_TIMEOUT_SECONDS = 0.6`
- `DEFAULT_MAX_AGE_SECONDS = 10.0`

Methods:

```python
snapshot() -> ConnectivitySnapshot | None
``` *(property)*

```python
probe(*, timeout: float = DEFAULT_TIMEOUT_SECONDS, force: bool = False, max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS) -> ConnectivitySnapshot
```

### `mcw_core.api.network.download_bandwidth_limiter`

Source re-export: `src.core.network.download_bandwidth_limiter`

#### `DownloadBandwidthLimiter`

Public constants:

- `BYTES_PER_MEGABYTE = 1024 * 1024`

Methods:

```python
limit_mbps() -> float
``` *(property)*

```python
is_enabled() -> bool
``` *(property)*

```python
configure_mbps(value: object) -> float
```

```python
throttle(byte_count: int) -> None
```

### `mcw_core.api.network.download_manager`

Source re-export: `src.core.network.download_manager`

#### `DownloadManager`

Methods:

```python
max_concurrent_downloads() -> int
``` *(property)*

```python
recommended_concurrency(mode: object = 'automatic', configured: object = 0, *, game_running: bool = False, cores: int | None = None) -> int
``` *(staticmethod)*

```python
per_host_limit() -> int
``` *(property)*

```python
configure(max_concurrent_downloads: object = DEFAULT_MAX_CONCURRENT_DOWNLOADS, per_host_limit: object | None = None) -> tuple[int, int]
```

```python
get_path_lock(path: Path) -> RLock
```

```python
download(request: DownloadRequest, reporter: ProgressReporter | None = None, progress_stage: ProgressStage | None = None, progress_message: str | None = None, client_provider = None) -> DownloadResult
```

```python
download_and_hash(url: str, path: Path, max_attempts: int = 2, timeout: float = 20.0, force: bool = False, reporter: ProgressReporter | None = None, progress_stage: ProgressStage | None = None, progress_message: str | None = None, client_provider = None) -> tuple[Path, str, int]
```

```python
verify(path: Path, expected_size: int, hashes: dict | object) -> bool
```

```python
calculate_hash(path: Path, algorithm: str, allow_while_paused: bool = False) -> str
```

```python
calculate_hashes(path: Path, expected: dict | object, allow_while_paused: bool = False) -> dict[str, str]
```

```python
content_length(response: httpx.Response, fallback: int) -> int
``` *(staticmethod)*

```python
parse_content_range(response: httpx.Response) -> tuple[int, int, int | None] | None
``` *(staticmethod)*

```python
valid_content_range(response: httpx.Response, expected_start: int, expected_size: int) -> bool
``` *(classmethod)*

```python
content_range_total(response: httpx.Response) -> int
``` *(classmethod)*

```python
partial_size(path: Path, expected_size: int) -> int
``` *(classmethod)*

```python
delete_file(path: Path) -> None
``` *(staticmethod)*

```python
describe_error(error: Exception | None) -> str
``` *(staticmethod)*

### `mcw_core.api.network.download_pause`

Source re-export: `src.core.network.download_pause`

#### `DownloadInterruptedError`

Base class for cooperative download interruption requests.

Bases: `RuntimeError`

#### `DownloadPausedError`

Legacy terminal pause error kept for compatibility with older callers.

Bases: `DownloadInterruptedError`

#### `DownloadCancelledError`

Raised when the user cancels the active launcher download session.

Bases: `DownloadPausedError`

#### `DownloadPauseController`

Methods:

```python
is_active() -> bool
``` *(property)*

```python
is_pause_requested() -> bool
``` *(property)*

```python
is_paused() -> bool
``` *(property)*

```python
is_cancel_requested() -> bool
``` *(property)*

```python
begin() -> None
```

```python
finish() -> None
```

```python
request_pause() -> bool
```

```python
request_resume() -> bool
```

```python
request_cancel() -> bool
```

```python
raise_if_requested() -> None
```

```python
raise_if_cancel_requested() -> None
```

```python
wait(seconds: float) -> None
```

#### `is_download_paused`

```python
is_download_paused(error: BaseException | None) -> bool
```

#### `is_download_cancelled`

```python
is_download_cancelled(error: BaseException | None) -> bool
```

### `mcw_core.api.network.network_session`

Source re-export: `src.core.network.network_session`

#### `NetworkSession`

Methods:

```python
max_concurrent_downloads() -> int
``` *(property)*

```python
configure(max_concurrent_downloads: object = DEFAULT_MAX_CONCURRENT_DOWNLOADS) -> int
```

```python
get_client() -> httpx.Client
```

```python
close() -> None
```

### `mcw_core.api.package.portable_content_manager`

Source re-export: `src.core.package.portable_content_manager`

#### `PortableManualDownloadRequired`

Bases: `RuntimeError`

#### `PortableContentManager`

Public constants:

- `FILE_NAME = 'manual-files.json'`
- `REFERENCED_FILE_NAME = 'portable-referenced-files.json'`
- `DISABLED_FILE_NAME = 'portable-disabled-files.json'`
- `COPY_CHUNK_SIZE = 1024 * 1024`

Methods:

```python
ensure(instance: Instance) -> None
``` *(staticmethod)*

```python
prefetch_referenced(instance: Instance, reporter: ProgressReporter | None = None) -> None
``` *(staticmethod)*

```python
finalize_disabled(instance: Instance) -> None
``` *(staticmethod)*

```python
install_many(instance: Instance, requirements: tuple[PortableManualDownload, ...] | list[PortableManualDownload], sources: tuple[Path, ...] | list[Path]) -> tuple[str, ...]
``` *(staticmethod)*

### `mcw_core.api.progress.progress_reporter`

Source re-export: `src.core.progress.progress_reporter`

#### `ProgressReporter`

Methods:

```python
report(stage: ProgressStage, message: str, current: int | None = None, total: int | None = None, unit: ProgressUnit = ProgressUnit.NONE, bytes_per_second: float | None = None, state: ProgressState = ProgressState.RUNNING, detail: str = '') -> None
```

```python
status(stage: ProgressStage, message: str) -> None
```

```python
bytes(stage: ProgressStage, message: str, current: int, total: int, bytes_per_second: float | None = None) -> None
```

```python
files(stage: ProgressStage, message: str, current: int, total: int, bytes_per_second: float | None = None) -> None
```

```python
steps(stage: ProgressStage, message: str, current: int, total: int) -> None
```

```python
succeeded(stage: ProgressStage, message: str, detail: str = '') -> None
```

```python
failed(stage: ProgressStage, message: str, detail: str = '') -> None
```

```python
cancelled(stage: ProgressStage, message: str, detail: str = '') -> None
```

```python
task(stage: ProgressStage, start_message: str, success_message: str, failure_message: str) -> Iterator[None]
```

### `mcw_core.api.repair.repair_service`

Source re-export: `src.core.repair.repair_service`

#### `RepairService`

Public constants:

- `REPORT_SCHEMA_VERSION = 1`
- `DEFAULT_COMPONENTS = tuple(RepairComponent)`
- `INSTANCE_SCOPED_COMPONENTS = frozenset({RepairComponent.MOD_LOADER, RepairComponent.MODPACK, RepairComponent.SETTINGS})`

Methods:

```python
scan(instance: Instance, mode: RepairMode | str = RepairMode.QUICK, components: Iterable[RepairComponent | str] | None = None, on_progress: ProgressCallback | None = None) -> RepairReport
``` *(classmethod)*

```python
build_plan(report: RepairReport, components: Iterable[RepairComponent | str] | None = None) -> RepairPlan
``` *(classmethod)*

```python
repair(instance: Instance, plan: RepairPlan, on_progress: ProgressCallback | None = None) -> RepairExecutionResult
``` *(classmethod)*

### `mcw_core.api.runtime.game_runtime_manager`

Source re-export: `src.core.runtime.game_runtime_manager`

#### `GameRuntimeManager`

Public constants:

- `HISTORY_SCHEMA_VERSION = 1`
- `HISTORY_LIMIT = 50`
- `POLL_INTERVAL_SECONDS = 0.5`

Methods:

```python
watch(process: object, instance: Instance, minecraft_version: str, started_at: datetime, on_exit: GameExitCallback | None = None, session_id: str | None = None, crash_report_snapshot: Mapping[str, tuple[int, int]] | None = None) -> bool
``` *(classmethod)*

```python
stop(instance: Instance, graceful_timeout: float = 2.5) -> bool
``` *(classmethod)*

```python
kill(instance: Instance, timeout: float = 1.5) -> bool
``` *(classmethod)*

```python
wait_for_exit_processing(instance: Instance, timeout: float = 3.0) -> bool
``` *(classmethod)*

```python
latest_game_log(instance: Instance) -> Path | None
``` *(staticmethod)*

```python
crash_report_snapshot(instance: Instance) -> dict[str, tuple[int, int]]
``` *(staticmethod)*

```python
latest_crash_report(instance: Instance, since: datetime | None = None, previous: Mapping[str, tuple[int, int]] | None = None) -> Path | None
``` *(staticmethod)*

```python
record_start(instance: Instance, started_at: datetime, session_id: str | None) -> None
``` *(classmethod)*

### `mcw_core.api.runtime.process_supervisor`

Source re-export: `src.core.runtime.process_supervisor`

#### `ProcessSupervisor`

Persist and supervise Minecraft process sessions without touching unrelated Java processes.

Public constants:

- `SCHEMA_VERSION = 1`
- `HISTORY_LIMIT = 100`

Methods:

```python
begin(instance: Instance) -> ProcessSession
``` *(classmethod)*

```python
attach(session_id: str, process: object) -> ProcessSession
``` *(classmethod)*

```python
register_child(session_id: str, pid: int) -> ProcessSession
``` *(classmethod)*

```python
finish(session_id: str, exit_code: int, crashed: bool, detail: str = '') -> ProcessSession | None
``` *(classmethod)*

```python
abort(session_id: str, detail: str = '') -> ProcessSession | None
``` *(classmethod)*

```python
stop_requested(session_id: str | None) -> bool
``` *(classmethod)*

```python
kill_requested(session_id: str | None) -> bool
``` *(classmethod)*

```python
active_for(instance: Instance) -> ProcessSession | None
``` *(classmethod)*

```python
list_active() -> tuple[ProcessSession, ...]
``` *(classmethod)*

```python
stop_process(process: object, graceful_timeout: float = 2.5) -> bool
``` *(classmethod)*

```python
stop_instance(instance: Instance, graceful_timeout: float = 2.5) -> bool
``` *(classmethod)*

```python
kill_instance(instance: Instance, timeout: float = 1.5) -> bool
``` *(classmethod)*

```python
reconcile() -> tuple[str, ...]
``` *(classmethod)*

```python
load(session_id: str) -> ProcessSession
``` *(classmethod)*

### `mcw_core.api.runtime.startup_recovery_manager`

Source re-export: `src.core.runtime.startup_recovery_manager`

#### `StartupRecoveryReport`

Fields / public attributes:

- `deleted_instances: tuple[str, ...]`
- `stale_locks: tuple[str, ...]`
- `interrupted_sessions: tuple[str, ...]`
- `operations: tuple[InstanceRecoveryRecord, ...]`
- `orphan_staging_paths: tuple[str, ...]`
- `orphan_partial_paths: tuple[str, ...]`
- `download_journal_entries_cleaned: int = 0`

Methods:

```python
recovered_item_count() -> int
``` *(property)*

#### `StartupRecoveryManager`

Methods:

```python
reconcile() -> StartupRecoveryReport
``` *(staticmethod)*

### `mcw_core.api.security.account_security_manager`

Source re-export: `src.core.security.account_security_manager`

#### `AccountSecurityManager`

Methods:

```python
audit() -> AccountSecurityReport
``` *(classmethod)*

```python
migrate_if_needed() -> AccountSecurityReport
``` *(classmethod)*

```python
migrate_and_reprotect() -> AccountSecurityReport
``` *(classmethod)*

### `mcw_core.api.security.sensitive_data_redactor`

Source re-export: `src.core.security.sensitive_data_redactor`

#### `SensitiveDataRedactor`

Public constants:

- `REDACTED = '<redacted>'`

Methods:

```python
redact_text(value: object) -> str
``` *(classmethod)*

```python
redact_value(value: Any, key: str = '') -> Any
``` *(classmethod)*

```python
redact_json(value: Any) -> str
``` *(classmethod)*

### `mcw_core.api.startup_runner`

Source re-export: `src.core.startup_runner`

#### `StartupTimeoutError`

Bases: `RuntimeError`

#### `StartupWorkerError`

Bases: `RuntimeError`

#### `run_startup_task`

```python
run_startup_task(task: StartupTask, on_progress: StartupProgressHandler, pump_events: EventPump, timeout_seconds: float = 45.0) -> Any
```

### `mcw_core.api.storage.content_store`

Source re-export: `src.core.storage.content_store`

#### `MaterializationResult`

Fields / public attributes:

- `path: Path`
- `canonical_path: Path`
- `sha256: str`
- `size_bytes: int`
- `hardlinked: bool`

#### `ContentStore`

Content-addressed store for immutable downloaded provider artifacts.

Public constants:

- `HASH_CHUNK_SIZE = 1024 * 1024`

Methods:

```python
sha256(path: Path) -> str
``` *(staticmethod)*

```python
adopt(source: Path) -> MaterializationResult
``` *(classmethod)*

```python
materialize(source: Path, destination: Path, *, adopt_source: bool = True, prefer_hardlink: bool = True) -> MaterializationResult
``` *(classmethod)*

### `mcw_core.api.storage.legacy_storage_migration_service`

Source re-export: `src.core.storage.legacy_storage_migration_service`

#### `CleanupCandidate`

Fields / public attributes:

- `candidate_id: str`
- `path: Path`
- `category: str`
- `reason: str`
- `safety: str`
- `size_bytes: int`
- `file_count: int`
- `directory_count: int`
- `reference_status: str = 'unreferenced'`
- `reclaimable_bytes: int = -1`

Methods:

```python
effective_reclaimable_bytes() -> int
``` *(property)*

#### `CleanupPlan`

Fields / public attributes:

- `candidates: tuple[CleanupCandidate, ...]`

Methods:

```python
total_bytes() -> int
``` *(property)*

```python
file_count() -> int
``` *(property)*

```python
directory_count() -> int
``` *(property)*

```python
by_category() -> dict[str, int]
```

#### `CleanupResult`

Fields / public attributes:

- `reclaimed_bytes: int`
- `removed: tuple[CleanupCandidate, ...]`
- `skipped: tuple[CleanupCandidate, ...]`
- `failures: tuple[tuple[CleanupCandidate, str], ...]`

#### `LegacyCleanupProbe`

Fields / public attributes:

- `candidate_count: int`
- `estimated_bytes: int`

Methods:

```python
has_candidates() -> bool
``` *(property)*

#### `LegacyStorageMigrationService`

Reference-aware migration/cleanup for storage left by pre-v1.3 builds.

Public constants:

- `SAFE = 'safe'`
- `REVIEWED = 'reviewed'`
- `STALE_TEMP_SECONDS = 7 * 24 * 60 * 60`
- `LOADER_STAGING_GRACE_SECONDS = 60 * 60`
- `DEFAULT_UNUSED_VERSION_RETENTION_DAYS = 14`
- `MIN_UNUSED_VERSION_RETENTION_DAYS = 1`
- `MAX_UNUSED_VERSION_RETENTION_DAYS = 365`
- `UNUSED_VERSION_RETENTION_SECONDS = DEFAULT_UNUSED_VERSION_RETENTION_DAYS * 24 * 60 * 60`
- `UNREFERENCED_CONTENT_RETENTION_SECONDS = 14 * 24 * 60 * 60`

Methods:

```python
probe(*, now: float | None = None, unused_version_retention_days: int | None = None) -> LegacyCleanupProbe
``` *(classmethod)*

```python
scan(*, now: float | None = None, unused_version_retention_days: int | None = None) -> CleanupPlan
``` *(classmethod)*

```python
apply(plan: CleanupPlan, candidate_ids: Iterable[str] | None = None, *, unused_version_retention_days: int | None = None) -> CleanupResult
``` *(classmethod)*

```python
normalize_unused_version_retention_days(value: int | None) -> int
``` *(classmethod)*

### `mcw_core.api.storage.platform_storage_migration`

Source re-export: `src.core.storage.platform_storage_migration`

#### `PlatformStorageMigrationReport`

Fields / public attributes:

- `copied_files: int = 0`
- `copied_bytes: int = 0`
- `skipped_files: int = 0`
- `conflicts: tuple[str, ...] = ()`
- `errors: tuple[str, ...] = ()`
- `already_completed: bool = False`

Methods:

```python
completed() -> bool
``` *(property)*

#### `PlatformStorageMigration`

Copy Alpha 2's portable Linux data into XDG roots without deleting it.

Public constants:

- `SCHEMA_VERSION = 1`
- `MARKER_NAME = '.platform-storage-migration-v1.json'`

Methods:

```python
migrate(legacy_root: Path | str | None = None) -> PlatformStorageMigrationReport
``` *(classmethod)*

### `mcw_core.api.system.memory`

Source re-export: `src.core.system.memory`

#### `SystemMemory`

Public constants:

- `BYTES_PER_MB = 1024 * 1024`

Methods:

```python
total_physical_memory_mb() -> int
``` *(classmethod)*

```python
available_physical_memory_mb() -> int
``` *(classmethod)*

#### `MemoryAllocationPolicy`

Public constants:

- `MIN_MEMORY_MB = 256`
- `DEFAULT_MIN_MEMORY_MB = 1024`
- `DEFAULT_MAX_MEMORY_MB = 2048`
- `SLIDER_STEP_MB = 256`
- `FALLBACK_PHYSICAL_LIMIT_MB = 4096`

Methods:

```python
physical_limit_mb(total_memory_mb: int | None = None) -> int
``` *(classmethod)*

```python
normalize(min_memory_mb: object, max_memory_mb: object, total_memory_mb: int | None = None) -> tuple[int, int]
``` *(classmethod)*

```python
is_valid(min_memory_mb: object, max_memory_mb: object, total_memory_mb: int | None = None) -> bool
``` *(classmethod)*

```python
snap_mb(memory_mb: object, upper_bound_mb: int) -> int
``` *(classmethod)*

```python
format_mb(memory_mb: int) -> str
``` *(staticmethod)*

### `mcw_core.api.theme.theme_animation`

Source re-export: `src.core.theme.theme_animation`

#### `ThemeAnimationDefinition`

Fields / public attributes:

- `key: str`
- `path: str`
- `frame_width: int`
- `frame_height: int`
- `frame_count: int`
- `columns: int`
- `frame_duration_ms: int`
- `loop: bool = True`
- `render_mode: str = 'tile_x'`
- `filtering: str = 'nearest'`
- `fallback_asset: str | None = None`

Methods:

```python
rows() -> int
``` *(property)*

#### `ResolvedThemeAnimation`

Fields / public attributes:

- `definition: ThemeAnimationDefinition`
- `path: Path`
- `theme_id: str`

Methods:

```python
key() -> str
``` *(property)*

### `mcw_core.api.theme.theme_authoring`

Source re-export: `src.core.theme.theme_authoring`

#### `ThemeAuthoringError`

Bases: `RuntimeError`

#### `ThemeAuthoringService`

Public constants:

- `THEME_ID_PATTERN = THEME_ID_PATTERN`
- `MAX_ARCHIVE_FILES = MAX_THEME_ARCHIVE_FILES`
- `MAX_ARCHIVE_BYTES = MAX_THEME_ARCHIVE_BYTES`
- `ALLOWED_EXTENSIONS = frozenset({'.json', '.png', '.ttf', '.otf', '.qss', '.md', '.txt', '.license'})`
- `ALLOWED_EXTENSIONLESS_NAMES = frozenset({'license', 'copying', 'notice'})`
- `EXCLUDED_NAMES = frozenset({'__pycache__', '.git', '.svn', '.hg'})`

Methods:

```python
validate(theme_id: str) -> ThemeValidationReport
```

```python
validate_directory(root: Path) -> ThemeValidationReport
```

```python
duplicate(theme_id: str, new_id: str, new_name: str | None = None) -> ThemeDefinition
```

```python
export(theme_id: str, destination: Path) -> Path
```

```python
import_archive(archive_path: Path, overwrite: bool = False) -> ThemeDefinition
```

### `mcw_core.api.theme.theme_font`

Source re-export: `src.core.theme.theme_font`

#### `ThemeFontDefinition`

Fields / public attributes:

- `paths: tuple[str, ...]`
- `family: str | None = None`
- `point_size: float = 10.5`
- `weight: int = 400`
- `italic: bool = False`
- `letter_spacing: float = 0.0`
- `fallback_families: tuple[str, ...] = ()`

#### `ResolvedThemeFont`

Fields / public attributes:

- `definition: ThemeFontDefinition`
- `paths: tuple[Path, ...]`
- `theme_id: str`

### `mcw_core.api.theme.theme_manager`

Source re-export: `src.core.theme.theme_manager`

#### `ThemeError`

Bases: `RuntimeError`

#### `ThemeManifestError`

Bases: `ThemeError`

#### `ThemeAssetError`

Bases: `ThemeError`

#### `ThemeDefinition`

Fields / public attributes:

- `theme_id: str`
- `name: str`
- `author: str`
- `root: Path | None`
- `schema_version: int = 1`
- `assets: dict[str, str] = field(default_factory=dict)`
- `text_assets: dict[str, str] = field(default_factory=dict)`
- `animations: dict[str, ThemeAnimationDefinition] = field(default_factory=dict)`
- `font: ThemeFontDefinition | None = None`
- `motion: ThemeMotionDefinition = field(default_factory=ThemeMotionDefinition)`
- `palette: ThemePaletteDefinition = field(default_factory=ThemePaletteDefinition)`
- `accent_assets: frozenset[str] = frozenset()`
- `stylesheet: str | None = None`
- `capabilities: frozenset[str] = frozenset()`
- `issues: tuple[str, ...] = ()`
- `builtin_fallback: bool = False`

#### `ThemeManager`

Public constants:

- `DEFAULT_THEME_ID = 'mcw-default'`
- `FALLBACK_THEME_ID = 'builtin-css'`
- `MANIFEST_NAME = 'theme.json'`
- `LATEST_SCHEMA_VERSION = THEME_SCHEMA_VERSION`
- `MAX_MANIFEST_BYTES = MAX_MANIFEST_BYTES`
- `MAX_STYLESHEET_BYTES = MAX_STYLESHEET_BYTES`
- `SUPPORTED_SCHEMA_VERSIONS = SUPPORTED_THEME_SCHEMA_VERSIONS`
- `MAX_ANIMATION_FRAMES = MAX_ANIMATION_FRAMES`
- `MIN_FRAME_DURATION_MS = MIN_FRAME_DURATION_MS`
- `MAX_FRAME_DURATION_MS = MAX_FRAME_DURATION_MS`
- `ANIMATION_KEY_PATTERN = ANIMATION_KEY_PATTERN`
- `ANIMATION_RENDER_MODES = ANIMATION_RENDER_MODES`
- `ANIMATION_FILTERING_MODES = ANIMATION_FILTERING_MODES`
- `FONT_EXTENSIONS = FONT_EXTENSIONS`
- `FONT_WEIGHTS = FONT_WEIGHTS`
- `MAX_FONT_FILES = MAX_FONT_FILES`
- `MAX_FONT_FILE_BYTES = MAX_FONT_FILE_BYTES`
- `MAX_FONT_TOTAL_BYTES = MAX_FONT_TOTAL_BYTES`
- `MOTION_EASINGS = MOTION_EASINGS`
- `PAGE_TRANSITIONS = PAGE_TRANSITIONS`
- `DIALOG_TRANSITIONS = DIALOG_TRANSITIONS`
- `LAUNCH_TRANSITIONS = LAUNCH_TRANSITIONS`
- `TOAST_TRANSITIONS = TOAST_TRANSITIONS`
- `SCHEMA_V6_FIELDS = frozenset({'$schema', 'schema_version', 'id', 'name', 'author', 'description', 'assets', 'text_assets', 'animations', 'font', 'motion', 'palette', 'accent_assets', 'stylesheet', 'capabilities'})`

Methods:

```python
current() -> ThemeDefinition
``` *(property)*

```python
reload() -> tuple[ThemeDefinition, ...]
```

```python
available_themes() -> tuple[ThemeDefinition, ...]
```

```python
select(theme_id: str) -> ThemeDefinition
```

```python
resolve_asset(key: str, theme: ThemeDefinition | None = None, fallback_to_default: bool = False) -> Path | None
```

```python
resolve_text_asset(role: str, theme: ThemeDefinition | None = None, fallback_to_default: bool = False) -> Path | None
```

```python
resolve_animation(key: str, theme: ThemeDefinition | None = None, fallback_to_default: bool = True) -> ResolvedThemeAnimation | None
```

```python
resolve_animation_fallback(key: str, theme: ThemeDefinition | None = None, fallback_to_default: bool = True) -> Path | None
```

```python
resolve_font(theme: ThemeDefinition | None = None, fallback_to_default: bool = True) -> ResolvedThemeFont | None
```

```python
resolve_palette(theme: ThemeDefinition | None = None) -> ThemePaletteDefinition
```

```python
is_accent_asset(key: str, theme: ThemeDefinition | None = None) -> bool
```

```python
resolve_stylesheet(theme: ThemeDefinition | None = None) -> str
```

```python
asset_status(theme: ThemeDefinition | None = None) -> dict[str, bool]
```

```python
animation_status(theme: ThemeDefinition | None = None) -> dict[str, bool]
```

```python
font_status(theme: ThemeDefinition | None = None) -> bool
```

### `mcw_core.api.theme.theme_motion`

Source re-export: `src.core.theme.theme_motion`

#### `MotionTransitionDefinition`

Fields / public attributes:

- `transition_type: str = 'fade'`
- `duration_ms: int = 160`
- `easing: str = 'out_cubic'`
- `distance_px: int = 20`

#### `ButtonMotionDefinition`

Fields / public attributes:

- `hover_duration_ms: int = 100`
- `press_duration_ms: int = 70`
- `easing: str = 'out_quad'`
- `hover_strength: float = 0.08`
- `press_strength: float = 0.18`

#### `SidebarMotionDefinition`

Fields / public attributes:

- `duration_ms: int = 220`
- `easing: str = 'out_cubic'`
- `collapsed_width: int = 72`

#### `ToastMotionDefinition`

Fields / public attributes:

- `transition_type: str = 'slide_fade'`
- `duration_ms: int = 180`
- `visible_duration_ms: int = 3000`
- `easing: str = 'out_cubic'`
- `distance_px: int = 24`
- `max_visible: int = 3`

#### `MotionPerformanceDefinition`

Fields / public attributes:

- `full_fps: int = 60`
- `reduced_fps: int = 30`
- `pause_when_hidden: bool = True`

#### `ThemeMotionDefinition`

Fields / public attributes:

- `page: MotionTransitionDefinition = field(default_factory=lambda: MotionTransitionDefinition('fade_slide', 170, 'out_cubic', 18))`
- `dialog: MotionTransitionDefinition = field(default_factory=lambda: MotionTransitionDefinition('fade', 160, 'out_cubic', 12))`
- `launch_control: MotionTransitionDefinition = field(default_factory=lambda: MotionTransitionDefinition('fade', 140, 'out_cubic', 8))`
- `button: ButtonMotionDefinition = field(default_factory=ButtonMotionDefinition)`
- `sidebar: SidebarMotionDefinition = field(default_factory=SidebarMotionDefinition)`
- `toast: ToastMotionDefinition = field(default_factory=ToastMotionDefinition)`
- `performance: MotionPerformanceDefinition = field(default_factory=MotionPerformanceDefinition)`

### `mcw_core.api.theme.theme_palette`

Source re-export: `src.core.theme.theme_palette`

#### `ThemePaletteDefinition`

Fields / public attributes:

- `primary: str = '#63984a'`
- `primary_hover: str = '#7db45e'`
- `primary_pressed: str = '#4d7938'`
- `primary_text: str = '#ffffff'`
- `focus: str = '#8ed35b'`
- `selection: str = '#4f6d3c'`
- `selection_text: str = '#ffffff'`
- `link: str = '#8ed35b'`
- `success: str = '#8ed35b'`
- `warning: str = '#d6a93c'`
- `error: str = '#c47a7a'`
- `text_primary: str = '#f4f4f4'`
- `text_muted: str = '#b8b8b8'`
- `text_disabled: str = '#777777'`
- `text_inverse: str = '#111111'`

Methods:

```python
to_dict() -> dict[str, str]
```

#### `normalize_hex_color`

```python
normalize_hex_color(value: object, label: str = 'color') -> str
```

#### `derive_custom_accent`

```python
derive_custom_accent(theme_palette: ThemePaletteDefinition, accent: str) -> ThemePaletteDefinition
```

#### `derive_custom_text`

```python
derive_custom_text(theme_palette: ThemePaletteDefinition, text_color: str) -> ThemePaletteDefinition
```

#### `contrast_ratio`

```python
contrast_ratio(foreground: str, background: str) -> float
```

#### `is_readable_text`

```python
is_readable_text(foreground: str, background: str, minimum_ratio: float = 3.0) -> bool
```

### `mcw_core.api.update.automatic_update_installer`

Source re-export: `src.core.update.automatic_update_installer`

#### `AutomaticUpdateInstaller`

Route installation to the packaged updater for the current platform.

Methods:

```python
is_supported() -> bool
``` *(classmethod)*

```python
launch(prepared: PreparedUpdate, install_directory: Path | None = None, executable_path: Path | None = None, parent_pid: int | None = None, persistent_log_path: Path | None = None) -> Path
``` *(classmethod)*

### `mcw_core.api.update.linux_update_installer`

Source re-export: `src.core.update.linux_update_installer`

#### `LinuxUpdateInstaller`

Start a detached copy of the packaged launcher to apply a Linux update.

Public constants:

- `STARTUP_GRACE_SECONDS = 1.0`

Methods:

```python
is_supported() -> bool
``` *(staticmethod)*

```python
launch(prepared: PreparedUpdate, install_directory: Path | None = None, executable_path: Path | None = None, parent_pid: int | None = None, persistent_log_path: Path | None = None) -> Path
``` *(classmethod)*

### `mcw_core.api.update.update_applier`

Source re-export: `src.core.update.update_applier`

#### `UpdateApplyRequest`

Fields / public attributes:

- `parent_pid: int`
- `source_directory: Path`
- `destination_directory: Path`
- `executable_name: str`
- `updater_directory: Path`
- `staging_directory: Path`
- `persistent_log_path: Path`
- `target_version: str`

Methods:

```python
load(path: Path) -> 'UpdateApplyRequest'
``` *(classmethod)*

```python
validate() -> None
```

#### `UpdateApplier`

Public constants:

- `COPY_RETRIES = 30`
- `COPY_RETRY_DELAY_SECONDS = 0.25`

Methods:

```python
run() -> int
```

#### `run_update_applier`

```python
run_update_applier(request_path: Path) -> int
```

### `mcw_core.api.update.update_cleanup`

Source re-export: `src.core.update.update_cleanup`

#### `UpdateCleanupRequest`

Fields / public attributes:

- `updater_directory: Path`
- `updater_pid: int`

Methods:

```python
validate() -> None
```

#### `UpdateCleanupWorker`

Public constants:

- `DELETE_RETRIES = 40`
- `DELETE_RETRY_DELAY_SECONDS = 0.25`

Methods:

```python
start() -> threading.Thread
```

```python
run() -> None
```

#### `consume_update_cleanup_arguments`

```python
consume_update_cleanup_arguments(arguments: list[str]) -> tuple[list[str], UpdateCleanupRequest | None]
```

### `mcw_core.api.update.update_manager`

Source re-export: `src.core.update.update_manager`

#### `UpdateManager`

Public constants:

- `MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024`
- `MAX_EXTRACTED_BYTES = 4 * 1024 * 1024 * 1024`
- `MAX_ARCHIVE_ENTRIES = 20000`
- `PACKAGE_MANIFEST_NAME = 'mcw-update.json'`
- `PACKAGE_MANIFEST_SCHEMA_VERSION = 1`

Methods:

```python
check_for_update(force_refresh: bool = False) -> UpdateInfo | None
```

```python
prepare_update(info: UpdateInfo, reporter: ProgressReporter | None = None) -> PreparedUpdate
```

### `mcw_core.api.update.windows_update_installer`

Source re-export: `src.core.update.windows_update_installer`

#### `WindowsUpdateInstaller`

Public constants:

- `STARTUP_GRACE_SECONDS = 1.0`

Methods:

```python
is_supported() -> bool
``` *(staticmethod)*

```python
launch(prepared: PreparedUpdate, install_directory: Path | None = None, executable_path: Path | None = None, parent_pid: int | None = None, persistent_log_path: Path | None = None) -> Path
``` *(classmethod)*
