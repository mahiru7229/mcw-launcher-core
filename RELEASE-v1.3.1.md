# MCW Core v1.3.1

MCW Core **v1.3.1** is a Windows compatibility hotfix for deeply nested launcher installations.

## Changes

- Adds a short temporary workspace root under `%LOCALAPPDATA%\MCW\t` on Windows.
- Uses readable three-character workspace prefixes: `jvm`, `frg`, `neo`, and `mrd`.
- Java archive extraction no longer stages beneath the potentially long launcher runtime root.
- Forge and NeoForge installer staging now runs from the short workspace while preserving their separate implementations.
- Modrinth staging uses the short workspace and an 8-character transaction ID.
- CurseForge override extraction uses the `cfr` short workspace before publishing into the instance.
- Java, Modrinth and CurseForge extraction/copy boundaries use Windows extended paths where required.
- Unified download file I/O and Modrinth verification use the same extended-path-aware filesystem boundary.
- Regression coverage includes the exact Java 8 and Modrinth nested paths observed in Windows 10 diagnostics.

## Compatibility

- Shared Storage and ContentStore behavior from v1.3.0 is unchanged.
- Provider API Cache behavior is unchanged.
- Permanent instance/cache/runtime roots remain configurable and are not relocated by this hotfix.

## Version

- Distribution: `mcw-core 1.3.1`
- Runtime: `mcw_core.__version__ == "1.3.1"`
