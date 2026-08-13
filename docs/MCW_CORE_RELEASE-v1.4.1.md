# MCW Core v1.4.1

MCW Core **1.4.1** is the stable Core distribution shipped with MCW Launcher v1.4.1.

## Changes

- Managed Java selection/recovery prioritizes the launcher-managed runtime for automatic Java 8 recovery while preserving compatible explicit user overrides.
- Java provisioning reports metadata, download/checksum, extraction, and install failures separately.
- Java scanning avoids background `javaw.exe` probes when a console `java.exe` sibling is available, preventing GUI JVM error dialogs from stale installations.
- Managed Java extraction uses a fresh child directory inside the short workspace to avoid Windows destination collisions.
- Diagnostics v2.1 adds stronger path/privacy sanitization, runtime truncation metadata, Java recovery evidence, loader-installer evidence, and collector isolation.

## Package metadata

- Distribution: `mcw-core 1.4.1`
- Runtime `mcw_core.__version__`: `1.4.1`
- Requires Python `>=3.12`
- GUI modules are not part of the wheel.
