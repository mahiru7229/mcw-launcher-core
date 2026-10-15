# MCW Core v1.8.2

MCW Core `1.8.2` is the Stable headless runtime and JSON-RPC 2.0 server shipped with MCW Launcher `v1.8.2`.

## Highlights

- **MCW LAN Agent Extended Support (Down to Minecraft 1.14+)**:
  - `LanAgentTargetResolver` supports Minecraft 1.14.0 through 1.16.5+ alongside 1.17+.
  - Automatically identifies Forge SRG (`func_71229_d`), Fabric Intermediary, and Mojang official mapping targets to eliminate "Invalid session" disconnects during offline LAN multiplayer.
- **Hotfix Manager Startup Synchronization & Memory Eviction**:
  - Fast pre-bootstrap auto-sync (`auto_sync=True`, timeout 2.0s) for newly downloaded or missing hotfix installations before UI modules are cached in RAM.
  - Automatic eviction of stale in-memory modules (`sys.modules`) upon applying patches, paired with observer notification callbacks.
- **Offline Account Steve / Alex Default Models Without Online Skin Lookups**:
  - Offline accounts automatically determine Steve (`classic`) or Alex (`slim`) models locally using Minecraft's official `DefaultPlayerSkin` UUID hash algorithm (`OfflineAuthentication.default_skin_variant`).
  - Completely bypasses external skin network calls (Minotar/Mojang), preventing accidental skin leakage even when an offline username matches a licensed player.

## Distribution contract

- Distribution: `mcw-core 1.8.2` (`mcw_core-1.8.2-py3-none-any.whl`)
- Runtime: `mcw_core.__version__ == "1.8.2"`
- Python: `>=3.12`
- GUI dependency: none
- Public imports: `mcw_core`, `mcw_core.rpc`, `mcw_core.api.*`, and `mcw_core.api.models.*`
- CLI entrypoints: `mcw-core-launch` and `mcw-core-rpc`
- Bundled LAN Agent: included
- CurseForge gateway source archive: not bundled with MCW Core

The gateway is distributed/deployed separately. A deployment must supply its own `CURSEFORGE_API_KEY` and the Core must be configured with the resulting HTTPS URL.
