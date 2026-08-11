# MCW Core 1.3.2

MCW Core **1.3.2** ships the headless/runtime-side fixes used by MCW Launcher v1.3.2.

## Fixed

- Added a reusable atomic text writer with per-operation temporary files, fsync, retryable atomic replace, and best-effort cleanup.
- Removed the reported manifest and instance-registry fixed-temp collision paths that could surface as Windows `WinError 32`.
- Hardened short-workspace recursive cleanup against canonical-path escapes and root deletion.
- Hardened launcher-update verification so automatic downloads require SHA-256 metadata or a `.sha256` sidecar.
- Added managed release-file inventory support and rollback-aware stale-file removal for future updates applied by v1.3.2+.
- Unified modpack relative-path validation with MCW package Windows filename restrictions.
- Made theme overwrite import rollback-safe at the final publish boundary.

## Compatibility

- Python: `>=3.12`
- Distribution: `mcw-core==1.3.2`
- No PySide6 dependency is introduced.
- Existing public imports from `mcw_core` remain unchanged; `ReleaseAsset` only gains the optional `sha256_url` field.
- Existing persisted instance/account/package formats are unchanged.
