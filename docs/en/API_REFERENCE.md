# MCW Core v1.5.0 API Reference

This reference is generated directly from the MCW Core v1.5.0 public source. The supported public boundary is `mcw_core` and `mcw_core.api.*`.

> External consumers should not import `src.core.*` or `src.models.*` directly.

## Stable facade and models

### `mcw_core/facade.py`

#### `MCWCore`

Public, GUI-independent facade for MCW Launcher core operations.

Methods:

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
```
*(property)*

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

#### `InstanceService`

Methods:

#### `OptiFineService`

Public constants:

- `OFFICIAL_DOWNLOADS_URL = 'https://optifine.net/downloads'`

Methods:

#### `JavaService`

Methods:

## Granular `mcw_core.api.*` modules

### `mcw_core.api.account.account_manager`

Source re-export: `src.core.account.account_manager`

#### `AccountManager`

Methods:

### `mcw_core.api.account.account_skin_manager`

Source re-export: `src.core.account.account_skin_manager`

#### `AccountSkinManager`

Cache Minecraft skin textures without making the GUI depend on network APIs.

Public constants:

- `MAX_TEXTURE_BYTES = 4 * 1024 * 1024`
- `REQUEST_TIMEOUT_SECONDS = 20.0`
- `PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'`

Methods:

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

### `mcw_core.api.atlauncher.atlauncher_content_manager`

Source re-export: `src.core.atlauncher.atlauncher_content_manager`

#### `ATLauncherContentManager`

Materialize deferred ATLauncher pack files before the first launch.

Public constants:

- `PROGRESS_EMIT_INTERVAL_SECONDS = 0.08`
- `MAX_CONFIG_ENTRIES = 100000`
- `MAX_CONFIG_BYTES = 10 * 1024 * 1024 * 1024`

Methods:

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

### `mcw_core.api.atlauncher.atlauncher_pack_registry`

Source re-export: `src.core.atlauncher.atlauncher_pack_registry`

#### `ATLauncherPackRegistry`

Public constants:

- `SCHEMA_VERSION = 1`

Methods:

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

#### `ReusableOAuthHTTPServer`

Bases: `HTTPServer`

#### `OAuthCallbackServer`

Public constants:

- `HOST = '127.0.0.1'`
- `PORT = 8400`
- `POLL_INTERVAL_SECONDS = 0.25`

Methods:

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

### `mcw_core.api.config.launcher_settings_manager`

Source re-export: `src.core.config.launcher_settings_manager`

#### `LauncherSettingsManager`

Public constants:

- `SCHEMA_VERSION = 19`
- `UPDATE_CHANNEL_POLICY_VERSION = 2`
- `DEFAULT_SETTINGS = {'schema_version': SCHEMA_VERSION, 'gui': {'start_page': 'instances', 'show_snapshots': False, 'remember_window_size': True, 'language': 'en-US', 'show_content_descriptions': False}, 'launch': {'debug_mode': False, 'prefer_dedicated_gpu': False}, 'onboarding': {'completed': False, 'version': 1}, 'window': {'geometry': None}, 'appearance': {'theme': 'mcw-default', 'show_static_text': False, 'motion_mode': 'full', 'live_theme_reload': False, 'accent_mode': 'theme', 'accent_color': '#8ed35b', 'text_color_mode': 'theme', 'text_color': '#f4f4f4'}, 'modrinth': {'include_beta': False, 'include_alpha': False}, 'managed_content': {'modrinth_failure_policy': 'block', 'curseforge_failure_policy': 'block', 'forge_preflight_failure_policy': 'ask'}, 'network': {'download_limit_mbps': 0.0, 'download_concurrency': 0, 'download_performance_mode': 'automatic'}, 'storage': {'notify_legacy_cache_cleanup': True, 'unused_version_retention_days': 14}, 'instance_defaults': default_instance_settings(), 'updates': {'auto_check': True, 'channel': 'stable', 'channel_policy_version': UPDATE_CHANNEL_POLICY_VERSION, 'last_checked_at': None}}`

Methods:

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

### `mcw_core.api.content.content_pack_registry`

Source re-export: `src.core.content.content_pack_registry`

#### `ContentPackRegistry`

Public constants:

- `SCHEMA_VERSION = 1`
- `REGISTRY_RELATIVE_PATH = Path('.mcw') / 'content-packs.json'`

