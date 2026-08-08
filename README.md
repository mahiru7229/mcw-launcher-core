# MCW Core v1.3.0

MCW Core is the GUI-independent runtime distributed with MCW Launcher.

## Package

- Distribution: `mcw-core 1.3.0`
- Runtime: `mcw_core.__version__ == "1.3.0"`
- Update channel metadata: `stable`
- Python: 3.12 or newer
- Wheel: pure Python `py3-none-any`

## v1.3.0 shared storage and cleanup

The stable v1.3.0 release keeps the validated Shared Storage foundation from Beta 1, the instance-deletion finalization fix from Beta 2, and the narrow unused-version-JAR cleanup from Beta 3.

Final stable hardening adds:

- configurable 1–365 day retention for unused Minecraft version JARs, defaulting to 14 days;
- conservative detection and cleanup of legacy instance residue directories that have no `instance.json`, no registry reference, and contain only `.mcw` / `crash-reports`;
- reference-aware revalidation before deletion;
- provider API/metadata cache remains separate and protected from binary storage cleanup.

## Public API

The supported entry point remains `import mcw_core`.

See `docs/MCW_CORE_LIBRARY.md`, `docs/en/CORE_GUIDE.md`, `docs/vi/CORE_GUIDE.md`, and `RELEASE-v1.3.0.md` in the source archive.
