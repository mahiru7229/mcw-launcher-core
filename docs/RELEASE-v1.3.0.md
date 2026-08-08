# MCW Core v1.3.0

## Stable storage lifecycle

MCW Core **v1.3.0** is the stable Shared Storage & Cache Lifecycle release used by MCW Launcher v1.3.0.

### Storage behavior

- SHA-256 ContentStore supports reuse of managed immutable provider artifacts.
- Forge/NeoForge installation staging is temporary and canonical artifacts are reused where possible.
- Provider API/metadata cache is explicitly separate from downloaded binary content and is never removed by legacy storage cleanup.
- Legacy cleanup plans report exact candidates and physical reclaimable bytes, then revalidate selected items immediately before deletion.

### Minecraft version retention

- Unused canonical Minecraft version JAR cleanup now accepts a configurable retention period from 1 to 365 days.
- Default retention is 14 days.
- A version JAR remains protected while referenced directly by an instance or through loader inheritance.
- Cleanup removes only `<version>.jar`; version/profile JSON metadata remains available.

### Legacy instance residue

- Old instance directories left behind by previous launcher deletion behavior can be cleanup candidates only when they are direct children of the configured instance root, have no `instance.json`, have no registry reference, and contain only known `.mcw` / `crash-reports` residue.
- Revalidation occurs before deletion so a folder that becomes referenced is skipped.

### Version metadata

- Runtime: `1.3.0`
- Distribution: `mcw-core 1.3.0`
- Update channel: `stable`
