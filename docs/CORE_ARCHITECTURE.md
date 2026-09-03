# MCW Core v1.5.0 Architecture

## 1. Architectural goal

MCW Core is the GUI-independent runtime behind MCW Launcher. The Core owns Minecraft
state, provider integration, installation, repair and launch behavior while leaving
presentation, widgets and user interaction to the host launcher.

The main compatibility rule is simple:

```text
GUI / CLI / external launcher
          |
          v
   mcw_core public API
    |             |
    |             +-- mcw_core.api.* granular modules
    v
 MCWCore facade + services
          |
          v
 src.core implementation
          |
          v
 src.models domain objects + filesystem/network/runtime resources
```

Consumers should not import `src.core.*` or `src.models.*` directly. Those packages are
implementation details and can evolve without the public compatibility guarantees of
`mcw_core` and `mcw_core.api.*`.

## 2. Public layers

### 2.1 `mcw_core`

The top-level package is the stable, small facade. It exposes:

- `MCWCore`
- `CorePaths`
- `LaunchRequest`, `LaunchResult`
- `InstanceCreateRequest`, `InstanceRuntimeProfile`
- `OperationHandle`, `OperationState`
- `InstanceService`, `LoaderService`, `JavaService`, `OptiFineService`
- common domain models, progress models and common exceptions.

Use this layer for normal launcher integration.

### 2.2 `mcw_core.api.*`

The granular public namespace re-exports selected implementation modules. It is for
launchers that need provider-specific, repair, update, theme, network or advanced
instance operations that are intentionally not compressed into the main facade.

The v1.5.0 source contains public modules across these domains:

- account, authentication and security
- bootstrap and startup
- instance, backup and diagnostics
- Minecraft metadata and mod loaders
- Java, hardware and memory
- mods and installed content
- Modrinth, CurseForge, FTB and ATLauncher
- network, download control and connectivity
- package/portable content
- runtime supervision and recovery
- shared storage and migration
- update installers
- language and theme runtime
- LAN hosting support

## 3. Process-wide path registry

`CorePaths.apply()` configures the internal `Paths` registry used throughout the
implementation. This means one Python process should normally operate on one active MCW
Core root at a time.

A host can explicitly create a portable root:

```python
from mcw_core import CorePaths, MCWCore

core = MCWCore(CorePaths.from_root('./mcw-data'))
```

On Linux, launcher bootstrap may choose XDG roots. Explicit `CorePaths` configuration
remains portable and overrides that launcher-oriented default selection.

## 4. Main runtime subsystems

### Instance subsystem

The instance subsystem owns creation, metadata, settings, loader changes, status, health,
clone/rename/delete, import/export, run locks and operation journaling. Destructive or
loader-changing operations are guarded against active instances where appropriate.

### Minecraft and loader subsystem

Minecraft metadata and assets are resolved separately from mod-loader preparation. The
loader manager normalizes Vanilla/Fabric/Quilt/Forge/NeoForge choices and dispatches to
provider-specific installation logic. Forge-family workflows have additional
compatibility confirmation and recovery logic.

### Java subsystem

Java resolution combines Minecraft/loader compatibility policy, locally discovered Java
installations and managed Adoptium runtimes. The Core can select or provision Java 8,
16, 17 or 21 where required by the game/loader pipeline.

### Provider/content subsystem

Provider clients expose normalized search and metadata operations. Installers then apply
provider-specific manifests transactionally to instances. v1.5.0 includes Modrinth,
CurseForge, FTB and ATLauncher integrations, plus portable/manual-content fallbacks.

### Runtime subsystem

Launch preparation resolves identity, Java, classpath, natives, game arguments and
provider-managed content before handing the game process to runtime supervision.
Instance run locks prevent conflicting management operations. Startup recovery repairs
stale state left by interrupted operations.

### Network subsystem

Network code centralizes sessions, retries, downloads, pause/cancel checkpoints,
bandwidth limiting, recovery journals and connectivity snapshots. Provider metadata
caches remain separate from binary shared content storage.

### Storage subsystem

The shared content store is SHA-256 addressed. Materialization can adopt and reuse files,
preferring hard links where safe. Legacy storage migration/cleanup is conservative and
revalidates references before deletion.

### Update subsystem

Update metadata is checked and prepared by `UpdateManager`. `AutomaticUpdateInstaller`
dispatches to platform-specific installer behavior. v1.5.0 includes Windows and Linux
automatic update support with package verification and rollback-oriented workflows.

## 5. Progress and cancellation

Long-running Core operations use structured `ProgressEvent` callbacks. Cooperative pause,
resume and cancel are controlled through `OperationHandle`, backed by the shared download
pause controller. Code performing long operations must continue to reach pause/cancel
checkpoints; cancellation is not a thread kill.

## 6. Security boundary

Account credentials are not ordinary configuration. The account/security subsystem is
responsible for platform credential protection, integrity checks and redaction. On Linux,
Secret Service/keyring integration is used when available. Diagnostics and issue reports
should pass sensitive values through the redaction layer.

CurseForge API credentials are intentionally not bundled. The optional gateway archive is
source only; a deployment supplies its own API key and HTTPS gateway URL.

## 7. Platform model

### Windows

The stable runtime keeps the established launcher storage layout when no explicit root is
selected. Short temporary workspaces are used for path-sensitive Java/loader/package
operations. Windows-specific update and GPU preference helpers remain available.

### Linux

The launcher bootstrap supports XDG roots:

- config: `$XDG_CONFIG_HOME/mcw-launcher` or `~/.config/mcw-launcher`
- data: `$XDG_DATA_HOME/mcw-launcher` or `~/.local/share/mcw-launcher`
- cache: `$XDG_CACHE_HOME/mcw-launcher` or `~/.cache/mcw-launcher`
- state/logs: `$XDG_STATE_HOME/mcw-launcher` or `~/.local/state/mcw-launcher`

Set `MCW_PORTABLE=1` to keep launcher-oriented bootstrap in portable mode. Explicit
`CorePaths.from_root(...)` is always the clearest choice for headless integrations.

## 8. Source layout

```text
mcw_core/             stable facade, models, services and public re-export namespace
src/core/             implementation subsystems
src/models/           domain data models
examples/             runnable integration examples
test/                 distribution contract tests
docs/                 guides, schemas and generated API reference
runtime/               bundled LAN Agent JAR
tools/                 release, validation and documentation tooling
mcw-curseforge-gateway-main.zip  optional gateway source
```

## 9. Compatibility rules for contributors

1. Add normal launcher-facing behavior to `mcw_core` when it belongs in the stable facade.
2. Add specialized but supported behavior under `mcw_core.api.*`.
3. Keep internal helper modules under `src.core`/`src.models` unless they are deliberately
   promoted through the public namespace.
4. Preserve existing public signatures or document a migration path.
5. Update the generated API reference after adding/removing a public module.
6. Keep the Core headless: no PySide6 dependency in the package runtime.
7. Do not bundle secrets, provider API keys or a deployed CurseForge gateway endpoint.
