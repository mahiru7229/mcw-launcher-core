# MCW Core v1.6.1 release notes

This is the standalone source release of the Core runtime bundled with MCW Launcher `v1.6.1`.

## Changes from 1.6.0

### Modloader metadata network retries

- Added `HttpDownloader.get_with_retry(url, max_attempts=5, timeout=20.0, ...)` with exponential backoff (0.5s, 1.0s, 2.0s, 4.0s) and retryable status code inspection (408, 429, 500, 502, 503, 504).
- Applied across all loader metadata clients:
  - `NeoForgeMetadataClient`
  - `ForgeMetadataClient`
  - `FabricMetaClient`
  - `QuiltMetaClient`
- Prevents transient network timeouts or connection drops from failing loader version queries during instance creation or verification.

### Extended Windows path (`\\?\`) support (Fix Issue #32)

- Extended `src/core/fs/windows_path.py` with:
  - `to_extended_windows_path()` and `native_filesystem_path()` prepending `\\?\` prefix on Windows.
  - Extended path support in `copy_file()`, `link_file()`, `same_file()`, `open_file()`, and `is_file()`.
  - Chunked streaming copy fallback when low-level Win32 `CopyFile2` APIs fail on long paths.
- Protected `NeoForgeVersionManager` and `ForgeVersionManager` during installer execution, library staging, and verification against `MAX_PATH` (260 characters) limitations.
- Shortened staging temporary publishing artifact pattern in `SharedFileMaterializer` (`.tmp_<hex>.pub`), saving up to 90 path characters.
- Protected `JavaProvisioner` using `open_file()` and `is_file()` to safely install Java runtimes into long path workspaces.

### Distribution & Installation

- Prebuilt `.whl` distribution package `mcw_core-1.6.1-py3-none-any.whl` available for standalone headless consumers.
- Tested and verified with 100% test pass rate across all core subsystems.

The CurseForge gateway source remains a separate project and is not bundled in this archive or wheel.
