# Complete MCW Core 1.0.1 Guide

## 1. Purpose

This guide explains how to use MCW Core as the backend of an independent Minecraft launcher. It covers data roots, bootstrap, instances, Java, accounts, loaders, launch, progress, pause/cancel, provider workflows, native package import, portable export, content management, repair, backup, diagnostics, recovery, threading and error handling.

## 2. Installation

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install .\mcw_core-1.0.1-py3-none-any.whl
python -c "import mcw_core; print(mcw_core.__version__)"
```

Dependencies: Python 3.12+, httpx, requests, and pywin32 on Windows. PySide6 is not a core dependency.

### Packaging note

The public contract is `mcw_core` and `mcw_core.api`. The current wheel still carries compatibility implementation modules under `src`. Consumers must not import those modules directly. The reduced core source snapshot does not run by itself unless the compatible implementation packages are also present. See [PACKAGING_RELEASE.md](PACKAGING_RELEASE.md).

## 3. Public surface

Preferred facade imports:

```python
from mcw_core import CorePaths, MCWCore, LaunchRequest, InstanceCreateRequest
```

Granular public modules:

```python
from mcw_core.api.account.account_manager import AccountManager
from mcw_core.api.modrinth.modrinth_client import ModrinthClient
```

Never build third-party code against `src.core`, `src.models`, `src.database`, or `src.gui`.

## 4. Data root

```python
from pathlib import Path
from mcw_core import CorePaths, MCWCore

core = MCWCore(CorePaths.from_root(Path.home() / "MyLauncherData"))
```

The root contains cache, instances, accounts, config, logs, backups, themes and runtimes. Path configuration is process-wide; use one active root per process.

## 5. Bootstrap

```python
from mcw_core.api.bootstrap import initialize_application

settings = initialize_application(lambda percent, key: print(percent, key))
```

Bootstrap creates directories, reconciles interrupted instance/process operations, loads settings, configures downloads, recovers partial downloads, initializes the account database and runs security migration. It returns normalized launcher settings.

## 6. Progress

```python
from mcw_core import ProgressEvent

def on_progress(event: ProgressEvent) -> None:
    print(event.stage.value, event.message)
    if event.is_determinate:
        print(event.current, event.total, event.percentage)
    if event.bytes_per_second:
        print(event.bytes_per_second)
```

`ProgressEvent` fields: stage, message, current, total, unit, bytes_per_second, state and detail. Properties: remaining, fraction, percentage, is_determinate and is_terminal.

A successful function return is the authoritative task success signal. Some legacy flows report a `FINISHED` stage while the event state remains `RUNNING`.

## 7. Instances

```python
for instance in core.instances.list():
    print(instance.name, instance.version_id, instance.mod_loader)
```

Create:

```python
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

Other operations:

```python
core.instances.load("Fabric 1.21.1")
core.instances.rename("Fabric 1.21.1", "Main Pack")
core.instances.clone("Main Pack", "Copy", include_saves=False)
core.instances.delete("Copy")
core.instances.set_icon("Main Pack", Path("icon.png"))
```

Status and health:

```python
status = core.instances.status("Main Pack")
health = core.instances.health("Main Pack")
```

Status is runtime state. Health is persistent integrity state.

## 8. Instance settings

```python
from mcw_core.api.instance.settings_manager import SettingsManager

settings = SettingsManager.load(instance)
settings.min_memory = 2048
settings.max_memory = 8192
settings.width = 1280
settings.height = 720
SettingsManager.save(instance, settings)
```

Settings include Java path, RAM, JVM/game arguments, LAN options, provider failure policies, resolution and fullscreen.

## 9. Minecraft versions

```python
from mcw_core.api.minecraft.version_manifest_manager import VersionManifestManager

versions = VersionManifestManager.get()
latest = VersionManifestManager.latest_version(False)
```

The manager refreshes Mojang metadata and falls back to cache when possible.

## 10. Java, memory and GPU

```python
java_diagnostics = core.java.scan(on_progress)
javaw = core.java.install(21, on_progress, force=False)
```

