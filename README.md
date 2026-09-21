# MCW Core 1.6.0

MCW Core is the headless runtime shipped with MCW Launcher `v1.6.0`. This source distribution contains the complete public API, implementation, data models, tests, documentation, examples and LAN Agent resource. The separate CurseForge gateway source archive is intentionally not bundled with MCW Core.

PySide6 and the launcher GUI are intentionally not part of the Core distribution.

## What changed in 1.6.0

- **Quick Play support**: `LaunchRequest` now accepts `quick_play_singleplayer` and `quick_play_multiplayer` to launch directly into a world or server, and `on_window_ready` to receive the game window handle.
- **JVM arguments via API**: `InstanceCreateRequest` accepts `jvm_arguments: tuple[str, ...]` to set custom JVM flags when creating an instance programmatically.
- **Discord RPC integration**: new `mcw_core.api.integrations.discord` module exposes the Discord Rich Presence bridge.
- **New public API modules**: `mcw_core.api.diagnostics.mclogs_client`, `mcw_core.api.java.jvm_presets`, `mcw_core.api.minecraft.screenshot_manager`, `mcw_core.api.minecraft.world_manager`.
- **CurseForge mod loader normalization**: strips game-version prefixes from loader version IDs, fixes duplicated Maven URL prefixes causing 404 download errors.
- **ATLauncher Forge normalization**: auto-heals existing instances with redundant version prefixes; skips server-only file actions and standard Forge launch wrappers.
- **FTB run-lock protection**: preparing-lock timeout extended to 600 s with periodic heartbeat; lock file auto-recreated if evicted while Minecraft is running.
- **Onefile upgrade cleanup**: `UpdateApplier` automatically removes the legacy `_internal/` directory when upgrading from an onedir build to a one-file build.

## Install for development

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m pytest test -q
```

On Windows PowerShell, activate the environment with:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Minimal usage

```python
from mcw_core import CorePaths, LaunchRequest, MCWCore

core = MCWCore(CorePaths.from_root("./mcw-data"))
core.operations.begin()
try:
    result = core.launch(
        LaunchRequest(
            instance="My Instance",
            offline_username="Player",
            on_progress=print,
            # Optional: launch directly into a world or multiplayer server
            quick_play_singleplayer="World Name",   # or quick_play_multiplayer="host:port"
            # Optional: callback when the game window is ready (receives window handle)
            on_window_ready=lambda hwnd: print("Window ready:", hwnd),
        )
    )
finally:
    core.operations.finish()

print(result.minecraft_version, result.java_path)
```

Create an instance with custom JVM arguments:

```python
from mcw_core import InstanceCreateRequest, get_default_core

core = get_default_core()
instance = core.instances.create(
    InstanceCreateRequest(
        name="My Forge Instance",
        version_id="1.20.1",
        loader_name="forge",
        jvm_arguments=("-XX:+UseG1GC", "-Dfml.ignoreInvalidMinecraftCertificates=true"),
    )
)
print(instance.name, instance.version_id)
```

The CLI can list or launch instances without the launcher GUI:

```bash
mcw-core-launch --root ./mcw-data --list
mcw-core-launch --root ./mcw-data --instance "My Instance" --username Player
```

## Public boundary

Supported consumers import from `mcw_core` or `mcw_core.api.*`. Modules under `src.core` and `src.models` are implementation details and may change outside the public compatibility contract.

## CurseForge gateway integration

MCW Core keeps CurseForge credentials outside desktop clients and supports configured HTTPS gateway endpoints. The gateway source is distributed separately and is not included in this Core source archive or wheel. Core bundles no gateway URL, client token or CurseForge API key.

Deploy the gateway separately using [mahiru7229/mcw-curseforge-gateway](https://github.com/mahiru7229/mcw-curseforge-gateway), configure its `CURSEFORGE_API_KEY`, then configure the resulting HTTPS endpoint through `MCW_CURSEFORGE_GATEWAY_URL` or the Core configuration API.

## Source layout

- `mcw_core/`: stable public API and facade.
- `src/core/`: Core implementation.
- `src/models/`: domain models.
- `test/`: headless Core regression suite.
- `docs/`: API, architecture, package and theme contracts.
- `examples/`: integration examples.
- `runtime/` and `mcw_core/resources/`: MCW LAN Agent.

See [RELEASE.md](RELEASE.md) and [docs/MCW_CORE_LIBRARY.md](docs/MCW_CORE_LIBRARY.md) for the release contract. Release history is in [docs/MCW_CORE_RELEASE-v1.6.0.md](docs/MCW_CORE_RELEASE-v1.6.0.md).