Methods:

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
```
*(property)*

```python
enabled_count() -> int
```
*(property)*

```python
pending_count() -> int
```
*(property)*

```python
missing_count() -> int
```
*(property)*

```python
managed_count() -> int
```
*(property)*

```python
total_size() -> int
```
*(property)*

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

### `mcw_core.api.curseforge.curseforge_mod_installer`

Source re-export: `src.core.curseforge.curseforge_mod_installer`

#### `CurseForgeModInstaller`

Public constants:

- `MAX_DEPENDENCIES = 64`

Methods:

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

### `mcw_core.api.curseforge.curseforge_registry`

Source re-export: `src.core.curseforge.curseforge_registry`

#### `CurseForgeRegistry`

Public constants:

- `SCHEMA_VERSION = 1`

Methods:

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

### `mcw_core.api.diagnostics.issue_report_builder`

Source re-export: `src.core.diagnostics.issue_report_builder`

#### `IssueReportBuilder`

Build a privacy-filtered GitHub issue draft from user-provided context.

Methods:

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

### `mcw_core.api.ftb.ftb_content_manager`

Source re-export: `src.core.ftb.ftb_content_manager`

#### `FTBContentManager`

Materialize deferred FTB modpack files immediately before launch.

Public constants:

- `PROGRESS_EMIT_INTERVAL_SECONDS = 0.08`

Methods:

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

### `mcw_core.api.ftb.ftb_pack_registry`

Source re-export: `src.core.ftb.ftb_pack_registry`

#### `FTBPackRegistry`

Public constants:

- `SCHEMA_VERSION = 2`

Methods:

### `mcw_core.api.hardware.first_run_recommendation_service`

Source re-export: `src.core.hardware.first_run_recommendation_service`

#### `FirstRunRecommendationService`

Collect safe first-run defaults without depending on the GUI.

Methods:

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
```
*(property)*

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
```
*(property)*

```python
has_dedicated_gpu() -> bool
```
*(property)*

#### `GpuPreferenceManager`

Best-effort Windows graphics preference integration.

Public constants:

- `REGISTRY_PATH = 'Software\\Microsoft\\DirectX\\UserGpuPreferences'`
- `HIGH_PERFORMANCE_VALUE = 'GpuPreference=2;'`
- `DETECTION_TIMEOUT_SECONDS = 8`

Methods:

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

### `mcw_core.api.java.java_major_policy`

Source re-export: `src.core.java.java_major_policy`

#### `JavaMajorPolicy`

Public constants:

- `SUPPORTED_MAJORS = (8, 17, 21, 25)`

Methods:

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
```
*(property)*

```python
language_dir() -> Path
```
*(property)*

```python
language_dirs() -> tuple[Path, ...]
```
*(property)*

#### `tr`

```python
tr(key: str, default: str | None = None, **values: object) -> str
```

### `mcw_core.api.minecraft.version_manifest_manager`

Source re-export: `src.core.minecraft.version_manifest_manager`

#### `VersionManifestManager`

Methods:

### `mcw_core.api.mod.mod_compatibility_manager`

Source re-export: `src.core.mod.mod_compatibility_manager`

#### `ModCompatibilityManager`

Public constants:

- `SYSTEM_DEPENDENCY_IDS = {'minecraft', 'java', 'forge', 'neoforge', 'javafml', 'fml', 'fabric', 'fabricloader', 'quilt', 'quilt_loader', 'quiltloader'}`

Methods:

### `mcw_core.api.mod.mod_manager`

Source re-export: `src.core.mod.mod_manager`

#### `ModManager`

Public constants:

- `DISABLED_SUFFIX = '.disabled'`
- `MAX_EMBEDDED_MOD_JARS = 64`
- `MAX_EMBEDDED_MOD_JAR_SIZE = 32 * 1024 * 1024`
- `MAX_EMBEDDED_MOD_DEPTH = 2`

Methods:

### `mcw_core.api.mod.mod_provenance_registry`

Source re-export: `src.core.mod.mod_provenance_registry`

#### `ModProvenanceRegistry`

Unified source identity for installed and manifest-managed mod files.

Public constants:

- `SCHEMA_VERSION = 2`

Methods:

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

### `mcw_core.api.modrinth.modrinth_mod_installer`

Source re-export: `src.core.modrinth.modrinth_mod_installer`

#### `ModrinthModInstaller`

Public constants:

- `MAX_DEPENDENCIES = 64`
- `SUPPORTED_LOADERS = ModLoaderManager.MODDED_LOADERS`

Methods:

### `mcw_core.api.modrinth.modrinth_mod_update_manager`

Source re-export: `src.core.modrinth.modrinth_mod_update_manager`

#### `ModrinthModUpdateManager`

Methods:

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

### `mcw_core.api.modrinth.modrinth_pack_registry`

Source re-export: `src.core.modrinth.modrinth_pack_registry`

#### `ModrinthPackRegistry`

Public constants:

- `SCHEMA_VERSION = 6`
- `FILE_NAME = 'modrinth-pack.json'`

Methods:

### `mcw_core.api.modrinth.modrinth_pack_repair_manager`

Source re-export: `src.core.modrinth.modrinth_pack_repair_manager`

#### `ModrinthPackRepairManager`

Methods:

### `mcw_core.api.modrinth.modrinth_pack_update_manager`

Source re-export: `src.core.modrinth.modrinth_pack_update_manager`

#### `ModrinthPackUpdateManager`

Methods:

### `mcw_core.api.modrinth.modrinth_registry`

Source re-export: `src.core.modrinth.modrinth_registry`

#### `ModrinthRegistry`

Public constants:

- `SCHEMA_VERSION = 2`

