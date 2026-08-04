# MCW Core 1.0.0 — English API Reference

> **Source of truth:** generated and manually reviewed from `mcw_core-1.0.0-py3-none-any.whl`.
>
> **Python:** 3.12 or newer  
> **License:** MIT  
> **Package version:** `1.0.0`  
> **Primary import boundary:** `mcw_core` and `mcw_core.api.*`

MCW Core is the GUI-independent runtime used by MCW Launcher. It provides instance management, Java discovery and installation, Minecraft launch orchestration, progress reporting, cooperative pause/cancel, provider integrations, mod and modpack management, backup, repair, diagnostics, content packs, runtime supervision, and update helpers.

This document is written for developers building a launcher or automation tool on top of the wheel. It explains what to call, what each call returns, how to route progress into a UI, and where advanced APIs fit into a complete launcher architecture.

---

## Table of contents

1. [API stability and package layout](#1-api-stability-and-package-layout)
2. [Installation and verification](#2-installation-and-verification)
3. [Filesystem roots and core initialization](#3-filesystem-roots-and-core-initialization)
4. [The top-level facade](#4-the-top-level-facade)
5. [Core data models](#5-core-data-models)
6. [Progress events](#6-progress-events)
7. [Threads, pause, resume, and cancel](#7-threads-pause-resume-and-cancel)
8. [Startup and recovery](#8-startup-and-recovery)
9. [Accounts and authentication](#9-accounts-and-authentication)
10. [Instances and settings](#10-instances-and-settings)
11. [Minecraft versions, Java, memory, and GPU](#11-minecraft-versions-java-memory-and-gpu)
12. [Mod loaders](#12-mod-loaders)
13. [Launching Minecraft](#13-launching-minecraft)
14. [Mods and compatibility](#14-mods-and-compatibility)
15. [Modrinth](#15-modrinth)
16. [CurseForge](#16-curseforge)
17. [FTB](#17-ftb)
18. [Provider-native import and portable export](#18-provider-native-import-and-portable-export)
19. [Resource packs, shader packs, and the content library](#19-resource-packs-shader-packs-and-the-content-library)
20. [Backup, repair, and diagnostics](#20-backup-repair-and-diagnostics)
21. [Runtime supervision and LAN helpers](#21-runtime-supervision-and-lan-helpers)
22. [Networking and low-level downloads](#22-networking-and-low-level-downloads)
23. [Settings, language, themes, security, and updates](#23-settings-language-themes-security-and-updates)
24. [Error handling](#24-error-handling)
25. [Minimal complete launcher example](#25-minimal-complete-launcher-example)
26. [Recommended application architecture](#26-recommended-application-architecture)
27. [Complete public-module index](#27-complete-public-module-index)

---

## 1. API stability and package layout

### 1.1 Supported import boundary

Application code should import from:

```python
import mcw_core
from mcw_core import MCWCore, CorePaths, LaunchRequest
from mcw_core.api.instance.instance_manager import InstanceManager
```

Avoid importing directly from `src.*` in a third-party launcher. The 1.0.0 wheel currently contains compatibility implementation modules under `src`, but those modules are not the preferred stable boundary.

### 1.2 API layers

| Layer | Intended use | Examples |
|---|---|---|
| Top-level facade | Most launchers | `MCWCore`, `LaunchRequest`, `InstanceCreateRequest` |
| Service objects | Common workflows | `core.instances`, `core.java`, `core.loaders` |
| Public API modules | Advanced features | `mcw_core.api.modrinth`, `mcw_core.api.repair` |
| Compatibility implementation | Internal/legacy | `src.core.*`, `src.models.*` |

### 1.3 Process-wide path registry

`CorePaths.apply()` updates a legacy process-wide path registry. A process should normally use one active MCW data root. Do not expect two `MCWCore` objects configured for different roots to operate concurrently without changing the shared path registry.

---

## 2. Installation and verification

Install the wheel:

```bash
python -m pip install mcw_core-1.0.0-py3-none-any.whl
```

Verify the runtime version:

```bash
python -c "import mcw_core; print(mcw_core.__version__)"
```

Expected output:

```text
1.0.0
```

Inspect the installed distribution metadata:

```python
from importlib.metadata import version

assert version("mcw-core") == "1.0.0"
```

Run the bundled command-line entry point:

```bash
mcw-core-launch --root ./mcw-data --list
mcw-core-launch --root ./mcw-data --instance "My Instance" --username MCWPlayer
```

---

## 3. Filesystem roots and core initialization

### 3.1 `CorePaths`

```python
from pathlib import Path
from mcw_core import CorePaths

paths = CorePaths.from_root(Path.home() / "MCWData")
created = paths.apply()
```

`CorePaths` fields:

| Field | Default under `root` |
|---|---|
| `cache` | `cache/` |
| `instances` | `instances/` |
| `accounts` | `accounts/` |
| `config` | `config/` |
| `logs` | `logs/` |
| `backups` | `backups/` |
| `themes` | `themes/` |
| `runtimes` | `runtimes/` |

Methods:

```python
CorePaths.from_root(root: Path | str) -> CorePaths
CorePaths.current() -> CorePaths
CorePaths.apply(initialize: bool = True) -> dict[str, Path]
```

`apply()` returns the previous path snapshot. Direct consumers usually do not need that return value.

### 3.2 Configure the singleton core

```python
from mcw_core import configure_default_core

core = configure_default_core("./mcw-data")
```

Retrieve it later:

```python
from mcw_core import get_default_core

core = get_default_core()
```

### 3.3 Create an independent facade object

```python
from mcw_core import MCWCore

core = MCWCore.create_default("./mcw-data")
```

This creates a new facade object, but path configuration is still process-wide.

---

## 4. The top-level facade

### 4.1 `MCWCore`

```python
class MCWCore:
    paths: CorePaths
    operations: OperationHandle
    loaders: LoaderService
    instances: InstanceService
    java: JavaService
```

Constructor and factory:

```python
MCWCore(paths: CorePaths | None = None)
MCWCore.create_default(root: Path | str | None = None) -> MCWCore
```

Primary launch call:

```python
MCWCore.launch(request: LaunchRequest) -> LaunchResult
```

Identity rules:

1. If `request.account` is provided, the core uses `request.authentication` or authenticates the account.
2. Otherwise, `request.offline_username` must be non-empty.
3. If neither is supplied, `ValueError` is raised.

### 4.2 Service access

```python
core.instances.list()
core.instances.create(...)
core.loaders.resolve(...)
core.java.scan(...)
core.launch(...)
```

Use the facade/service layer for normal application workflows. Use `mcw_core.api.*` for provider-specific or lower-level features.

---

## 5. Core data models

### 5.1 `LaunchRequest`

```python
@dataclass(frozen=True, slots=True)
class LaunchRequest:
    instance: Instance | str
    account: Account | None = None
    authentication: Authentication | None = None
    offline_username: str = ""
    debug_mode: bool = False
    on_progress: Callable[[ProgressEvent], None] | None = None
    on_exit: Callable[[GameExitResult], None] | None = None
```

### 5.2 `LaunchResult`

```python
@dataclass(frozen=True, slots=True)
class LaunchResult:
    java_path: Path
    minecraft_java_major_version: int
    minecraft_version: str
    warnings: tuple[str, ...] = ()
```

It also behaves as a mapping for legacy compatibility:

```python
result["javaPath"]
result["minecraftJavaMajorVersion"]
result["minecraftVersion"]
result.as_dict()
```

### 5.3 `InstanceCreateRequest`

```python
@dataclass(frozen=True, slots=True)
class InstanceCreateRequest:
    name: str
    version_id: str
    loader_name: str = "vanilla"
    loader_version: str = "auto"
    on_progress: Callable[[ProgressEvent], None] | None = None
```

### 5.4 `Account`

```python
@dataclass(slots=True)
class Account:
    account_id: str
    account_type: AccountSource
    username: str
    uuid: str
    access_token: str | None = None
    refresh_token: str | None = None
    token_expires_at: int | None = None
    skin_url: str | None = None
    skin_variant: str | None = None
```

Treat tokens as sensitive. Do not log or serialize them into diagnostics without using the security redactor.

### 5.5 `Authentication`

```python
@dataclass(slots=True)
class Authentication:
    player_name: str
    uuid: str
    access_token: str
    xuid: str
    client_id: str
    user_type: str
```

### 5.6 `Instance`

```python
@dataclass(slots=True)
class Instance:
    instance_id: str
    name: str
    version_id: str
    instance_dir: Path
    mod_loader: tuple[str, str]
    icon: str = "grass_block"
    last_played: str = ""
    last_exit_code: int | None = None
    last_launch_crashed: bool = False
    last_launch_state: str = "ready"
```

### 5.7 Status and health models

`InstanceStatus` reports runtime state. `InstanceHealthReport` reports static health checks.

```python
status = core.instances.status("My Instance")
print(status.state, status.minecraft_pid)

health = core.instances.health("My Instance")
print(health.healthy, health.repairable)
for issue in health.issues:
    print(issue.severity, issue.code, issue.message)
```

Instance states:

```text
ready, loading, running, finished, crashed
```

Health states include:

```text
healthy, needs_attention, migration_required, missing_java,
missing_files, incomplete, corrupted
```

---

## 6. Progress events

### 6.1 Callback shape

A progress callback receives one `ProgressEvent`:

```python
from mcw_core import ProgressEvent

def on_progress(event: ProgressEvent) -> None:
    print(event.stage.value, event.message)
```

Fields:

| Field | Type | Meaning |
|---|---|---|
| `stage` | `ProgressStage` | Logical operation stage |
| `message` | `str` | Human-readable status |
| `current` | `int | None` | Completed amount |
| `total` | `int | None` | Total amount |
| `unit` | `ProgressUnit` | `none`, `bytes`, `files`, or `steps` |
| `bytes_per_second` | `float | None` | Current aggregate speed |
| `state` | `ProgressState` | `running`, `succeeded`, `failed`, `cancelled` |
| `detail` | `str` | Additional diagnostic detail |

Computed properties:

```python
event.remaining
event.fraction
event.percentage
event.is_determinate
event.is_terminal
```

### 6.2 Stages

The 1.0.0 wheel defines:

```text
preparing
repairing_instance
scanning_repair
verifying_repair
planning_repair
applying_repair
importing_instance
exporting_instance
loading_version
downloading_mod_loader
installing_mod_loader
selecting_java
downloading_java
installing_java
downloading_client
downloading_libraries
downloading_asset_index
downloading_assets
checking_mods
downloading_mods
downloading_content
checking_modpack
downloading_modpack
downloading_update
building_context
building_command
launching
finished
```

Do not build UI logic that assumes a fixed ordering. Switch on the enum value and tolerate future stages.

### 6.3 A robust formatter

```python
from mcw_core import ProgressEvent, ProgressState, ProgressUnit


def format_progress(event: ProgressEvent) -> str:
    prefix = event.stage.value.replace("_", " ").title()

    if event.is_determinate:
        percent = event.percentage or 0.0
        amount = f"{event.current}/{event.total}"
    else:
        percent = None
        amount = ""

    speed = ""
    if event.bytes_per_second is not None:
        speed = f" · {event.bytes_per_second / 1024 / 1024:.1f} MiB/s"

    terminal = ""
    if event.state is not ProgressState.RUNNING:
        terminal = f" [{event.state.value}]"

    percentage = f" · {percent:.1f}%" if percent is not None else ""
    return f"{prefix}: {event.message} {amount}{percentage}{speed}{terminal}".strip()
```

### 6.4 `ProgressReporter`

Use this class when implementing extensions that should emit standard events:

```python
from mcw_core.api.progress.progress_reporter import ProgressReporter
from mcw_core import ProgressStage

reporter = ProgressReporter(on_progress)
reporter.status(ProgressStage.PREPARING, "Preparing custom operation")
reporter.files(ProgressStage.DOWNLOADING_MODS, "Downloading mods", 4, 20, 12_000_000)
reporter.succeeded(ProgressStage.FINISHED, "Operation completed")
```

---

## 7. Threads, pause, resume, and cancel

### 7.1 Never block the GUI thread

Provider calls, Java scans, downloads, repairs, and `core.launch()` may perform blocking work. Run them in a worker thread or task executor.

Callbacks are invoked from the operation's worker thread. Marshal updates onto your GUI thread before touching UI widgets.

### 7.2 `OperationHandle`

```python
state = core.operations.state
print(state.active, state.paused, state.cancel_requested)

core.operations.pause()
core.operations.resume()
core.operations.cancel()
```

Methods:

```python
begin() -> None
finish() -> None
pause() -> bool
resume() -> bool
cancel() -> bool
checkpoint() -> None
```

`MCWCore.launch()` automatically starts and finishes an operation if no operation is already active. For other multi-step workflows, wrap the task yourself:

```python
core.operations.begin()
try:
    core.java.install(21, on_progress=on_progress)
finally:
    core.operations.finish()
```

### 7.3 Cooperative behavior

Pause and cancel are cooperative. Download and preparation code checks the shared controller at checkpoints.

- **Pause** pauses supported preparation/download work.
- **Cancel** interrupts supported preparation/download work.
- These controls do not suspend an already running Minecraft process.
- To stop a running game, use `GameRuntimeManager.stop()` or `ProcessSupervisor.stop_instance()`.

### 7.4 Detecting interruption errors

```python
from mcw_core import is_download_cancelled, is_download_paused

try:
    long_operation()
except Exception as error:
    if is_download_cancelled(error):
        print("Cancelled")
    elif is_download_paused(error):
        print("Paused")
    else:
        raise
```

---

## 8. Startup and recovery

### 8.1 Initialize persistent resources

```python
from mcw_core.api.bootstrap import initialize_application


def startup_progress(percent: int, message_key: str) -> None:
    print(percent, message_key)

settings = initialize_application(startup_progress)
```

The function:

1. Creates required directories.
2. Reconciles interrupted instance sessions.
3. Initializes and loads launcher settings.
4. Configures download concurrency and bandwidth limits.
5. Reconciles interrupted downloads.
6. Initializes the account database.
7. Migrates/protects account data.
8. Returns the loaded settings dictionary.

### 8.2 Keep a splash screen responsive

```python
from mcw_core.api.bootstrap import initialize_application
from mcw_core.api.startup_runner import run_startup_task

settings = run_startup_task(
    task=initialize_application,
    on_progress=lambda percent, key: print(percent, key),
    pump_events=lambda: app.processEvents(),
    timeout_seconds=45.0,
)
```

Exceptions:

- `StartupTimeoutError`
- `StartupWorkerError` (`original_error`, `traceback_text`)

### 8.3 Startup recovery

```python
from mcw_core.api.runtime.startup_recovery_manager import StartupRecoveryManager

report = StartupRecoveryManager.reconcile()
print(report.recovered_item_count)
```

---

## 9. Accounts and authentication

### 9.1 Offline accounts

```python
from mcw_core.api.account.account_manager import AccountManager

account = AccountManager.create_offline_account("MCWPlayer")
AccountManager.set_selected_account(account.account_id)
```

List or manage accounts:

```python
accounts = AccountManager.list_accounts()
selected = AccountManager.get_selected_account()
found = AccountManager.get_account(account_id)
removed = AccountManager.remove_account(account_id)
```

### 9.2 Microsoft accounts

```python
from threading import Event
from mcw_core.api.account.account_manager import AccountManager

cancel_event = Event()
account = AccountManager.create_microsoft_account(cancel_event=cancel_event)
```

Before enabling a Microsoft-authentication button, query availability:

```python
from mcw_core.api.auth.microsoft.microsoft_auth_gate import MicrosoftAuthenticationGate

availability = MicrosoftAuthenticationGate.availability()
```

`MicrosoftAuthenticationGate.require_enabled()` raises `MicrosoftAuthenticationLockedError` when the feature is unavailable.

OAuth callback errors include `MicrosoftAuthorizationCancelledError`.

### 9.3 Launch identity options

Offline launch:

```python
request = LaunchRequest(instance="My Instance", offline_username="MCWPlayer")
```

Account-based launch:

```python
request = LaunchRequest(instance="My Instance", account=account)
```

Pre-authenticated launch:

```python
request = LaunchRequest(
    instance="My Instance",
    account=account,
    authentication=authentication,
)
```

### 9.4 Skin cache

```python
from mcw_core.api.account.account_skin_manager import AccountSkinManager

path = AccountSkinManager.cache_account(account)
cached = AccountSkinManager.cached_texture(account)
```

---

## 10. Instances and settings

### 10.1 List and load

```python
instances = core.instances.list()
instance = core.instances.load("My Instance")
```

Equivalent advanced import:

```python
from mcw_core.api.instance.instance_manager import InstanceManager
instance = InstanceManager.load("My Instance")
```

### 10.2 Create an instance

```python
from mcw_core import InstanceCreateRequest

instance = core.instances.create(
    InstanceCreateRequest(
        name="Fabric 1.21.1",
        version_id="1.21.1",
        loader_name="fabric",
        loader_version="auto",
        on_progress=on_progress,
    )
)
```

`create()` validates the name, resolves/prepares the loader, and returns the created `Instance`.

### 10.3 Lifecycle operations

```python
core.instances.rename("Old Name", "New Name")
clone = core.instances.clone("New Name", "Copy", include_saves=False)
core.instances.delete("Copy")
```

Deletion may raise `InstanceDeletionError`, especially when the instance is active or cannot be safely removed.

### 10.4 Icons

```python
core.instances.set_icon("My Instance", Path("icon.png"))
core.instances.reset_icon("My Instance")
```

### 10.5 Runtime status and health

```python
running_sessions = core.instances.list_running()
status = core.instances.status(instance)
health = core.instances.health(instance)
```

### 10.6 Instance settings

```python
from mcw_core.api.instance.settings_manager import SettingsManager

settings = SettingsManager.load(instance)
settings.max_memory = 8192
SettingsManager.save(instance, settings)
```

Use the concrete `InstanceSettings` model returned by the manager. Do not edit `settings.json` concurrently with a running save operation.

### 10.7 Instance backup packages

```python
preview = core.instances.inspect_package(Path("backup.mcwpack"))
imported = core.instances.import_package(
    Path("backup.mcwpack"),
    on_progress=on_progress,
    settings_override={"max_memory": 8192},
)

output = core.instances.export_package(
    "My Instance",
    Path("My-Instance.mcwpack"),
    include_saves=False,
    on_progress=on_progress,
)
```

---

## 11. Minecraft versions, Java, memory, and GPU

### 11.1 Minecraft version manifest

```python
from mcw_core.api.minecraft.version_manifest_manager import VersionManifestManager

versions = VersionManifestManager.get()
latest_release = VersionManifestManager.latest_version(is_snapshot=False)
latest_snapshot = VersionManifestManager.latest_version(is_snapshot=True)
```

A `VersionManifest` contains:

```python
id: str
type: str
url: str
release_time: datetime
```

### 11.2 Scan Java installations

```python
results = core.java.scan(on_progress=on_progress)

for java in results:
    print(java.display_name)
    print(java.major_version, java.executable, java.source, java.valid)
```

The returned objects are `JavaDiagnostic` values containing:

```text
major_version, version_string, vendor, architecture,
java_home, executable, source, valid
```

### 11.3 Install managed Java

```python
latest = core.java.latest_feature_release()
java_home = core.java.install(21, on_progress=on_progress, force=True)
```

Normalize a requested feature version:

```python
major = core.java.normalize_feature_major("21")
```

### 11.4 Java compatibility policy

```python
from mcw_core.api.java.java_major_policy import JavaMajorPolicy

preferred = JavaMajorPolicy.resolve(required_major=17)
accepted = JavaMajorPolicy.accepted_majors(required_major=17)
```

### 11.5 Memory policy

```python
from mcw_core.api.system.memory import SystemMemory, MemoryAllocationPolicy

total_mb = SystemMemory.total_physical_memory_mb()
minimum, maximum = MemoryAllocationPolicy.normalize(2048, 8192, total_mb)
print(MemoryAllocationPolicy.format_mb(maximum))
```

### 11.6 Dedicated-GPU preference

```python
from mcw_core.api.hardware.gpu_preference_manager import GpuPreferenceManager

detection = GpuPreferenceManager.detect()
if detection.has_dedicated_gpu:
    GpuPreferenceManager.apply_to_java(java_path, enabled=True)
```

This is a best-effort Windows preference. The OS/driver still decides the final adapter.

---

## 12. Mod loaders

### 12.1 Normalize and resolve

```python
loader_name, loader_version = core.loaders.normalize(instance.mod_loader)
resolved = core.loaders.resolve("1.21.1", "fabric", "auto")
```

Supported constants:

```python
core.loaders.VANILLA
core.loaders.FABRIC
core.loaders.QUILT
core.loaders.FORGE
core.loaders.NEOFORGE
core.loaders.AUTO
```

### 12.2 Prepare a loader

```python
prepared_version, resolved_loader = core.loaders.prepare(
    game_version="1.21.1",
    loader_name="fabric",
    loader_version="auto",
    on_progress=on_progress,
)
```

### 12.3 Change, repair, or restore a loader

```python
updated = core.instances.change_loader(
    "My Instance", "neoforge", "auto", on_progress=on_progress
)

core.instances.repair_loader("My Instance", on_progress=on_progress)
core.instances.restore_previous_loader("My Instance", on_progress=on_progress)
```

The instance must not be running.

### 12.4 Loader metadata clients

Advanced modules expose provider metadata:

```python
from mcw_core.api.modloader.fabric.fabric_meta_client import FabricMetaClient
from mcw_core.api.modloader.quilt.quilt_meta_client import QuiltMetaClient
from mcw_core.api.modloader.forge.forge_metadata_client import ForgeMetadataClient
from mcw_core.api.modloader.neoforge.neoforge_metadata_client import NeoForgeMetadataClient
```

Use `core.loaders.resolve()` unless your UI explicitly needs to present raw loader versions.

---

## 13. Launching Minecraft

### 13.1 Offline launch

```python
from mcw_core import LaunchRequest

result = core.launch(
    LaunchRequest(
        instance="Fabric 1.21.1",
        offline_username="MCWPlayer",
        debug_mode=False,
        on_progress=on_progress,
    )
)

print(result.minecraft_version)
print(result.java_path)
print(result.minecraft_java_major_version)
```

### 13.2 Receive game-exit information

```python
def on_exit(exit_result) -> None:
    print("Exit code:", exit_result.exit_code)
    print("Crashed:", exit_result.crashed)
    print("Duration:", exit_result.duration_seconds)
    print("Log:", exit_result.log_path)
    print("Crash report:", exit_result.crash_report_path)

result = core.launch(
    LaunchRequest(
        instance="Fabric 1.21.1",
        offline_username="MCWPlayer",
        on_progress=on_progress,
        on_exit=on_exit,
    )
)
```

Important lifecycle rule:

- `core.launch()` returns after the Minecraft process has been created and launch preparation has completed.
- It does **not** wait until the game closes.
- `on_exit` is called later by the runtime watcher.

### 13.3 Stop a running instance

```python
from mcw_core.api.runtime.game_runtime_manager import GameRuntimeManager

stopped = GameRuntimeManager.stop(instance)
```

Or:

```python
from mcw_core.api.runtime.process_supervisor import ProcessSupervisor
ProcessSupervisor.stop_instance(instance)
```

---

## 14. Mods and compatibility

### 14.1 List mods

```python
from mcw_core.api.mod.mod_manager import ModManager

mods = ModManager.list_mods(instance)
for mod in mods:
    print(mod.name, mod.version, mod.enabled, mod.source)
```

`ModInfo` includes metadata such as:

```text
path, file_name, enabled, mod_id, name, version, loader,
description, authors, licenses, dependencies, conflicts,
source, source_project_id, source_version_id, source_file_id,
managed_by_modpack, source_pack_provider
```

### 14.2 Add local mods

```python
added = ModManager.add_mods(
    instance,
    [Path("mods/FabricAPI.jar")],
    replace=False,
    allow_unverified=False,
)
```

### 14.3 Enable, disable, and remove

```python
ModManager.set_enabled(instance, [mod.path], enabled=False)
ModManager.set_enabled(instance, [mod.path], enabled=True)
ModManager.remove_mods(instance, [mod.path])
```

### 14.4 Compatibility scan

```python
from mcw_core.api.mod.mod_compatibility_manager import ModCompatibilityManager

report = ModCompatibilityManager.scan(instance)
```

Use the report to display missing dependencies, loader mismatches, or conflicts before launch.

### 14.5 Provenance registry

```python
from mcw_core.api.mod.mod_provenance_registry import ModProvenanceRegistry

entries = ModProvenanceRegistry.synchronize(instance)
entry = ModProvenanceRegistry.entry_for_file(instance, "fabric-api.jar")
```

Provider provenance is important for update checks and portable manifest export.

---

## 15. Modrinth

### 15.1 Search projects

```python
from mcw_core.api.modrinth.modrinth_client import ModrinthClient

result = ModrinthClient.search_projects(
    project_type="mod",
    query="sodium",
    game_version="1.21.1",
    loader="fabric",
    index="relevance",
    offset=0,
    limit=25,
)

for project in result.projects:
    print(project.title, project.project_id)
```

### 15.2 Project details and versions

```python
project = ModrinthClient.get_project(project_id)
versions = ModrinthClient.list_project_versions(
    project_id,
    loader="fabric",
    game_version="1.21.1",
    version_types=("release",),
)
version = ModrinthClient.get_version(versions[0].version_id)
```

### 15.3 Install a mod

```python
from mcw_core.api.modrinth.modrinth_mod_installer import ModrinthModInstaller

result = ModrinthModInstaller.install(
    instance,
    version_id=version.version_id,
    install_dependencies=True,
    allowed_version_types=("release", "beta"),
    reporter=ProgressReporter(on_progress),
)
```

### 15.4 Check and apply updates

```python
from mcw_core.api.modrinth.modrinth_mod_update_manager import ModrinthModUpdateManager

report = ModrinthModUpdateManager.check(instance, ("release",))
updated = ModrinthModUpdateManager.update_all(instance, ("release",), ProgressReporter(on_progress))
```

### 15.5 Install or import a Modrinth pack

Online provider installation:

```python
from mcw_core.api.modrinth.modrinth_pack_installer import ModrinthPackInstaller

result = ModrinthPackInstaller.install(
    project_id=project_id,
    version_id=version_id,
    instance_name="My Pack",
    install_optional_files=True,
    reporter=ProgressReporter(on_progress),
    settings_override={"max_memory": 8192},
)
```

Local `.mrpack` import:

```python
result = ModrinthPackInstaller.install_local_archive(
    Path("pack.mrpack"),
    instance_name="My Pack",
    reporter=ProgressReporter(on_progress),
)
```

### 15.6 Pack scan, repair, and update

```python
from mcw_core.api.modrinth.modrinth_pack_registry import ModrinthPackRegistry
from mcw_core.api.modrinth.modrinth_pack_repair_manager import ModrinthPackRepairManager
from mcw_core.api.modrinth.modrinth_pack_update_manager import ModrinthPackUpdateManager

state = ModrinthPackRegistry.scan(instance, ProgressReporter(on_progress))
repair = ModrinthPackRepairManager.repair(instance, ProgressReporter(on_progress))
update_info = ModrinthPackUpdateManager.check(instance, ("release",))
```

---

## 16. CurseForge

### 16.1 Configuration

```python
from mcw_core.api.config.curseforge_config_manager import CurseForgeConfigManager

configured = CurseForgeConfigManager.is_configured()
urls = CurseForgeConfigManager.gateway_urls()
```

Do not place private API tokens in logs or portable package exports.

### 16.2 Search projects

```python
from mcw_core.api.curseforge.curseforge_client import CurseForgeClient

result = CurseForgeClient.search_projects(
    project_type="mod",
    query="jei",
    game_version="1.20.1",
    loader="forge",
    index=0,
    page_size=25,
    sort="popularity",
)
```

### 16.3 Resolve files

```python
project = CurseForgeClient.get_project(project_id)
files = CurseForgeClient.list_files(
    project_id,
    game_version="1.20.1",
    loader="forge",
    release_types=("release",),
)
file = CurseForgeClient.get_file(project_id, file_id)
```

### 16.4 Install a mod

```python
from mcw_core.api.curseforge.curseforge_mod_installer import CurseForgeModInstaller

result = CurseForgeModInstaller.install(
    instance,
    project_id=project_id,
    file_id=file_id,
    install_dependencies=True,
    allowed_release_types=("release",),
    reporter=ProgressReporter(on_progress),
)
```

### 16.5 Install or import a CurseForge pack

```python
from mcw_core.api.curseforge.curseforge_pack_installer import CurseForgePackInstaller

result = CurseForgePackInstaller.install(
    project_id=project_id,
    file_id=file_id,
    instance_name="CurseForge Pack",
    install_optional_files=True,
    reporter=ProgressReporter(on_progress),
    settings_override={"max_memory": 8192},
)
```

Import a provider-native ZIP containing `manifest.json` and `overrides/`:

```python
result = CurseForgePackInstaller.install_local_archive(
    Path("curseforge-pack.zip"),
    instance_name="Imported Pack",
    reporter=ProgressReporter(on_progress),
)
```

### 16.6 Manual download flow

Some CurseForge files do not expose an automatic download URL. A provider operation may raise `CurseForgeManagedFilesRequired` or `CurseForgeModpackManualDownloadRequired`.

```python
from mcw_core.api.curseforge.curseforge_manual_installer import CurseForgeManualInstaller

result = CurseForgeManualInstaller.install_many(
    instance,
    requirements,
    selected_files,
)
```

Always verify the selected file against the required size/hash metadata.

---

## 17. FTB

### 17.1 Search and inspect packs

```python
from mcw_core.api.ftb.ftb_client import FTBClient

result = FTBClient.search_projects(query="academy", page_size=25)
project = FTBClient.get_project_details(project_id)
versions = FTBClient.list_versions(project_id, release_types=("release",))
version = FTBClient.get_version(project_id, version_id)
```

### 17.2 Install an FTB pack

```python
from mcw_core.api.ftb.ftb_pack_installer import FTBPackInstaller

result = FTBPackInstaller.install(
    project_id=project_id,
    version_id=version_id,
    instance_name="FTB Pack",
    install_optional_files=True,
    reporter=ProgressReporter(on_progress),
    settings_override={"max_memory": 8192},
)
```

### 17.3 Deferred content materialization

```python
from mcw_core.api.ftb.ftb_content_manager import FTBContentManager

installed_paths = FTBContentManager.ensure(
    instance,
    reporter=ProgressReporter(on_progress),
)
```

### 17.4 Registry

```python
from mcw_core.api.ftb.ftb_pack_registry import FTBPackRegistry

metadata = FTBPackRegistry.load(instance)
```

---

## 18. Provider-native import and portable export

### 18.1 Inspect a local modpack package

```python
preview = core.instances.inspect_modpack_package(Path("pack.mrpack"))
print(preview.provider)
print(preview.package_format)
print(preview.name)
print(preview.minecraft_version)
print(preview.mod_loader)
print(preview.file_count)
```

The inspector recognizes provider-native packages and MCW portable/profile formats by archive contents, not only filename extension.

### 18.2 Import a package

```python
instance = core.instances.import_modpack_package(
    Path("pack.mrpack"),
    on_progress=on_progress,
    settings_override={
        "min_memory": 2048,
        "max_memory": 8192,
        "width": 1280,
        "height": 720,
    },
    install_optional_files=True,
    instance_name="Imported Pack",
)
```

Supported categories include:

- Modrinth `.mrpack`
- CurseForge manifest ZIP
- Provider Profile ZIP
- Portable MCWPack

### 18.3 Provider Profile export

```python
result = core.instances.export_modpack(
    name="My Pack",
    output_path=Path("My-Pack-Provider-Profile.zip"),
    mode="provider_profile",
    include_saves=False,
    on_progress=on_progress,
)
```

This preserves the provider-native package/reference and adds portable MCW settings without claiming ownership of the original pack.

### 18.4 Portable Smart/Hybrid export

```python
result = core.instances.export_modpack(
    name="My Pack",
    output_path=Path("My-Pack.mcwpack"),
    mode="portable",
    portable_mode="smart",
    include_saves=False,
    on_progress=on_progress,
)
```

The result reports:

```python
result.output_path
result.mode
result.referenced_files
result.embedded_files
result.manual_files
result.native_package_included
```

### 18.5 Full/offline export

```python
result = core.instances.export_modpack(
    name="My Pack",
    output_path=Path("My-Pack-Full.mcwpack"),
    mode="portable",
    portable_mode="full",
    include_saves=False,
    on_progress=on_progress,
)
```

A launcher should show a distribution/license warning before publishing or hosting full packages.

### 18.6 Manual portable files

```python
result = core.instances.install_portable_manual_files(
    "Imported Pack",
    requirements=requirements,
    sources=[Path("downloaded-mod.jar")],
)
```

The selected file must match expected hashes and size.

---

## 19. Resource packs, shader packs, and the content library

### 19.1 List installed content packs

```python
from mcw_core.api.content.content_pack_manager import ContentPackManager

resource_packs = ContentPackManager.list_entries(instance, "resourcepack")
shader_packs = ContentPackManager.list_entries(instance, "shaderpack")
```

### 19.2 Install from Modrinth

```python
result = ContentPackManager.install_modrinth(
    instance,
    content_type="resourcepack",
    version_id=version_id,
    reporter=ProgressReporter(on_progress),
)
```

### 19.3 Install from CurseForge

```python
result = ContentPackManager.install_curseforge(
    instance,
    content_type="shaderpack",
    file=curseforge_file,
    project_name=project.name,
    project_url=project.project_url,
    reporter=ProgressReporter(on_progress),
)
```

### 19.4 Import local ZIP

```python
result = ContentPackManager.import_local(
    instance,
    "resourcepack",
    Path("pack.zip"),
)
```

### 19.5 Toggle and remove

```python
entry = ContentPackManager.set_enabled(instance, entry_id, False)
removed = ContentPackManager.remove(instance, entry_id)
```

### 19.6 Installed Content Library

```python
from mcw_core.api.content.installed_content_library import InstalledContentLibraryManager

library = InstalledContentLibraryManager.scan(instance)
print(library.total_count)
print(library.enabled_count)
print(library.pending_count)
print(library.missing_count)
print(library.managed_count)
print(library.total_size)
```

Batch actions:

```python
InstalledContentLibraryManager.set_enabled(instance, item_ids, False)
InstalledContentLibraryManager.remove(instance, item_ids)
InstalledContentLibraryManager.set_pinned(instance, item_ids, True)
InstalledContentLibraryManager.set_ignored_update(instance, item_ids, True)
```

Respect `toggleable` and `removable` flags in each `InstalledContentItem`.

---

## 20. Backup, repair, and diagnostics

### 20.1 Backups

```python
from mcw_core.api.backup.instance_backup_manager import InstanceBackupManager

created = InstanceBackupManager.create(
    instance,
    scope="full",
    reason="before-update",
)

backups = InstanceBackupManager.list_backups(instance)
info = InstanceBackupManager.inspect(created.backup.path)
restored = InstanceBackupManager.restore(instance, created.backup.path)
```

### 20.2 Repair scan

```python
from mcw_core.api.repair.repair_service import RepairService

report = RepairService.scan(
    instance,
    mode="quick",
    on_progress=on_progress,
)

print(report.healthy)
for issue in report.issues:
    print(issue.component, issue.code, issue.repairable)
```

### 20.3 Build and execute a plan

```python
plan = RepairService.build_plan(report)
if plan.can_repair:
    result = RepairService.repair(instance, plan, on_progress=on_progress)
    print(result.succeeded, result.report_path, result.backup_path)
```

Repair components:

```text
client, libraries, assets, java, mod_loader,
modpack, lan_agent, settings
```

### 20.4 Diagnostics bundle

```python
from mcw_core.api.diagnostics.diagnostics_manager import DiagnosticsManager

bundle = DiagnosticsManager.write_bundle(
    Path("MCW-Diagnostics.zip"),
    launcher_version="1.0.0",
    settings=launcher_settings,
    activity_log=activity_log_text,
)
```

Sensitive values are redacted by the diagnostics/security layer, but callers should still avoid passing unnecessary secrets.

---

## 21. Runtime supervision and LAN helpers

### 21.1 Process sessions

```python
from mcw_core.api.runtime.process_supervisor import ProcessSupervisor

sessions = ProcessSupervisor.list_active()
session = ProcessSupervisor.active_for(instance)
```

`ProcessSession` includes:

```text
session_id, instance_id, instance_name, instance_dir, state,
launcher_pid, root_pid, child_pids, started_at, updated_at,
ended_at, exit_code, detail
```

### 21.2 Stop an instance

```python
ProcessSupervisor.stop_instance(instance, graceful_timeout=2.5)
```

### 21.3 Reconcile stale sessions

```python
removed_session_ids = ProcessSupervisor.reconcile()
```

### 21.4 LAN hosting

```python
from mcw_core.api.lan.lan_hosting_manager import LanHostingManager

plan = LanHostingManager.plan(
    instance,
    auth_mode="private_offline",
    connection_provider="e4mc",
)

result = LanHostingManager.prepare(
    instance,
    auth_mode="private_offline",
    connection_provider="e4mc",
    reporter=ProgressReporter(on_progress),
)
```

### 21.5 LAN Agent

```python
from mcw_core.api.lan.lan_agent_manager import LanAgentManager

install_result = LanAgentManager.install()
arguments = LanAgentManager.runtime_arguments(
    version,
    auth_mode="private_offline",
    instance=instance,
    reporter=ProgressReporter(on_progress),
)
```

---

## 22. Networking and low-level downloads

Most launchers should let provider/core services own downloads. Use `DownloadManager` when implementing a new provider or artifact pipeline.

### 22.1 Download a verified artifact

```python
from mcw_core.api.network.download_manager import DownloadManager

path, sha1, size = DownloadManager().download_and_hash(
    url="https://example.invalid/file.jar",
    path=Path("cache/file.jar"),
    max_attempts=3,
    timeout=30.0,
    reporter=ProgressReporter(on_progress),
)
```

### 22.2 Verify a local file

```python
manager = DownloadManager()
valid = manager.verify(path, expected_size, {"sha1": expected_sha1})
sha512 = manager.calculate_hash(path, "sha512")
```

### 22.3 Configure concurrency

```python
from mcw_core.api.network.download_manager import download_manager

download_manager.configure(max_concurrent_downloads=8, per_host_limit=4)
```

### 22.4 Network session

```python
from mcw_core.api.network.network_session import NetworkSession

session = NetworkSession()
client = session.get_client()
try:
    response = client.get("https://example.com")
finally:
    session.close()
```

---

## 23. Settings, language, themes, security, and updates

### 23.1 Launcher settings

```python
from mcw_core.api.config.launcher_settings_manager import LauncherSettingsManager

manager = LauncherSettingsManager()
manager.initialize()
settings = manager.load()
settings = manager.update_section("launch", {"prefer_dedicated_gpu": True})
```

### 23.2 Managed-content policy

```python
from mcw_core.api.config.managed_content_policy import ManagedContentPolicy

policy = ManagedContentPolicy.resolve(instance_settings, launcher_settings, "modrinth")
blocks = ManagedContentPolicy.blocks_launch(instance_settings, launcher_settings, "modrinth")
```

### 23.3 Language manager

```python
from mcw_core.api.language.language_manager import language_manager, tr

language_manager.reload()
language_manager.set_language("en-US")
print(tr("launch.ready"))
```

Validation helpers:

```python
missing = language_manager.missing_keys("vi-VN")
mismatches = language_manager.placeholder_mismatches("vi-VN")
```

### 23.4 Theme manager

```python
from mcw_core.api.theme.theme_manager import ThemeManager

manager = ThemeManager()
themes = manager.available_themes()
selected = manager.select(theme_id)
stylesheet = manager.resolve_stylesheet(selected)
palette = manager.resolve_palette(selected)
```

Theme authoring:

```python
from mcw_core.api.theme.theme_authoring import ThemeAuthoringService

service = ThemeAuthoringService()
report = service.validate(theme_id)
archive = service.export(theme_id, Path("theme.zip"))
```

### 23.5 Sensitive-data redaction

```python
from mcw_core.api.security.sensitive_data_redactor import SensitiveDataRedactor

safe_text = SensitiveDataRedactor.redact_text(raw_log)
safe_json = SensitiveDataRedactor.redact_json(settings)
```

### 23.6 Account security audit

```python
from mcw_core.api.security.account_security_manager import AccountSecurityManager

report = AccountSecurityManager.audit()
report = AccountSecurityManager.migrate_if_needed()
```

### 23.7 Update check and preparation

```python
from mcw_core.api.update.update_manager import UpdateManager

manager = UpdateManager()
info = manager.check_for_update(force_refresh=True)
if info is not None:
    prepared = manager.prepare_update(info, ProgressReporter(on_progress))
```

Windows automatic application:

```python
from mcw_core.api.update.windows_update_installer import WindowsUpdateInstaller

if WindowsUpdateInstaller.is_supported():
    request_path = WindowsUpdateInstaller.launch(prepared)
```

---

## 24. Error handling

### 24.1 Recommended pattern

```python
from mcw_core import InstanceDeletionError, is_download_cancelled, is_download_paused

try:
    operation()
except Exception as error:
    if is_download_cancelled(error):
        show_cancelled()
    elif is_download_paused(error):
        show_paused()
    elif isinstance(error, InstanceDeletionError):
        show_instance_in_use(error)
    else:
        show_error(type(error).__name__, str(error))
```

### 24.2 Provider manual-download exceptions

Provider imports/downloads may produce structured exceptions that contain requirements for a manual download UI:

- `CurseForgeManagedFilesRequired`
- `CurseForgeModpackManualDownloadRequired`
- Modrinth manual-download exceptions from `mcw_core.api.modrinth.modrinth_errors`
- `PortableManualDownloadRequired`

A launcher should:

1. Present the official project/download page.
2. Ask the user to select the downloaded file.
3. Verify size and strong hashes.
4. Continue only after verification succeeds.

### 24.3 Security errors

Do not catch-and-ignore archive validation, path traversal, checksum, or signature errors. Treat them as hard failures and leave the destination instance unchanged or rolled back.

---

## 25. Minimal complete launcher example

The following console launcher demonstrates startup, instance listing, offline launch, progress, cancellation, and game-exit reporting.

```python
from __future__ import annotations

from pathlib import Path
from threading import Thread
from time import sleep

from mcw_core import (
    CorePaths,
    LaunchRequest,
    MCWCore,
    ProgressEvent,
    is_download_cancelled,
)
from mcw_core.api.bootstrap import initialize_application


def on_startup(percent: int, key: str) -> None:
    print(f"[startup {percent:3d}%] {key}")


def on_progress(event: ProgressEvent) -> None:
    percent = ""
    if event.percentage is not None:
        percent = f" {event.percentage:5.1f}%"
    speed = ""
    if event.bytes_per_second is not None:
        speed = f" {event.bytes_per_second / 1024 / 1024:.1f} MiB/s"
    print(f"[{event.stage.value}] {event.message}{percent}{speed}")


def on_exit(result) -> None:
    print(f"Minecraft exited with code {result.exit_code}")
    if result.crashed:
        print("Crash report:", result.crash_report_path)


def main() -> int:
    root = Path.home() / "MCWExample"
    core = MCWCore(CorePaths.from_root(root))
    initialize_application(on_startup)

    instances = core.instances.list()
    if not instances:
        print("No instances exist yet.")
        return 1

    instance = instances[0]
    print("Launching:", instance.name)

    error_box: list[BaseException] = []

    def worker() -> None:
        try:
            result = core.launch(
                LaunchRequest(
                    instance=instance,
                    offline_username="MCWPlayer",
                    on_progress=on_progress,
                    on_exit=on_exit,
                )
            )
            print("Process created using:", result.java_path)
        except BaseException as error:
            error_box.append(error)

    thread = Thread(target=worker, name="mcw-launch", daemon=True)
    thread.start()

    while thread.is_alive():
        sleep(0.1)
        # Connect your UI buttons to these methods:
        # core.operations.pause()
        # core.operations.resume()
        # core.operations.cancel()

    thread.join()

    if error_box:
        error = error_box[0]
        if is_download_cancelled(error):
            print("Launch preparation was cancelled.")
            return 130
        raise error

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

---

## 26. Recommended application architecture

A desktop launcher should separate UI state from core operations:

```text
View / Page / Dialog
        ↓ signals and input validation
Controller / Presenter
        ↓ immutable request objects
Task Runner / Worker Thread
        ↓ public MCW Core API
MCWCore / mcw_core.api
        ↓ ProgressEvent and result objects
Presenter / View-model mapper
        ↓ GUI-thread update
View
```

Recommended rules:

1. Never import GUI modules from the core layer.
2. Never run network, disk, hash, repair, or launch preparation on the GUI thread.
3. Pass `ProgressEvent` values through a thread-safe signal/queue.
4. Treat provider objects as domain data, not widgets.
5. Keep account tokens out of logs.
6. Display explicit manual-download requirements instead of bypassing provider policy.
7. Preserve provider provenance and hashes when importing/exporting modpacks.
8. Make cancellation and rollback visible to the user.
9. Use `on_exit` to update playtime/crash UI after the process ends.
10. Prefer public `mcw_core`/`mcw_core.api` imports over `src.*` compatibility imports.

---

## 27. Complete public-module index

The following index lists public classes and functions exposed through `mcw_core.api` modules in the 1.0.0 wheel. Signatures are extracted from the shipped source. Some advanced return models are implementation dataclasses; inspect their attributes or type annotations when building specialized views.
### `mcw_core.api.account.account_manager`
#### `AccountManager`
- *staticmethod* `create_offline_account(username: str) -> Account`
- *staticmethod* `create_microsoft_account(cancel_event: Event | None = None) -> Account`
- *staticmethod* `list_accounts() -> list[Account]`
- *staticmethod* `get_account(account_id: str) -> Account | None`
- *staticmethod* `get_selected_account() -> Account | None`
- *staticmethod* `set_selected_account(account_id: str) -> bool`
- *staticmethod* `synchronize_microsoft_profile(account_id: str) -> Account`
- *staticmethod* `remove_account(account_id: str) -> bool`
- *staticmethod* `is_account_exist(username: str) -> bool`
### `mcw_core.api.account.account_skin_manager`
#### `AccountSkinManager`
Cache Minecraft skin textures without making the GUI depend on network APIs.
- *classmethod* `cache_profile(cls, profile: MinecraftProfile) -> Path | None`
- *classmethod* `cache_account(cls, account: Account) -> Path | None`
- *classmethod* `cache_texture(cls, profile_uuid: str, skin_url: str) -> Path`
- *classmethod* `cached_texture(cls, account_or_uuid: Account | str) -> Path | None`
- *classmethod* `remove_cached_texture(cls, account_or_uuid: Account | str) -> None`
- *staticmethod* `texture_path(profile_uuid: str) -> Path`
### `mcw_core.api.auth.microsoft.microsoft_auth_gate`
#### `MicrosoftAuthenticationLockedError` — bases: `RuntimeError`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `MicrosoftAuthenticationAvailability`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `MicrosoftAuthenticationGate`
- *staticmethod* `availability() -> MicrosoftAuthenticationAvailability`
- *staticmethod* `require_enabled() -> None`
### `mcw_core.api.auth.microsoft.oauth_callback_server`
#### `MicrosoftAuthorizationCancelledError` — bases: `RuntimeError`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `OAuthCallbackHandler` — bases: `BaseHTTPRequestHandler`
- `do_GET(self) -> None`
- `log_message(self, format: str, *args) -> None`
#### `ReusableOAuthHTTPServer` — bases: `HTTPServer`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `OAuthCallbackServer`
- *staticmethod* `wait_for_callback(timeout: float = 180.0, cancel_event: Event | None = None) -> tuple[str, str]`
### `mcw_core.api.backup.instance_backup_manager`
#### `InstanceBackupManager`
- *staticmethod* `create(instance: Instance, scope: str = SCOPE_FULL, reason: str = 'manual', destination: Path | None = None) -> InstanceBackupResult`
- *staticmethod* `inspect(path: Path) -> InstanceBackupInfo`
- *staticmethod* `list_backups(instance: Instance) -> list[InstanceBackupInfo]`
- *staticmethod* `restore(instance: Instance, backup_path: Path, create_safety_backup: bool = True) -> InstanceRestoreResult`
### `mcw_core.api.bootstrap`
#### Function `initialize_application(progress_callback: BootstrapProgressCallback | None = None) -> dict[str, Any]`
### `mcw_core.api.config.curseforge_config_manager`
#### `CurseForgeConfigManager`
Loads CurseForge gateway endpoints with safe local overrides. The public MCW gateway is the default on fresh installations. User-provided overrides are protected with Windows DPAPI and environment variables remain available for managed deployments. No CurseForge API credential is stored in the launcher.
- *staticmethod* `path() -> Path`
- *staticmethod* `legacy_path() -> Path`
- *classmethod* `gateway_urls(cls) -> tuple[str, ...]`
- *classmethod* `gateway_url(cls) -> str`
- *classmethod* `client_token(cls) -> str`
- *classmethod* `is_configured(cls) -> bool`
- *classmethod* `save_local(cls, gateway_urls: Iterable[str] | str, client_token: str | None = None) -> Path`
### `mcw_core.api.config.launcher_settings_manager`
#### `LauncherSettingsManager`
- `initialize(self) -> Path`
- `load(self) -> dict[str, Any]`
- `save(self, settings: dict[str, Any]) -> dict[str, Any]`
- `update_section(self, section: str, values: dict[str, Any]) -> dict[str, Any]`
- `reset(self) -> dict[str, Any]`
- `load_window_geometry(self) -> bytes | None`
- `save_window_geometry(self, geometry: bytes | bytearray | memoryview) -> None`
### `mcw_core.api.config.managed_content_policy`
#### `ManagedContentPolicy`
- *classmethod* `normalize_instance(cls, value: object, default: str = INHERIT) -> str`
- *classmethod* `normalize_global(cls, value: object, default: str = BLOCK) -> str`
- *classmethod* `from_legacy_bool(cls, value: object, default: bool = True) -> str`
- *classmethod* `resolve(cls, instance_settings: object, launcher_settings: dict[str, Any], provider: str) -> str`
- *classmethod* `blocks_launch(cls, instance_settings: object, launcher_settings: dict[str, Any], provider: str) -> bool`
### `mcw_core.api.content.content_pack_manager`
#### `ContentPackManager`
- *classmethod* `list_entries(cls, instance: Instance, content_type: str = '') -> list[ContentPackEntry]`
- *classmethod* `install_modrinth(cls, instance: Instance, content_type: str, version_id: str, reporter: ProgressReporter | None = None) -> ContentPackInstallResult`
- *classmethod* `install_curseforge(cls, instance: Instance, content_type: str, file: CurseForgeFile, project_name: str = '', project_url: str = '', reporter: ProgressReporter | None = None) -> ContentPackInstallResult`
- *classmethod* `import_local(cls, instance: Instance, content_type: str, source: Path) -> ContentPackInstallResult`
- *classmethod* `set_enabled(cls, instance: Instance, entry_id: str, enabled: bool) -> ContentPackEntry`
- *classmethod* `remove(cls, instance: Instance, entry_id: str) -> ContentPackEntry`
- *classmethod* `destination_dir(cls, instance: Instance, content_type: str) -> Path`
- *classmethod* `validate_archive(cls, source: Path, content_type: str) -> dict[str, object]`
- *classmethod* `normalize_type(cls, value: str) -> str`
- *classmethod* `display_name(cls, content_type: str) -> str`
- *classmethod* `curseforge_project_url(cls, content_type: str, project_id: int | str) -> str`
### `mcw_core.api.content.content_pack_registry`
#### `ContentPackRegistry`
- *classmethod* `path(cls, instance: Instance) -> Path`
- *classmethod* `load(cls, instance: Instance) -> dict`
- *classmethod* `save(cls, instance: Instance, payload: dict) -> Path`
- *classmethod* `entries(cls, instance: Instance, content_type: str = '') -> list[ContentPackEntry]`
- *classmethod* `upsert(cls, instance: Instance, entry: ContentPackEntry) -> None`
- *classmethod* `remove(cls, instance: Instance, entry_id: str) -> ContentPackEntry | None`
### `mcw_core.api.content.installed_content_library`
#### `InstalledContentLibraryManager`
- *classmethod* `scan(cls, instance: Instance) -> InstalledContentLibrary`
- *classmethod* `set_enabled(cls, instance: Instance, item_ids: list[str] | tuple[str, ...], enabled: bool) -> tuple[str, ...]`
- *classmethod* `remove(cls, instance: Instance, item_ids: list[str] | tuple[str, ...]) -> tuple[str, ...]`
- *staticmethod* `set_pinned(instance: Instance, item_ids: list[str] | tuple[str, ...], pinned: bool) -> tuple[str, ...]`
- *staticmethod* `set_ignored_update(instance: Instance, item_ids: list[str] | tuple[str, ...], ignored: bool) -> tuple[str, ...]`
- *classmethod* `destination_folder(cls, instance: Instance, content_type: str) -> Path`
#### `InstalledContentItem`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `InstalledContentLibrary`
- *property* `total_count(self) -> int`
- *property* `enabled_count(self) -> int`
- *property* `pending_count(self) -> int`
- *property* `missing_count(self) -> int`
- *property* `managed_count(self) -> int`
- *property* `total_size(self) -> int`
### `mcw_core.api.curseforge.curseforge_client`
#### `CurseForgeClient`
- *staticmethod* `is_available() -> bool`
- *staticmethod* `gateway_urls() -> tuple[str, ...]`
- *staticmethod* `gateway_url() -> str`
- *staticmethod* `cache_status() -> CurseForgeCacheInfo`
- *staticmethod* `clear_cache() -> None`
- *staticmethod* `manual_refresh_remaining_seconds() -> int`
- *staticmethod* `search_projects(project_type: str, query: str = '', game_version: str = '', loader: str = 'forge', index: int = 0, page_size: int = 25, sort: str = 'popularity', force_refresh: bool = False, manual_refresh: bool = False) -> CurseForgeSearchResult`
- *staticmethod* `get_project(project_id: int | str, force_refresh: bool = False) -> CurseForgeProject`
- *staticmethod* `get_project_details(project_id: int | str, force_refresh: bool = False) -> CurseForgeProject`
- *staticmethod* `get_projects_batch(project_ids: list[int] | tuple[int, ...] | set[int]) -> dict[int, CurseForgeProject]`
- *staticmethod* `list_files_result(project_id: int | str, game_version: str = '', loader: str = 'forge', release_types: tuple[str, ...] | list[str] | set[str] | None = None, page_size: int = 50, force_refresh: bool = False, manual_refresh: bool = False) -> CurseForgeFileListResult`
- *staticmethod* `list_files(project_id: int | str, game_version: str = '', loader: str = 'forge', release_types: tuple[str, ...] | list[str] | set[str] | None = None, page_size: int = 50, force_refresh: bool = False) -> list[CurseForgeFile]`
- *staticmethod* `get_file(project_id: int | str, file_id: int | str, force_refresh: bool = False) -> CurseForgeFile`
- *staticmethod* `get_files_batch(file_ids: list[int] | tuple[int, ...] | set[int]) -> dict[int, CurseForgeFile]`
- *staticmethod* `get_download_url(project_id: int | str, file_id: int | str, force_refresh: bool = False) -> str`
- *staticmethod* `latest_compatible_file(project_id: int | str, game_version: str, loader: str = 'forge', release_types: tuple[str, ...] | list[str] | set[str] | None = None) -> CurseForgeFile`
- *staticmethod* `normalize_loader(loader: str) -> str`
- *staticmethod* `loader_compatibility(file: CurseForgeFile, loader: str) -> str`
- *staticmethod* `is_permanent_error(error: BaseException) -> bool`
- *staticmethod* `normalize_release_types(release_types: tuple[str, ...] | list[str] | set[str] | None = None) -> tuple[str, ...]`
### `mcw_core.api.curseforge.curseforge_errors`
#### `CurseForgeManagedFilesRequired` — bases: `RuntimeError`
Raised when managed CurseForge files require user-assisted recovery.
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `CurseForgeModpackManualDownloadRequired` — bases: `RuntimeError`
Raised when a CurseForge modpack archive must be downloaded manually.
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
### `mcw_core.api.curseforge.curseforge_manual_installer`
#### `CurseForgeManualInstaller`
- *staticmethod* `install(instance: Instance, requirement: CurseForgeManualDownload, source: Path) -> str`
- *staticmethod* `install_many(instance: Instance, requirements: tuple[CurseForgeManualDownload, ...] | list[CurseForgeManualDownload], sources: tuple[Path, ...] | list[Path]) -> CurseForgeManualImportResult`
- *staticmethod* `copy_to_cache(source: Path, destination: Path) -> Path`
### `mcw_core.api.curseforge.curseforge_mod_installer`
#### `CurseForgeModInstaller`
- *staticmethod* `install(instance: Instance, project_id: int, file_id: int, install_dependencies: bool = True, allowed_release_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None, allow_unverified: bool = False) -> CurseForgeModInstallResult`
### `mcw_core.api.curseforge.curseforge_pack_installer`
#### `CurseForgePackInstaller`
- *staticmethod* `install(project_id: int, file_id: int, instance_name: str, install_optional_files: bool = True, allowed_release_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None, expected_loader: str = '', settings_override: dict | None = None) -> CurseForgeModpackInstallResult`
- *staticmethod* `install_local_archive(pack_path: Path, instance_name: str = '', install_optional_files: bool = True, reporter: ProgressReporter | None = None, settings_override: dict | None = None) -> CurseForgeModpackInstallResult`
- *staticmethod* `install_manual_archive(request: CurseForgeModpackManualDownloadRequired, source: Path, reporter: ProgressReporter | None = None) -> CurseForgeModpackInstallResult`
### `mcw_core.api.curseforge.curseforge_registry`
#### `CurseForgeRegistry`
- *staticmethod* `empty() -> dict`
- *staticmethod* `load(instance: Instance) -> dict`
- *staticmethod* `save(instance: Instance, data: dict) -> None`
- *staticmethod* `remove_by_filenames(instance: Instance, filenames: list[str] | tuple[str, ...] | set[str]) -> tuple[str, ...]`
- *staticmethod* `safe_tracked_path(instance: Instance, filename: str) -> Path | None`
### `mcw_core.api.diagnostics.diagnostics_manager`
#### `DiagnosticsManager`
- *classmethod* `build_report(cls, launcher_version: str, settings: dict[str, Any] | None = None, activity_log: str = '') -> str`
- *classmethod* `write_report(cls, path: Path, launcher_version: str, settings: dict[str, Any] | None = None, activity_log: str = '') -> Path`
- *classmethod* `write_bundle(cls, path: Path, launcher_version: str, settings: dict[str, Any] | None = None, activity_log: str = '') -> Path`
### `mcw_core.api.fs.paths`
#### `Paths`
- *staticmethod* `initialize() -> None`
- *staticmethod* `backups_root() -> Path`
- *staticmethod* `instance_backups_dir(instance: Instance) -> Path`
- *staticmethod* `backup_staging_root() -> Path`
- *staticmethod* `theme_asset(theme: str, *paths: str) -> Path`
- *staticmethod* `theme_dir(name: str) -> Path`
- *staticmethod* `root() -> Path`
- *staticmethod* `snapshot() -> dict[str, Path]`
- *staticmethod* `restore(snapshot: dict[str, Path], initialize: bool = False) -> None`
- *staticmethod* `configure(root: Path | str | None = None, *, cache_root: Path | str | None = None, instances_root: Path | str | None = None, accounts_root: Path | str | None = None, config_root: Path | str | None = None, logs_root: Path | str | None = None, backups_root: Path | str | None = None, theme_root: Path | str | None = None, runtimes_root: Path | str | None = None, initialize: bool = True) -> dict[str, Path]`
- *staticmethod, contextmanager* `configured(root: Path | str | None = None, **overrides: object) -> Iterator[None]`
- *staticmethod* `microsoft_config_root() -> Path`
- *staticmethod* `launcher_settings_path() -> Path`
- *staticmethod* `logs_root() -> Path`
- *staticmethod* `updater_log_path() -> Path`
- *staticmethod* `diagnostics_default_path() -> Path`
- *staticmethod* `download_journal_path() -> Path`
- *staticmethod* `update_root() -> Path`
- *staticmethod* `update_release_cache() -> Path`
- *staticmethod* `update_download_path(tag_name: str, asset_name: str) -> Path`
- *staticmethod* `update_staging_root() -> Path`
- *staticmethod* `account_database_path()`
- *staticmethod* `account_skins_root() -> Path`
- *staticmethod* `accounts_path() -> Path`
- *staticmethod* `instance_metadata(instance_name: str) -> Path`
- *staticmethod* `instance_settings_path(instance: Instance) -> Path`
- *staticmethod* `instance_settings_create(instance: Instance) -> Path`
- *staticmethod* `instances_root() -> Path`
- *staticmethod* `instance_runtime_root() -> Path`
- *staticmethod* `instance_operations_root() -> Path`
- *staticmethod* `instance_staging_root() -> Path`
- *staticmethod* `process_sessions_root() -> Path`
- *staticmethod* `process_session_history_root() -> Path`
- *staticmethod* `load_instance_dir(name: str) -> Path`
- *staticmethod* `create_instance_dir(name: str) -> Path`
- *staticmethod* `instance_data_path_create()`
- *staticmethod* `instance_data_path()`
- *staticmethod* `version_dir(version: Version)`
- *staticmethod* `client(version: Version)`
- *staticmethod* `fabric_version_dir(game_version: str, loader_version: str) -> Path`
- *staticmethod* `fabric_version_json(game_version: str, loader_version: str) -> Path`
- *staticmethod* `fabric_metadata_root() -> Path`
- *staticmethod* `fabric_catalog_json(game_version: str) -> Path`
- *staticmethod* `fabric_install_metadata_json(game_version: str, loader_version: str) -> Path`
- *staticmethod* `fabric_profile_json(game_version: str, loader_version: str) -> Path`
- *staticmethod* `quilt_version_dir(game_version: str, loader_version: str) -> Path`
- *staticmethod* `quilt_version_json(game_version: str, loader_version: str) -> Path`
- *staticmethod* `quilt_metadata_root() -> Path`
- *staticmethod* `quilt_catalog_json(game_version: str) -> Path`
- *staticmethod* `quilt_install_metadata_json(game_version: str, loader_version: str) -> Path`
- *staticmethod* `quilt_profile_json(game_version: str, loader_version: str) -> Path`
- *staticmethod* `neoforge_root() -> Path`
- *staticmethod* `neoforge_version_dir(game_version: str, neoforge_version: str) -> Path`
- *staticmethod* `neoforge_version_json(game_version: str, neoforge_version: str) -> Path`
- *staticmethod* `neoforge_installer_path(game_version: str, neoforge_version: str) -> Path`
- *staticmethod* `neoforge_staging_dir(game_version: str, neoforge_version: str) -> Path`
- *staticmethod* `forge_root() -> Path`
- *staticmethod* `forge_version_dir(game_version: str, forge_version: str) -> Path`
- *staticmethod* `forge_version_json(game_version: str, forge_version: str) -> Path`
- *staticmethod* `forge_installer_path(game_version: str, forge_version: str) -> Path`
- *staticmethod* `forge_staging_dir(game_version: str, forge_version: str) -> Path`
- *staticmethod* `forge_instance_root(instance: Instance) -> Path`
- *staticmethod* `forge_rollback_path(instance: Instance) -> Path`
- *staticmethod* `forge_instance_log_path(instance: Instance) -> Path`
- *staticmethod* `forge_diagnostics_default_path(instance: Instance) -> Path`
- *staticmethod* `ftb_root() -> Path`
- *staticmethod* `ftb_file_cache(project_id: int | str, version_id: int | str, filename: str) -> Path`
- *staticmethod* `ftb_pack_registry(instance: Instance) -> Path`
- *staticmethod* `curseforge_root() -> Path`
- *staticmethod* `curseforge_api_cache(cache_key: str) -> Path`
- *staticmethod* `curseforge_file_cache(project_id: int | str, file_id: int | str, filename: str) -> Path`
- *staticmethod* `curseforge_pack_cache(project_id: int | str, file_id: int | str, filename: str) -> Path`
- *staticmethod* `instance_artwork_cache(provider: str, project_id: str, artwork_url: str) -> Path`
- *staticmethod* `curseforge_instance_registry(instance: Instance) -> Path`
- *staticmethod* `curseforge_instance_transaction_root(instance: Instance) -> Path`
- *staticmethod* `curseforge_pack_registry(instance: Instance) -> Path`
- *staticmethod* `instance_logs_dir(instance: Instance) -> Path`
- *staticmethod* `instance_crash_reports_dir(instance: Instance) -> Path`
- *staticmethod* `instance_runtime_history(instance: Instance) -> Path`
- *staticmethod* `instance_repair_report(instance: Instance) -> Path`
- *staticmethod* `instance_repair_cache(instance: Instance) -> Path`
- *staticmethod* `instance_repair_scan_report(instance: Instance) -> Path`
- *staticmethod* `instance_repair_execution_report(instance: Instance) -> Path`
- *staticmethod* `instance_mods_dir(instance: Instance) -> Path`
- *staticmethod* `mod_provenance_registry(instance: Instance) -> Path`
- *staticmethod* `modrinth_root() -> Path`
- *staticmethod* `modrinth_api_cache(cache_key: str) -> Path`
- *staticmethod* `modrinth_file_cache(project_id: str, version_id: str, filename: str) -> Path`
- *staticmethod* `modrinth_pack_cache(project_id: str, version_id: str, filename: str) -> Path`
- *staticmethod* `modrinth_staging_root() -> Path`
- *staticmethod* `modrinth_instance_registry(instance: Instance) -> Path`
- *staticmethod* `libraries()`
- *staticmethod* `version_manifest() -> Path`
- *staticmethod* `version_json(version: Version) -> Path`
- *staticmethod* `asset_index(version: Version)`
- *staticmethod* `asset_index_dir()`
- *staticmethod* `asset_object(asset: DownloadAsset)`
- *staticmethod* `assets_dir()`
- *staticmethod* `natives(version: Version)`
### `mcw_core.api.ftb.ftb_client`
#### `FTBClient`
Small public FTB modpack API adapter. The FTB feeds have historically exposed both a public catalog prefix and a direct modpack prefix. Requests therefore use ordered official endpoints and only fail after every compatible route has been attempted.
- *staticmethod* `cache_status() -> FTBCacheInfo`
- *staticmethod* `clear_cache() -> None`
- *staticmethod* `search_projects(query: str = '', index: int = 0, page_size: int = 25, sort: str = 'popularity', force_refresh: bool = False) -> FTBSearchResult`
- *staticmethod* `get_project(project_id: int | str, force_refresh: bool = False) -> FTBProject`
- *staticmethod* `get_project_details(project_id: int | str, force_refresh: bool = False) -> FTBProject`
- *staticmethod* `list_versions(project_id: int | str, release_types: Iterable[str] | None = None, force_refresh: bool = False) -> tuple[FTBVersionSummary, ...]`
- *staticmethod* `get_version(project_id: int | str, version_id: int | str, force_refresh: bool = False) -> FTBVersion`
- *staticmethod* `normalize_release_type(value: object) -> str`
- *staticmethod* `normalize_loader(value: object) -> str`
### `mcw_core.api.ftb.ftb_content_manager`
#### `FTBContentManager`
Materialize deferred FTB modpack files immediately before launch.
- *staticmethod* `ensure(instance: Instance, reporter: ProgressReporter | None = None, launch_lock_token: str | None = None) -> tuple[str, ...]`
### `mcw_core.api.ftb.ftb_pack_installer`
#### `FTBPackInstaller`
- *staticmethod* `install(project_id: int, version_id: int, instance_name: str, install_optional_files: bool = True, allowed_release_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None, settings_override: dict | None = None) -> FTBModpackInstallResult`
### `mcw_core.api.ftb.ftb_pack_registry`
#### `FTBPackRegistry`
- *staticmethod* `load(instance: Instance | Path) -> dict`
- *staticmethod* `save(instance: Instance | Path, data: dict) -> None`
- *staticmethod* `safe_relative_path(value: str, fallback_filename: str) -> str`
### `mcw_core.api.hardware.gpu_preference_manager`
#### `GraphicsAdapter`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `GraphicsDetectionResult`
- *property* `dedicated_adapters(self) -> tuple[GraphicsAdapter, ...]`
- *property* `has_dedicated_gpu(self) -> bool`
#### `GpuPreferenceManager`
Best-effort Windows graphics preference integration. Windows owns the final adapter selection. MCW records the per-executable high-performance preference for the selected Java runtime and never blocks a launch when Windows or a display driver refuses the preference.
- *classmethod* `detect(cls) -> GraphicsDetectionResult`
- *classmethod* `apply_for_executable(cls, executable: Path | str, enabled: bool) -> bool`
- *classmethod* `apply_to_java(cls, java_path: Path | str, enabled: bool) -> bool`
- *classmethod* `adapter_summary(cls, adapters: Iterable[GraphicsAdapter]) -> str`
### `mcw_core.api.instance.errors`
#### `InstanceAlreadyRunningError` — bases: `RuntimeError`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `InstanceModChangeBlockedError` — bases: `RuntimeError`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `InstanceDeletionError` — bases: `RuntimeError`
Structured failure raised when an instance cannot be removed safely.
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
### `mcw_core.api.instance.instance_health_manager`
#### `InstanceHealthManager`
Run a fast, non-networked health check suitable for launcher startup.
- *classmethod* `scan(cls, instance: Instance) -> InstanceHealthReport`
- *classmethod* `list(cls, instances: list[Instance]) -> list[InstanceHealthReport]`
### `mcw_core.api.instance.instance_manager`
#### `InstanceManager`
- *staticmethod* `validate_name(value: str) -> str`
- *staticmethod* `list_instances() -> list[Instance]`
- *staticmethod* `clone(source_name: str, new_name: str, include_saves: bool = False) -> Instance`
- *staticmethod* `export(instance_name: str, output_path: Path, include_saves: bool = False, on_progress: ProgressCallback | None = None) -> Path`
- *staticmethod* `set_icon(instance_name: str, source_path: Path, origin: dict | None = None) -> Instance`
- *staticmethod* `reset_icon(instance_name: str) -> Instance`
- *staticmethod* `resolve_icon_path(instance: Instance) -> Path | None`
- *staticmethod* `inspect_import(package_path: Path) -> InstancePackagePreview`
- *staticmethod* `import_instance(package_path: Path, on_progress: ProgressCallback | None = None, settings_override: dict | InstanceSettings | None = None) -> Instance`
- *staticmethod* `rename(instance_name: str, new_name: str) -> Path`
- *staticmethod* `load(name: str) -> Instance`
- *staticmethod* `create(name: str, version: Version, mod_loader = ('vanilla', '-1'), settings: dict | InstanceSettings | None = None) -> Instance`
- *staticmethod* `default_instance_settings() -> dict`
- *staticmethod* `set_runtime_profile(name: str, version: Version, mod_loader: tuple[str, str]) -> Instance`
- *staticmethod* `set_mod_loader(name: str, mod_loader: tuple[str, str]) -> Instance`
- *staticmethod* `delete_instance(name: str) -> bool`
- *staticmethod* `reconcile_registry() -> dict`
- *staticmethod* `next_available_name(preferred_name: str) -> str`
- *staticmethod* `is_instance_exist(name: str) -> bool`
### `mcw_core.api.instance.instance_operation_journal`
#### `InstanceRecoveryRecord`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `InstanceOperationJournal`
- *classmethod* `begin(cls, operation: str, instance_name: str, *, source_path: Path | None = None, target_path: Path | None = None, staging_path: Path | None = None) -> InstanceOperationJournal`
- `update(self, phase: str, **updates: Any) -> None`
- `complete(self) -> None`
- `abandon(self) -> None`
- *classmethod* `recover_all(cls) -> tuple[InstanceRecoveryRecord, ...]`
### `mcw_core.api.instance.instance_run_lock`
#### `RunningInstanceInfo`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `InstanceRunLock`
- *classmethod* `acquire(cls, instance: Instance) -> InstanceRunLock`
- `track_process(self, process: Any) -> bool`
- `release(self) -> None`
- *classmethod* `is_active(cls, instance: Instance) -> bool`
- *classmethod* `owns_preparing_lock(cls, instance: Instance, token: str | None) -> bool`
- *classmethod* `active_for(cls, instance: Instance) -> RunningInstanceInfo | None`
- *classmethod* `remove_for(cls, instance: Instance, force: bool = False) -> bool`
- *classmethod* `reconcile(cls) -> tuple[str, ...]`
- *classmethod* `list_active(cls) -> list[RunningInstanceInfo]`
- *classmethod* `lock_path_for(cls, instance: Instance) -> Path`
### `mcw_core.api.instance.settings_manager`
#### Function `default_instance_settings() -> dict[str, Any]`
#### `SettingsManager`
- *staticmethod* `load(instance: Instance) -> InstanceSettings`
- *staticmethod* `save(instance: Instance, settings: InstanceSettings) -> None`
- *staticmethod* `save_default(instance: Instance) -> None`
- *classmethod* `default_dict(cls) -> dict[str, Any]`
- *staticmethod* `from_dict(data: dict[str, Any] | InstanceSettings | None) -> InstanceSettings`
- *staticmethod* `to_dict(settings: InstanceSettings) -> dict[str, Any]`
- *staticmethod* `normalize_dict(data: dict[str, Any] | InstanceSettings | None) -> dict[str, Any]`
- *staticmethod* `save_dict(instance: Instance, data: dict[str, Any] | InstanceSettings | None) -> None`
- *staticmethod* `update_memory(instance: Instance, min_memory: int, max_memory: int) -> InstanceSettings`
- *staticmethod* `update_java_path(instance: Instance, java_path: str) -> InstanceSettings`
- *staticmethod* `update_window(instance: Instance, width: int, height: int, fullscreen: bool) -> InstanceSettings`
- *staticmethod* `update_jvm_arguments(instance: Instance, arguments: list[str]) -> InstanceSettings`
- *staticmethod* `update_game_arguments(instance: Instance, arguments: list[str]) -> InstanceSettings`
### `mcw_core.api.java.java_major_policy`
#### `JavaMajorPolicy`
- *classmethod* `resolve(cls, required_major: int | None) -> int`
- *classmethod* `accepted_majors(cls, required_major: int | None) -> tuple[int, ...]`
### `mcw_core.api.lan.lan_agent_manager`
#### `LanAgentInstallResult`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `LanAgentManager`
Install and attach the bundled host-side LAN agent. The agent is intentionally narrow: it only changes ``MinecraftServer#setUsesAuthentication(boolean)`` inside the Minecraft client process. It never replaces Authlib and is attached only when the selected instance uses the explicit ``private_offline`` LAN policy.
- *classmethod* `is_enabled(cls, auth_mode: object) -> bool`
- *classmethod* `install(cls) -> LanAgentInstallResult`
- *classmethod* `runtime_arguments(cls, version: Version, auth_mode: object, instance: Instance, reporter: ProgressReporter | None = None) -> list[str]`
- *classmethod* `log_path(cls, instance: Instance) -> Path`
- *classmethod* `prepare_log(cls, instance: Instance, auth_mode: object = 'unknown') -> Path`
- *classmethod* `append_log(cls, instance: Instance, message: str) -> None`
- *staticmethod* `append_log_path(path: Path, message: str) -> None`
- *classmethod* `read_log(cls, instance: Instance) -> str`
- *classmethod* `sanitize_user_jvm_arguments(cls, arguments: list[str]) -> list[str]`
- *classmethod* `runtime_agent_path(cls) -> Path`
### `mcw_core.api.lan.lan_hosting_manager`
#### `LanHostingManager`
Prepare per-instance LAN hosting support. Authentication policy and connection transport are intentionally separate: * ``microsoft_only`` keeps vanilla session verification. * ``private_offline`` attaches MCW's bundled host-side Java agent when the game launches. The agent forces only the integrated Minecraft server to keep authentication disabled; Authlib and Microsoft tokens stay untouched. * ``manual`` leaves networking to LAN, VPN, port forwarding, or another relay. * ``e4mc`` installs e4mc as the current convenience tunnel provider. The agent is bundled and SHA-256 verified. Third-party connection components are downloaded as public release builds from Modrinth.
- *staticmethod* `normalize_auth_mode(value: object) -> str`
- *staticmethod* `normalize_connection_provider(value: object) -> str`
- *staticmethod* `plan(instance: Instance, auth_mode: object, connection_provider: object) -> LanHostingPlan`
- *staticmethod* `prepare(instance: Instance, auth_mode: object, connection_provider: object, reporter: ProgressReporter | None = None) -> LanHostingPrepareResult`
- *staticmethod* `disable_legacy_auth_bridges(instance: Instance) -> tuple[str, ...]`
### `mcw_core.api.language.language_manager`
#### `LanguageInfo`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `LanguageManager`
- *property* `current_locale(self) -> str`
- *property* `language_dir(self) -> Path`
- *property* `language_dirs(self) -> tuple[Path, ...]`
- `reload(self) -> list[LanguageInfo]`
- `available_languages(self) -> list[LanguageInfo]`
- `set_language(self, locale: str, notify: bool = True) -> bool`
- `resolve_key(self, key: str) -> str`
- `translate(self, key: str, default: str | None = None, **values: object) -> str`
- `has_key(self, key: str) -> bool`
- `missing_keys(self, locale: str | None = None) -> list[str]`
- `placeholder_mismatches(self, locale: str | None = None) -> dict[str, tuple[set[str], set[str]]]`
- `subscribe(self, listener: Callable[[str], None]) -> None`
- `unsubscribe(self, listener: Callable[[str], None]) -> None`
#### Function `tr(key: str, default: str | None = None, **values: object) -> str`
### `mcw_core.api.minecraft.version_manifest_manager`
#### `VersionManifestManager`
- *staticmethod* `get() -> list[VersionManifest]`
- *staticmethod* `latest_version(is_snapshot: bool = False) -> str`
### `mcw_core.api.mod.mod_compatibility_manager`
#### `ModCompatibilityManager`
- *staticmethod* `scan(instance: Instance, mods: list[ModInfo] | None = None) -> ModHealthReport`
### `mcw_core.api.mod.mod_manager`
#### `ModManager`
- *staticmethod* `mods_dir(instance: Instance) -> Path`
- *staticmethod* `list_mods(instance: Instance) -> list[ModInfo]`
- *staticmethod* `add_mods(instance: Instance, source_paths: Iterable[Path], replace: bool = False, launch_lock_token: str | None = None, allow_unverified: bool = False) -> list[ModInfo]`
- *staticmethod* `remove_mods(instance: Instance, paths: Iterable[Path]) -> None`
- *staticmethod* `set_enabled(instance: Instance, paths: Iterable[Path], enabled: bool) -> list[ModInfo]`
- *staticmethod* `read_mod(path: Path, preferred_loader: str = '', provider_version: str = '') -> ModInfo`
- *staticmethod* `validate_mod_for_instance(instance: Instance, mod: ModInfo, allow_unverified: bool = False) -> None`
- *staticmethod* `compatibility_warning(instance: Instance, mod: ModInfo) -> str`
- *staticmethod* `ensure_modifiable(instance: Instance, launch_lock_token: str | None = None) -> None`
### `mcw_core.api.mod.mod_provenance_registry`
#### `ModProvenanceRegistry`
Unified source identity for installed and manifest-managed mod files. Provider-specific registries remain authoritative for their own install and update workflows. This registry normalizes those records by destination file so the UI and future MCWPack exporter can recover provenance consistently.
- *staticmethod* `empty() -> dict`
- *staticmethod* `load(instance: Instance) -> dict`
- *staticmethod* `save(instance: Instance, data: dict) -> None`
- *staticmethod* `synchronize(instance: Instance) -> dict[str, dict]`
- *staticmethod* `entries_by_file(instance: Instance, synchronize: bool = True) -> dict[str, dict]`
- *staticmethod* `entry_for_file(instance: Instance, filename: str) -> dict | None`
- *staticmethod* `record_many(instance: Instance, entries: list[dict] | tuple[dict, ...]) -> None`
- *staticmethod* `remove_by_filenames(instance: Instance, filenames: list[str] | tuple[str, ...] | set[str]) -> tuple[str, ...]`
### `mcw_core.api.modloader.fabric.fabric_meta_client`
#### `FabricMetaClient`
- *staticmethod* `list_loader_versions(game_version: str, force_refresh: bool = False) -> list[FabricLoaderVersion]`
- *staticmethod* `get_install_metadata(game_version: str, loader_version: str, force_refresh: bool = False) -> FabricInstallMetadata`
- *staticmethod* `get_profile(game_version: str, loader_version: str, force_refresh: bool = False) -> dict`
- *staticmethod* `clear_cached_install(game_version: str, loader_version: str) -> None`
### `mcw_core.api.modloader.forge.forge_metadata_client`
#### `ForgeMetadataClient`
- *staticmethod* `list_versions(game_version: str, force_refresh: bool = False) -> list[ForgeLoaderVersion]`
- *staticmethod* `recommended_version(game_version: str) -> str`
- *staticmethod* `installer_url(game_version: str, forge_version: str) -> str`
- *staticmethod* `installer_sha1(game_version: str, forge_version: str) -> str`
### `mcw_core.api.modloader.mod_loader_manager`
#### `ModLoaderManager`
- *staticmethod* `load(instance: Instance, reporter: ProgressReporter | None = None) -> Version`
- *staticmethod* `prepare(version: Version, loader_name: str, loader_version: str, reporter: ProgressReporter | None = None) -> Version`
- *staticmethod* `repair(instance: Instance, reporter: ProgressReporter | None = None) -> Version`
- *staticmethod* `resolve(game_version: str, loader_name: str, loader_version: str = AUTO) -> tuple[str, str]`
- *staticmethod* `normalize(mod_loader: object) -> tuple[str, str]`
### `mcw_core.api.modloader.neoforge.neoforge_metadata_client`
#### `NeoForgeMetadataClient`
- *staticmethod* `list_versions(game_version: str, force_refresh: bool = False) -> list[NeoForgeLoaderVersion]`
- *staticmethod* `recommended_version(game_version: str) -> str`
- *staticmethod* `coordinate(game_version: str, neoforge_version: str) -> tuple[str, str]`
- *staticmethod* `installer_url(game_version: str, neoforge_version: str) -> str`
- *staticmethod* `installer_sha1(game_version: str, neoforge_version: str) -> str`
### `mcw_core.api.modloader.quilt.quilt_meta_client`
#### `QuiltMetaClient`
- *staticmethod* `list_loader_versions(game_version: str, force_refresh: bool = False) -> list[QuiltLoaderVersion]`
- *staticmethod* `version_sort_key(version: str) -> tuple`
- *staticmethod* `get_install_metadata(game_version: str, loader_version: str, force_refresh: bool = False) -> QuiltInstallMetadata`
- *staticmethod* `get_profile(game_version: str, loader_version: str, force_refresh: bool = False) -> dict`
- *staticmethod* `clear_cached_install(game_version: str, loader_version: str) -> None`
### `mcw_core.api.modrinth.modrinth_client`
#### `ModrinthClient`
- *staticmethod* `search_projects(project_type: str, query: str = '', game_version: str = '', loader: str = 'fabric', index: str = 'relevance', offset: int = 0, limit: int = 25, force_refresh: bool = False) -> ModrinthSearchResult`
- *staticmethod* `get_project(project_id: str, force_refresh: bool = False) -> ModrinthProject`
- *staticmethod* `list_project_versions(project_id: str, loader: str = 'fabric', game_version: str = '', version_types: tuple[str, ...] | list[str] | set[str] | None = None, force_refresh: bool = False) -> list[ModrinthVersion]`
- *staticmethod* `get_version(version_id: str, force_refresh: bool = False) -> ModrinthVersion`
- *staticmethod* `select_version(project_id: str, game_version: str, loader: str = 'fabric', version_types: tuple[str, ...] | list[str] | set[str] | None = None) -> ModrinthVersion`
- *staticmethod* `compatible_loaders(loader: str) -> tuple[str, ...]`
- *staticmethod* `normalize_version_types(version_types: tuple[str, ...] | list[str] | set[str] | None = None) -> tuple[str, ...]`
### `mcw_core.api.modrinth.modrinth_errors`
#### `ModrinthManagedFilesRequired` — bases: `RuntimeError`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `ModrinthModpackManualDownloadRequired` — bases: `RuntimeError`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
### `mcw_core.api.modrinth.modrinth_manual_installer`
#### `ModrinthManualInstaller`
- *staticmethod* `install(instance: Instance, requirement: ModrinthManualDownload, source: Path) -> str`
- *staticmethod* `install_many(instance: Instance, requirements: tuple[ModrinthManualDownload, ...] | list[ModrinthManualDownload], sources: tuple[Path, ...] | list[Path]) -> ModrinthManualImportResult`
### `mcw_core.api.modrinth.modrinth_mod_installer`
#### `ModrinthModInstaller`
- *staticmethod* `install(instance: Instance, version_id: str, install_dependencies: bool = True, allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None) -> ModrinthModInstallResult`
### `mcw_core.api.modrinth.modrinth_mod_update_manager`
#### `ModrinthModUpdateManager`
- *staticmethod* `check(instance: Instance, allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, force_refresh: bool = False, reporter: ProgressReporter | None = None) -> ModrinthModUpdateReport`
- *staticmethod* `update(instance: Instance, project_ids: list[str] | tuple[str, ...] | set[str], allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None) -> ModrinthModUpdateResult`
- *staticmethod* `update_all(instance: Instance, allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None) -> ModrinthModUpdateResult`
- *staticmethod* `set_locked(instance: Instance, project_ids: list[str] | tuple[str, ...] | set[str], locked: bool) -> tuple[str, ...]`
### `mcw_core.api.modrinth.modrinth_pack_installer`
#### `ModrinthPackInstaller`
- *staticmethod* `install(project_id: str, version_id: str, instance_name: str, install_optional_files: bool = True, allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None, expected_loader: str = '', settings_override: dict | None = None) -> ModrinthModpackInstallResult`
- *staticmethod* `install_local_archive(pack_path: Path, instance_name: str = '', install_optional_files: bool = True, reporter: ProgressReporter | None = None, settings_override: dict | None = None) -> ModrinthModpackInstallResult`
- *staticmethod* `install_manual_archive(request: ModrinthModpackManualDownloadRequired, source: Path, reporter: ProgressReporter | None = None) -> ModrinthModpackInstallResult`
- *staticmethod* `inspect(pack_path: Path) -> dict`
### `mcw_core.api.modrinth.modrinth_pack_registry`
#### `ModrinthPackRegistry`
- *staticmethod* `path(instance_dir: Path) -> Path`
- *staticmethod* `load(instance: Instance) -> dict`
- *staticmethod* `load_from_dir(instance_dir: Path) -> dict`
- *staticmethod* `save(instance_dir: Path, data: dict) -> None`
- *staticmethod* `scan(instance: Instance, reporter: ProgressReporter | None = None, force_hash: bool = False) -> ModrinthPackStateReport`
- *staticmethod* `verify_entry(instance_dir: Path, entry: dict, cache: dict | None = None, force_hash: bool = False) -> tuple[bool, bool, int]`
- *staticmethod* `build_verification_cache(instance_dir: Path, managed_files: list[dict]) -> dict`
### `mcw_core.api.modrinth.modrinth_pack_repair_manager`
#### `ModrinthPackRepairManager`
- *staticmethod* `repair(instance: Instance, reporter: ProgressReporter | None = None) -> ModrinthPackRepairResult`
### `mcw_core.api.modrinth.modrinth_pack_update_manager`
#### `ModrinthPackUpdateManager`
- *staticmethod* `check(instance: Instance, allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, force_refresh: bool = False, reporter: ProgressReporter | None = None) -> ModrinthPackUpdateInfo | None`
- *staticmethod* `preview(instance: Instance, target_version_id: str = '', allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None) -> ModrinthPackUpdatePlan`
- *staticmethod* `update(instance: Instance, target_version_id: str = '', allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None) -> ModrinthPackUpdateResult`
### `mcw_core.api.modrinth.modrinth_registry`
#### `ModrinthRegistry`
- *staticmethod* `load(instance: Instance) -> dict`
- *staticmethod* `empty() -> dict`
- *staticmethod* `save(instance: Instance, data: dict) -> None`
- *staticmethod* `set_locked(instance: Instance, project_ids: list[str] | tuple[str, ...] | set[str], locked: bool) -> tuple[str, ...]`
- *staticmethod* `remove_by_filenames(instance: Instance, filenames: list[str] | tuple[str, ...] | set[str]) -> tuple[str, ...]`
- *staticmethod* `entries_by_file(instance: Instance) -> dict[str, dict]`
- *staticmethod* `safe_tracked_path(instance: Instance, filename: str) -> Path | None`
### `mcw_core.api.network.download_bandwidth_limiter`
#### `DownloadBandwidthLimiter`
- *property* `limit_mbps(self) -> float`
- *property* `is_enabled(self) -> bool`
- `configure_mbps(self, value: object) -> float`
- `throttle(self, byte_count: int) -> None`
### `mcw_core.api.network.download_manager`
#### `DownloadManager`
- *property* `max_concurrent_downloads(self) -> int`
- *property* `per_host_limit(self) -> int`
- `configure(self, max_concurrent_downloads: object = DEFAULT_MAX_CONCURRENT_DOWNLOADS, per_host_limit: object | None = None) -> tuple[int, int]`
- `get_path_lock(self, path: Path) -> RLock`
- `download(self, request: DownloadRequest, reporter: ProgressReporter | None = None, progress_stage: ProgressStage | None = None, progress_message: str | None = None, client_provider = None) -> DownloadResult`
- `download_and_hash(self, url: str, path: Path, max_attempts: int = 2, timeout: float = 20.0, force: bool = False, reporter: ProgressReporter | None = None, progress_stage: ProgressStage | None = None, progress_message: str | None = None, client_provider = None) -> tuple[Path, str, int]`
- `verify(self, path: Path, expected_size: int, hashes: dict | object) -> bool`
- *staticmethod* `calculate_hash(path: Path, algorithm: str) -> str`
- `calculate_hashes(self, path: Path, expected: dict | object) -> dict[str, str]`
- *staticmethod* `content_length(response: httpx.Response, fallback: int) -> int`
- *staticmethod* `parse_content_range(response: httpx.Response) -> tuple[int, int, int | None] | None`
- *classmethod* `valid_content_range(cls, response: httpx.Response, expected_start: int, expected_size: int) -> bool`
- *classmethod* `content_range_total(cls, response: httpx.Response) -> int`
- *classmethod* `partial_size(cls, path: Path, expected_size: int) -> int`
- *staticmethod* `delete_file(path: Path) -> None`
- *staticmethod* `describe_error(error: Exception | None) -> str`
### `mcw_core.api.network.download_pause`
#### `DownloadInterruptedError` — bases: `RuntimeError`
Base class for cooperative download interruption requests.
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `DownloadPausedError` — bases: `DownloadInterruptedError`
Legacy terminal pause error kept for compatibility with older callers.
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `DownloadCancelledError` — bases: `DownloadPausedError`
Raised when the user cancels the active launcher download session.
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `DownloadPauseController`
- *property* `is_active(self) -> bool`
- *property* `is_pause_requested(self) -> bool`
- *property* `is_paused(self) -> bool`
- *property* `is_cancel_requested(self) -> bool`
- `begin(self) -> None`
- `finish(self) -> None`
- `request_pause(self) -> bool`
- `request_resume(self) -> bool`
- `request_cancel(self) -> bool`
- `raise_if_requested(self) -> None`
- `wait(self, seconds: float) -> None`
#### Function `is_download_paused(error: BaseException | None) -> bool`
#### Function `is_download_cancelled(error: BaseException | None) -> bool`
### `mcw_core.api.network.network_session`
#### `NetworkSession`
- *property* `max_concurrent_downloads(self) -> int`
- `configure(self, max_concurrent_downloads: object = DEFAULT_MAX_CONCURRENT_DOWNLOADS) -> int`
- `get_client(self) -> httpx.Client`
- `close(self) -> None`
### `mcw_core.api.package.portable_content_manager`
#### `PortableManualDownloadRequired` — bases: `RuntimeError`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `PortableContentManager`
- *staticmethod* `ensure(instance: Instance) -> None`
- *staticmethod* `prefetch_referenced(instance: Instance, reporter: ProgressReporter | None = None) -> None`
- *staticmethod* `finalize_disabled(instance: Instance) -> None`
- *staticmethod* `install_many(instance: Instance, requirements: tuple[PortableManualDownload, ...] | list[PortableManualDownload], sources: tuple[Path, ...] | list[Path]) -> tuple[str, ...]`
### `mcw_core.api.progress.progress_reporter`
#### `ProgressReporter`
- `report(self, stage: ProgressStage, message: str, current: int | None = None, total: int | None = None, unit: ProgressUnit = ProgressUnit.NONE, bytes_per_second: float | None = None, state: ProgressState = ProgressState.RUNNING, detail: str = '') -> None`
- `status(self, stage: ProgressStage, message: str) -> None`
- `bytes(self, stage: ProgressStage, message: str, current: int, total: int, bytes_per_second: float | None = None) -> None`
- `files(self, stage: ProgressStage, message: str, current: int, total: int, bytes_per_second: float | None = None) -> None`
- `steps(self, stage: ProgressStage, message: str, current: int, total: int) -> None`
- `succeeded(self, stage: ProgressStage, message: str, detail: str = '') -> None`
- `failed(self, stage: ProgressStage, message: str, detail: str = '') -> None`
- `cancelled(self, stage: ProgressStage, message: str, detail: str = '') -> None`
- *contextmanager* `task(self, stage: ProgressStage, start_message: str, success_message: str, failure_message: str) -> Iterator[None]`
### `mcw_core.api.repair.repair_service`
#### `RepairService`
- *classmethod* `scan(cls, instance: Instance, mode: RepairMode | str = RepairMode.QUICK, components: Iterable[RepairComponent | str] | None = None, on_progress: ProgressCallback | None = None) -> RepairReport`
- *classmethod* `build_plan(cls, report: RepairReport, components: Iterable[RepairComponent | str] | None = None) -> RepairPlan`
- *classmethod* `repair(cls, instance: Instance, plan: RepairPlan, on_progress: ProgressCallback | None = None) -> RepairExecutionResult`
### `mcw_core.api.runtime.game_runtime_manager`
#### `GameRuntimeManager`
- *classmethod* `watch(cls, process: object, instance: Instance, minecraft_version: str, started_at: datetime, on_exit: GameExitCallback | None = None, session_id: str | None = None, crash_report_snapshot: Mapping[str, tuple[int, int]] | None = None) -> bool`
- *classmethod* `stop(cls, instance: Instance, graceful_timeout: float = 2.5) -> bool`
- *staticmethod* `latest_game_log(instance: Instance) -> Path | None`
- *staticmethod* `crash_report_snapshot(instance: Instance) -> dict[str, tuple[int, int]]`
- *staticmethod* `latest_crash_report(instance: Instance, since: datetime | None = None, previous: Mapping[str, tuple[int, int]] | None = None) -> Path | None`
- *classmethod* `record_start(cls, instance: Instance, started_at: datetime, session_id: str | None) -> None`
### `mcw_core.api.runtime.process_supervisor`
#### `ProcessSupervisor`
Persist and supervise Minecraft process sessions without touching unrelated Java processes.
- *classmethod* `begin(cls, instance: Instance) -> ProcessSession`
- *classmethod* `attach(cls, session_id: str, process: object) -> ProcessSession`
- *classmethod* `register_child(cls, session_id: str, pid: int) -> ProcessSession`
- *classmethod* `finish(cls, session_id: str, exit_code: int, crashed: bool, detail: str = '') -> ProcessSession | None`
- *classmethod* `abort(cls, session_id: str, detail: str = '') -> ProcessSession | None`
- *classmethod* `stop_requested(cls, session_id: str | None) -> bool`
- *classmethod* `active_for(cls, instance: Instance) -> ProcessSession | None`
- *classmethod* `list_active(cls) -> tuple[ProcessSession, ...]`
- *classmethod* `stop_process(cls, process: object, graceful_timeout: float = 2.5) -> bool`
- *classmethod* `stop_instance(cls, instance: Instance, graceful_timeout: float = 2.5) -> bool`
- *classmethod* `reconcile(cls) -> tuple[str, ...]`
- *classmethod* `load(cls, session_id: str) -> ProcessSession`
### `mcw_core.api.runtime.startup_recovery_manager`
#### `StartupRecoveryReport`
- *property* `recovered_item_count(self) -> int`
#### `StartupRecoveryManager`
- *staticmethod* `reconcile() -> StartupRecoveryReport`
### `mcw_core.api.security.account_security_manager`
#### `AccountSecurityManager`
- *classmethod* `audit(cls) -> AccountSecurityReport`
- *classmethod* `migrate_if_needed(cls) -> AccountSecurityReport`
- *classmethod* `migrate_and_reprotect(cls) -> AccountSecurityReport`
### `mcw_core.api.security.sensitive_data_redactor`
#### `SensitiveDataRedactor`
- *classmethod* `redact_text(cls, value: object) -> str`
- *classmethod* `redact_value(cls, value: Any, key: str = '') -> Any`
- *classmethod* `redact_json(cls, value: Any) -> str`
### `mcw_core.api.startup_runner`
#### `StartupTimeoutError` — bases: `RuntimeError`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `StartupWorkerError` — bases: `RuntimeError`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### Function `run_startup_task(task: StartupTask, on_progress: StartupProgressHandler, pump_events: EventPump, timeout_seconds: float = 45.0) -> Any`
### `mcw_core.api.system.memory`
#### `SystemMemory`
- *classmethod* `total_physical_memory_mb(cls) -> int`
#### `MemoryAllocationPolicy`
- *classmethod* `physical_limit_mb(cls, total_memory_mb: int | None = None) -> int`
- *classmethod* `normalize(cls, min_memory_mb: object, max_memory_mb: object, total_memory_mb: int | None = None) -> tuple[int, int]`
- *classmethod* `is_valid(cls, min_memory_mb: object, max_memory_mb: object, total_memory_mb: int | None = None) -> bool`
- *classmethod* `snap_mb(cls, memory_mb: object, upper_bound_mb: int) -> int`
- *staticmethod* `format_mb(memory_mb: int) -> str`
### `mcw_core.api.theme.theme_animation`
#### `ThemeAnimationDefinition`
- *property* `rows(self) -> int`
#### `ResolvedThemeAnimation`
- *property* `key(self) -> str`
### `mcw_core.api.theme.theme_authoring`
#### `ThemeAuthoringError` — bases: `RuntimeError`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `ThemeAuthoringService`
- `validate(self, theme_id: str) -> ThemeValidationReport`
- `validate_directory(self, root: Path) -> ThemeValidationReport`
- `duplicate(self, theme_id: str, new_id: str, new_name: str | None = None) -> ThemeDefinition`
- `export(self, theme_id: str, destination: Path) -> Path`
- `import_archive(self, archive_path: Path, overwrite: bool = False) -> ThemeDefinition`
### `mcw_core.api.theme.theme_font`
#### `ThemeFontDefinition`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `ResolvedThemeFont`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
### `mcw_core.api.theme.theme_manager`
#### `ThemeError` — bases: `RuntimeError`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `ThemeManifestError` — bases: `ThemeError`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `ThemeAssetError` — bases: `ThemeError`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `ThemeDefinition`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `ThemeManager`
- *property* `current(self) -> ThemeDefinition`
- `reload(self) -> tuple[ThemeDefinition, ...]`
- `available_themes(self) -> tuple[ThemeDefinition, ...]`
- `select(self, theme_id: str) -> ThemeDefinition`
- `resolve_asset(self, key: str, theme: ThemeDefinition | None = None, fallback_to_default: bool = False) -> Path | None`
- `resolve_text_asset(self, role: str, theme: ThemeDefinition | None = None, fallback_to_default: bool = False) -> Path | None`
- `resolve_animation(self, key: str, theme: ThemeDefinition | None = None, fallback_to_default: bool = True) -> ResolvedThemeAnimation | None`
- `resolve_animation_fallback(self, key: str, theme: ThemeDefinition | None = None, fallback_to_default: bool = True) -> Path | None`
- `resolve_font(self, theme: ThemeDefinition | None = None, fallback_to_default: bool = True) -> ResolvedThemeFont | None`
- `resolve_palette(self, theme: ThemeDefinition | None = None) -> ThemePaletteDefinition`
- `is_accent_asset(self, key: str, theme: ThemeDefinition | None = None) -> bool`
- `resolve_stylesheet(self, theme: ThemeDefinition | None = None) -> str`
- `asset_status(self, theme: ThemeDefinition | None = None) -> dict[str, bool]`
- `animation_status(self, theme: ThemeDefinition | None = None) -> dict[str, bool]`
- `font_status(self, theme: ThemeDefinition | None = None) -> bool`
### `mcw_core.api.theme.theme_motion`
#### `MotionTransitionDefinition`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `ButtonMotionDefinition`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `SidebarMotionDefinition`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `ToastMotionDefinition`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `MotionPerformanceDefinition`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `ThemeMotionDefinition`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
### `mcw_core.api.theme.theme_palette`
#### `ThemePaletteDefinition`
- `to_dict(self) -> dict[str, str]`
#### Function `normalize_hex_color(value: object, label: str = 'color') -> str`
#### Function `derive_custom_accent(theme_palette: ThemePaletteDefinition, accent: str) -> ThemePaletteDefinition`
### `mcw_core.api.update.update_applier`
#### `UpdateApplyRequest`
- *classmethod* `load(cls, path: Path) -> 'UpdateApplyRequest'`
- `validate(self) -> None`
#### `UpdateApplier`
- `run(self) -> int`
#### Function `run_update_applier(request_path: Path) -> int`
### `mcw_core.api.update.update_cleanup`
#### `UpdateCleanupRequest`
- `validate(self) -> None`
#### `UpdateCleanupWorker`
- `start(self) -> threading.Thread`
- `run(self) -> None`
#### Function `consume_update_cleanup_arguments(arguments: list[str]) -> tuple[list[str], UpdateCleanupRequest | None]`
### `mcw_core.api.update.update_manager`
#### `UpdateManager`
- `check_for_update(self, force_refresh: bool = False) -> UpdateInfo | None`
- `prepare_update(self, info: UpdateInfo, reporter: ProgressReporter | None = None) -> PreparedUpdate`
### `mcw_core.api.update.windows_update_installer`
#### `AutomaticUpdateUnsupportedError` — bases: `RuntimeError`
No public methods declared in this class body; inspect its dataclass fields or exception attributes as applicable.
#### `WindowsUpdateInstaller`
- *staticmethod* `is_supported() -> bool`
- *classmethod* `launch(cls, prepared: PreparedUpdate, install_directory: Path | None = None, executable_path: Path | None = None, parent_pid: int | None = None, persistent_log_path: Path | None = None) -> Path`
---

## Final compatibility notes

- The wheel reports `mcw_core.__version__ == "1.0.0"`.
- Python 3.12+ is required by package metadata.
- Windows-only features, including DPAPI account protection, registry-based GPU preference, and the automatic executable updater, should be feature-detected.
- The wheel currently ships compatibility implementation modules under `src`. Third-party launchers should still code against `mcw_core` and `mcw_core.api`.
- Provider availability, schemas, and policies can change independently of the core library. Handle API failures, rate limits, unavailable automatic download URLs, and manual-download workflows explicitly.
- `MCWCore.launch()` returning successfully means the game process was created; it does not mean the game has exited successfully.