```python
from mcw_core.api.system.memory import SystemMemory, MemoryAllocationPolicy

total = SystemMemory.total_physical_memory_mb()
minimum, maximum = MemoryAllocationPolicy.normalize(1024, 8192, total)
```

```python
from mcw_core.api.hardware.gpu_preference_manager import GpuPreferenceManager

detection = GpuPreferenceManager.detect()
if detection.has_dedicated_gpu:
    GpuPreferenceManager.apply_to_java(javaw, True)
```

The GPU preference is best-effort. Windows and the driver retain the final decision.

## 11. Accounts

```python
from mcw_core.api.account.account_manager import AccountManager

account = AccountManager.create_offline_account("Player")
AccountManager.set_selected_account(account.account_id)
```

Microsoft login:

```python
from mcw_core.api.auth.microsoft.microsoft_auth_gate import MicrosoftAuthenticationGate

if MicrosoftAuthenticationGate.availability().enabled:
    account = AccountManager.create_microsoft_account()
```

Microsoft login is blocking and should run in a worker thread. Never log token fields from `Account` or `Authentication`.

## 12. Loaders

```python
resolved = core.loaders.resolve("1.21.1", "fabric", "auto")
prepared, resolved = core.loaders.prepare("1.21.1", "fabric", "auto", on_progress)
core.instances.change_loader("Main Pack", "neoforge", "auto", on_progress)
```

Supported loader names: vanilla, fabric, quilt, forge and neoforge.

## 13. Launch

Offline:

```python
result = core.launch(
    LaunchRequest(
        instance="Main Pack",
        offline_username="Player",
        on_progress=on_progress,
        on_exit=lambda exit_result: print(exit_result.to_dict()),
    )
)
```

Stored account:

```python
account = AccountManager.get_selected_account()
result = core.launch(LaunchRequest(instance="Main Pack", account=account, on_progress=on_progress, on_exit=on_exit))
```

`LaunchResult` exposes Java path, compatibility Java major, resolved Minecraft version and warnings. It also behaves like the legacy mapping returned by the old executor.

`launch()` returns after the Minecraft process is created and watched. It does not wait for the game to close. `on_exit` receives `GameExitResult` later.

## 14. Pause, resume and cancel

For UI-controlled operations:

```python
core.operations.begin()
try:
    result = core.launch(request)
finally:
    core.operations.finish()
```

From another thread:

```python
core.operations.pause()
core.operations.resume()
core.operations.cancel()
```

Pause is cooperative and affects checkpoints/downloaders. To stop an already running game, call `ProcessSupervisor.stop_instance(instance)`.

## 15. Mods

```python
from mcw_core.api.mod.mod_manager import ModManager
from mcw_core.api.mod.mod_compatibility_manager import ModCompatibilityManager

mods = ModManager.list_mods(instance)
added = ModManager.add_mods(instance, [Path("example.jar")])
ModManager.set_enabled(instance, [added[0].path], False)
health = ModCompatibilityManager.scan(instance)
```

`ModInfo` includes loader metadata, dependencies, license fields and provider provenance.

## 16. Modrinth

```python
from mcw_core.api.modrinth.modrinth_client import ModrinthClient
from mcw_core.api.modrinth.modrinth_mod_installer import ModrinthModInstaller
from mcw_core.api.progress.progress_reporter import ProgressReporter

search = ModrinthClient.search_projects("mod", "sodium", "1.21.1", "fabric", "downloads")
versions = ModrinthClient.list_project_versions(search.projects[0].project_id, "fabric", "1.21.1", ("release",))
result = ModrinthModInstaller.install(instance, versions[0].version_id, True, reporter=ProgressReporter(on_progress))
```

## 17. CurseForge

```python
from mcw_core.api.curseforge.curseforge_client import CurseForgeClient
from mcw_core.api.curseforge.curseforge_mod_installer import CurseForgeModInstaller

search = CurseForgeClient.search_projects("mod", "jei", "1.20.1", "forge")
files = CurseForgeClient.list_files(search.projects[0].project_id, "1.20.1", "forge", ("release",))
result = CurseForgeModInstaller.install(instance, search.projects[0].project_id, files[0].file_id, reporter=ProgressReporter(on_progress))
```

