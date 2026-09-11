# MCW Core v1.5.1

MCW Core `1.5.1` is the Stable headless runtime shipped with MCW Launcher `v1.5.1`.

## Highlights

- Fabric `provides` aliases are indexed as real mod capabilities, including nested Fabric JARs.
- Managed modpacks can recover undeclared Modrinth dependencies only after the downloaded JAR is hash-verified and proven to provide the requested mod ID/version.
- Dependency errors are grouped for clearer diagnostics when many mods require the same missing capability.
- Update services match Launcher 1.5.1, including schema-2 manifests, bundled updater handoff, emergency Bridge strategy and hardened Windows executable replacement/rollback.
- Windows x64 and Linux x64 runtime abstractions, XDG storage and safe legacy migration remain supported.
- Vanilla, Fabric, Quilt, Forge and NeoForge instance pipelines remain supported.
- Microsoft authentication, managed Java, Modrinth, CurseForge, FTB and ATLauncher integrations remain available.

## Distribution contract

- Distribution: `mcw-core 1.5.1`
- Runtime: `mcw_core.__version__ == "1.5.1"`
- Python: `>=3.12`
- GUI dependency: none
- Public imports: `mcw_core` and `mcw_core.api.*`
- Bundled LAN Agent: included
- CurseForge gateway source archive: not bundled with MCW Core

The gateway is distributed/deployed separately. A deployment must supply its own `CURSEFORGE_API_KEY` and the Core must be configured with the resulting HTTPS URL.
