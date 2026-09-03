# MCW Core v1.5.0

MCW Core `1.5.0` is the Stable headless runtime shipped with MCW Launcher `v1.5.0`.

## Highlights

- Windows x64 and Linux x64 runtime abstractions, XDG storage and safe legacy migration.
- Vanilla, Fabric, Quilt, Forge and NeoForge instance pipelines.
- Automatic Java 8/16/17/21 selection and managed runtime provisioning.
- Microsoft authentication with platform credential protection.
- Modrinth, CurseForge, FTB and ATLauncher integrations.
- Transactional modpack/content installation, repair, backups and diagnostics.
- Process supervision, offline cache behavior and automatic update services.
- Stable `mcw_core` facade, models, progress events and operation controls.

## Distribution contract

- Distribution: `mcw-core 1.5.0`
- Runtime: `mcw_core.__version__ == "1.5.0"`
- Python: `>=3.12`
- GUI dependency: none
- Public imports: `mcw_core` and `mcw_core.api.*`
- Bundled LAN Agent: included
- Optional CurseForge gateway source: `mcw-curseforge-gateway-main.zip`

The gateway archive contains no deployed endpoint or secret. A deployment must supply its own `CURSEFORGE_API_KEY` and the Core must be configured with the resulting HTTPS URL.
