# MCW Core v1.5.0 Public API Overview

## Recommended import level

For most launchers:

```python
from mcw_core import CorePaths, InstanceCreateRequest, LaunchRequest, MCWCore
```

Use `mcw_core.api.*` only when the facade does not expose the specialized operation you
need.

## Stable facade

### `MCWCore`

`MCWCore` owns the configured Core paths and creates the principal services:

- `core.instances` -> `InstanceService`
- `core.loaders` -> `LoaderService`
- `core.java` -> `JavaService`
- `core.optifine` -> `OptiFineService`
- `core.operations` -> `OperationHandle`
- `core.launch(request)` -> `LaunchResult`

### Request/result models

- `InstanceCreateRequest`: instance name, Minecraft version, loader and progress callback.
- `InstanceRuntimeProfile`: resolved loader and Java runtime requirements for an instance.
- `LaunchRequest`: instance, identity, callbacks and launch compatibility controls.
- `LaunchResult`: selected Java path, Java major, Minecraft version and warnings.

### `InstanceService`

Provides the common lifecycle operations: list/load/create, status/health, icon/library
metadata, Java selection, loader change/repair, clone/rename/delete, package import/export,
modpack import/export and portable manual-file installation.

### `LoaderService`

Normalizes and resolves Vanilla/Fabric/Forge/NeoForge/Quilt selections and prepares loader
metadata.

### `JavaService`

Scans installed Java runtimes, normalizes Java feature versions and installs managed
Adoptium runtimes.

### `OptiFineService`

Inspects an OptiFine JAR, reports state/compatibility, installs, repairs and uninstalls.

### `OperationHandle`

Provides cooperative `begin`, `finish`, `pause`, `resume`, `cancel` and `checkpoint`
controls for long-running operations.

## Granular public namespaces

| Namespace | Main responsibility |
|---|---|
| `mcw_core.api.account` | account persistence and skin state |
| `mcw_core.api.auth.microsoft` | Microsoft authentication gate and OAuth callback server |
| `mcw_core.api.backup` | instance backups |
| `mcw_core.api.config` | launcher/provider policy configuration |
| `mcw_core.api.content` | content packs and installed content library |
| `mcw_core.api.curseforge` | CurseForge metadata, links, registry and installers |
| `mcw_core.api.modrinth` | Modrinth metadata, registry, installers, repair/update |
| `mcw_core.api.ftb` | FTB search, versions, content and pack install |
| `mcw_core.api.atlauncher` | ATLauncher search, versions, content and pack install |
| `mcw_core.api.instance` | advanced instance lifecycle, health, settings and run locks |
| `mcw_core.api.java` | Java compatibility policy |
| `mcw_core.api.modloader` | loader metadata and compatibility confirmation |
| `mcw_core.api.mod` | mod operations, compatibility and provenance |
| `mcw_core.api.network` | sessions, connectivity, downloads and pause/cancel |
| `mcw_core.api.package` | portable content workflows |
| `mcw_core.api.repair` | repair scans/plans/execution |
| `mcw_core.api.runtime` | game runtime, process supervision and startup recovery |
| `mcw_core.api.security` | account security and redaction |
| `mcw_core.api.storage` | shared content store and storage migration/cleanup |
| `mcw_core.api.update` | update checking/preparation/apply and platform installers |
| `mcw_core.api.theme` | theme runtime, palette, fonts, motion, animation and authoring |
| `mcw_core.api.language` | language packs/runtime |
| `mcw_core.api.lan` | bundled LAN Agent and LAN hosting support |
| `mcw_core.api.hardware` | first-run recommendations and GPU preferences |
| `mcw_core.api.diagnostics` | diagnostics bundles and issue-report generation |

For exact signatures, classes and methods, use [en/API_REFERENCE.md](en/API_REFERENCE.md)
or [vi/API_REFERENCE.md](vi/API_REFERENCE.md).
