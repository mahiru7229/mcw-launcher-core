# MCW Core v1.3.0-beta.3

## Summary

MCW Core **v1.3.0-beta.3** keeps the validated v1.3 shared-storage and instance-deletion behavior intact and makes Minecraft version cleanup narrower and safer.

## Unused Minecraft version JAR cleanup

- Storage cleanup now considers only canonical cached version JARs at `cache/versions/<version>/<version>.jar`.
- A JAR becomes a cleanup candidate only when no installed instance or loader inheritance chain references its version and the existing retention window has elapsed.
- The surrounding version directory is preserved. JSON/profile metadata and unrelated files are not deleted.
- The cleanup plan continues to expose the exact path, reason, safety class, file count, category subtotal, and reclaimable bytes before deletion.
- `apply()` rescans immediately before deletion, so a JAR that becomes referenced after preview is skipped instead of removed.

## Loader reference safety

- Vanilla/base Minecraft versions referenced directly by instances remain protected.
- Forge and NeoForge loader profile references remain protected.
- Fabric and Quilt profile IDs now use their actual cached directory layout: `fabric-loader-<loader>-<game>` and `quilt-loader-<loader>-<game>`.
- `inheritsFrom` chains continue to protect base Minecraft versions needed by loader profiles.

## Unchanged boundaries

- Provider API/metadata cache is not part of this cleanup.
- Shared ContentStore behavior from Beta 1 is unchanged.
- Complete instance deletion behavior from Beta 2 is unchanged.
- No instance files, saves, configs, worlds, Java runtimes, assets, or libraries are deleted by version-JAR cleanup.

## Version metadata

- Runtime: `1.3.0-beta.3`
- Distribution: `1.3.0b3`
- Update channel: `beta`