Methods:

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
```
*(property)*

### `mcw_core.api.network.download_bandwidth_limiter`

Source re-export: `src.core.network.download_bandwidth_limiter`

#### `DownloadBandwidthLimiter`

Public constants:

- `BYTES_PER_MEGABYTE = 1024 * 1024`

Methods:

```python
limit_mbps() -> float
```
*(property)*

```python
is_enabled() -> bool
```
*(property)*

### `mcw_core.api.network.download_manager`

Source re-export: `src.core.network.download_manager`

#### `DownloadManager`

Methods:

```python
max_concurrent_downloads() -> int
```
*(property)*

```python
per_host_limit() -> int
```
*(property)*

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
```
*(property)*

```python
is_pause_requested() -> bool
```
*(property)*

```python
is_paused() -> bool
```
*(property)*

```python
is_cancel_requested() -> bool
```
*(property)*

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
```
*(property)*

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

### `mcw_core.api.progress.progress_reporter`

Source re-export: `src.core.progress.progress_reporter`

#### `ProgressReporter`

Methods:

### `mcw_core.api.repair.repair_service`

Source re-export: `src.core.repair.repair_service`

#### `RepairService`

Public constants:

- `REPORT_SCHEMA_VERSION = 1`
- `DEFAULT_COMPONENTS = tuple(RepairComponent)`
- `INSTANCE_SCOPED_COMPONENTS = frozenset({RepairComponent.MOD_LOADER, RepairComponent.MODPACK, RepairComponent.SETTINGS})`

Methods:

### `mcw_core.api.runtime.game_runtime_manager`

Source re-export: `src.core.runtime.game_runtime_manager`

#### `GameRuntimeManager`

Public constants:

- `HISTORY_SCHEMA_VERSION = 1`
- `HISTORY_LIMIT = 50`
- `POLL_INTERVAL_SECONDS = 0.5`

Methods:

### `mcw_core.api.runtime.process_supervisor`

Source re-export: `src.core.runtime.process_supervisor`

#### `ProcessSupervisor`

Persist and supervise Minecraft process sessions without touching unrelated Java processes.

Public constants:

- `SCHEMA_VERSION = 1`
- `HISTORY_LIMIT = 100`

Methods:

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
```
*(property)*

#### `StartupRecoveryManager`

Methods:

### `mcw_core.api.security.account_security_manager`

Source re-export: `src.core.security.account_security_manager`

#### `AccountSecurityManager`

Methods:

### `mcw_core.api.security.sensitive_data_redactor`

Source re-export: `src.core.security.sensitive_data_redactor`

#### `SensitiveDataRedactor`

Public constants:

- `REDACTED = '<redacted>'`

Methods:

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
```
*(property)*

#### `CleanupPlan`

Fields / public attributes:

- `candidates: tuple[CleanupCandidate, ...]`

Methods:

```python
total_bytes() -> int
```
*(property)*

```python
file_count() -> int
```
*(property)*

```python
directory_count() -> int
```
*(property)*

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
```
*(property)*

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
```
*(property)*

#### `PlatformStorageMigration`

Copy Alpha 2's portable Linux data into XDG roots without deleting it.

Public constants:

- `SCHEMA_VERSION = 1`
- `MARKER_NAME = '.platform-storage-migration-v1.json'`

Methods:

### `mcw_core.api.system.memory`

Source re-export: `src.core.system.memory`

#### `SystemMemory`

Public constants:

- `BYTES_PER_MB = 1024 * 1024`

Methods:

#### `MemoryAllocationPolicy`

Public constants:

- `MIN_MEMORY_MB = 256`
- `DEFAULT_MIN_MEMORY_MB = 1024`
- `DEFAULT_MAX_MEMORY_MB = 2048`
- `SLIDER_STEP_MB = 256`
- `FALLBACK_PHYSICAL_LIMIT_MB = 4096`

Methods:

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
```
*(property)*

#### `ResolvedThemeAnimation`

Fields / public attributes:

- `definition: ThemeAnimationDefinition`
- `path: Path`
- `theme_id: str`

Methods:

```python
key() -> str
```
*(property)*

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
```
*(property)*

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

### `mcw_core.api.update.linux_update_installer`

Source re-export: `src.core.update.linux_update_installer`

#### `LinuxUpdateInstaller`

Start a detached copy of the packaged launcher to apply a Linux update.

Public constants:

- `STARTUP_GRACE_SECONDS = 1.0`

Methods:

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

#### `UpdateApplier`

Public constants:

- `COPY_RETRIES = 30`
- `COPY_RETRY_DELAY_SECONDS = 0.25`

Methods:

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

#### `UpdateCleanupWorker`

Public constants:

- `DELETE_RETRIES = 40`
- `DELETE_RETRY_DELAY_SECONDS = 0.25`

Methods:

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

### `mcw_core.api.update.windows_update_installer`

Source re-export: `src.core.update.windows_update_installer`

#### `WindowsUpdateInstaller`

Public constants:

- `STARTUP_GRACE_SECONDS = 1.0`

Methods:
