# MCW Core v1.2.0

## Stable release

MCW Core **1.2.0** is the headless core shipped with MCW Launcher v1.2.0 stable.

### Instance Manager 2.0 support

- Adds backward-compatible instance Favorite / Group / Tags metadata.
- Adds public instance-library metadata mutation through `InstanceService`.
- Adds public `InstanceRuntimeProfile` with Minecraft version, loader version, Java requirement and runtime selection information.
- Adds validated per-instance Java runtime selection through the public Core boundary.

### Unified content support

- Keeps installed-content discovery/provider provenance in Core so GUI local import and filtering do not bypass domain validation.
- Preserves managed modpack protection and instance run-lock behavior.

### Reliability retained from v1.1.2 / v1.2 RC

- Loader-scoped dependencies and environment capabilities.
- Embedded/JarJar capability resolution.
- Forge/Maven version matching and primary-vs-provided identity handling.
- Same-session manual CurseForge/Modrinth dependency recovery.
- Bounded download/modloader installation concurrency and retry behavior.
- Legacy `mcmod.info` salvage.
- Disk-space/local-file-access failures terminate preparation and release the instance lock instead of entering manual-download recovery.

### Package metadata

- Distribution: `mcw-core 1.2.0`
- Runtime: `mcw_core.__version__ == "1.2.0"`
- Python: 3.12+
- Wheel: `py3-none-any`
