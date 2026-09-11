# MCW Core v1.5.1 release notes

This is the standalone source release of the Core runtime bundled with MCW Launcher `v1.5.1`.

## Changes from 1.5.0

- Fabric metadata now honors `provides` aliases as dependency capabilities.
- Nested Fabric JAR aliases are indexed by the capability scanner.
- Managed modpacks can recover undeclared Modrinth dependencies through verified provider discovery.
- Dependency diagnostics group repeated requirements for the same missing dependency.
- Core update services are synchronized with Launcher 1.5.1's schema-2 updater and Bridge-aware update path.
- Windows update replacement and rollback use the hardened native/fallback behavior from Launcher 1.5.1.

The CurseForge gateway source remains a separate project and is not bundled in this archive or wheel.