Files without automatic distribution must enter the manual-download workflow. Do not bypass provider restrictions.

## 18. FTB

```python
from mcw_core.api.ftb.ftb_client import FTBClient
from mcw_core.api.ftb.ftb_pack_installer import FTBPackInstaller

projects = FTBClient.search_projects("academy")
versions = FTBClient.list_versions(projects.projects[0].project_id, ("release",))
result = FTBPackInstaller.install(projects.projects[0].project_id, versions[0].version_id, "FTB Pack", reporter=ProgressReporter(on_progress))
```

## 19. Native import and portable export

```python
preview = core.instances.inspect_modpack_package(Path("pack.mrpack"))
instance = core.instances.import_modpack_package(
    Path("pack.mrpack"),
    on_progress=on_progress,
    settings_override={"min_memory": 2048, "max_memory": 8192},
    instance_name="Imported Pack",
)
```

Export provider profile:

```python
result = core.instances.export_modpack("Imported Pack", Path("profile.zip"), mode="provider_profile", on_progress=on_progress)
```

Export portable package:

```python
result = core.instances.export_modpack("Imported Pack", Path("portable.mcwpack"), mode="portable", portable_mode="smart", on_progress=on_progress)
```

Smart export separates referenced, legally embeddable and manual-download files. Full export is intended for private/offline use and still does not grant redistribution rights.

## 20. Manual downloads

Catch structured exceptions such as `PortableManualDownloadRequired`, `ModrinthManagedFilesRequired` and `CurseForgeManagedFilesRequired`. Open official pages, let the user select downloaded files, then verify hashes using the corresponding manual installer or `core.instances.install_portable_manual_files()`.

## 21. Resource packs, shaders and content library

```python
from mcw_core.api.content.content_pack_manager import ContentPackManager
from mcw_core.api.content.installed_content_library import InstalledContentLibraryManager

ContentPackManager.import_local(instance, "resourcepack", Path("pack.zip"))
library = InstalledContentLibraryManager.scan(instance)
```

## 22. Backup, repair and diagnostics

```python
from mcw_core.api.backup.instance_backup_manager import InstanceBackupManager
backup = InstanceBackupManager.create(instance, scope="full")
```

```python
from mcw_core.api.repair.repair_service import RepairService
report = RepairService.scan(instance, "quick", on_progress=on_progress)
plan = RepairService.build_plan(report)
result = RepairService.repair(instance, plan, on_progress=on_progress) if plan.can_repair else None
```

```python
from mcw_core.api.diagnostics.diagnostics_manager import DiagnosticsManager
DiagnosticsManager.write_bundle(Path("diagnostics.zip"), "1.0.0", settings, activity_log)
```

## 23. Runtime supervision and recovery

```python
from mcw_core.api.runtime.startup_recovery_manager import StartupRecoveryManager
from mcw_core.api.runtime.process_supervisor import ProcessSupervisor

recovery = StartupRecoveryManager.reconcile()
active = ProcessSupervisor.list_active()
```

## 24. GUI threading

Core I/O operations are blocking. Run them on a worker thread. Progress callbacks execute in the worker context and must be marshalled to the UI thread. See [PROGRESS_ASYNC.md](PROGRESS_ASYNC.md), [BUILD_A_LAUNCHER.md](BUILD_A_LAUNCHER.md), and the PySide6 example.

## 25. Error handling

Catch structured cancellation/manual-download exceptions before general `RuntimeError`/`OSError`. Never parse exception text when a typed exception exposes fields.

## 26. Complete launcher checklist

A production launcher should implement bootstrap, task runner, progress, account selection, instance library, version/loader selection, Java and memory setup, launch/pause/cancel, manual download UI, exit/crash handling, persistent settings, repair/diagnostics, startup recovery, update flow, redaction and localization.
