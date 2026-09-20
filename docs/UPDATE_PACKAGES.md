# MCW Launcher update packages

Automatic updates use a GitHub Release ZIP. The ZIP must contain the packaged launcher executable and may contain any other file or directory that should overwrite the current installation.

## Build a release package

After building the EXE with PyInstaller (one-file mode), pass the target version to the package builder. The version must match `src.config.VERSION_ID`:

```powershell
python -m tools.build_release_zip --exe ".\dist\MCW Launcher.exe" --version "1.6.0"
```

The command creates:

```text
MCW-Launcher-v1.6.0-windows-x64.zip
MCW-Launcher-v1.6.0-windows-x64.zip.sha256
```

The package contains a single wrapper directory:

```text
MCW-Launcher-v1.6.0-windows-x64/
├── MCW Launcher.exe       ← single-file executable (one-file mode)
├── mcw-update.json
├── lang/
├── themes/
├── docs/
├── README.md
└── LICENSE
```

`mcw-update.json` lets the updater verify that the downloaded package matches the selected GitHub release before replacing files.

> [!NOTE]
> Since v1.6.0 the launcher is distributed as a **single-file executable** (PyInstaller `onefile`). The `cleanup_paths` manifest field includes `_internal` so the updater automatically removes the legacy `_internal/` directory left over from older `onedir` beta builds when upgrading.

## Test an updater transition

1. Build and publish the newer ZIP as an asset of a GitHub release with a higher semantic version.
2. The asset name should contain `MCW`, `windows`, and `x64`.
3. Start a packaged launcher build that contains the current updater but reports an older test version.
4. Use **Launcher Settings → Check for updates** if the automatic check has already run recently.
5. Confirm the update prompt, release notes, package size, backup, overwrite, restart, and `logs/updater.log`.
6. Confirm `config`, `instances`, `accounts`, and other user data remain intact.
7. Confirm the `_internal/` directory (if present from a beta install) has been removed.

The updater copies and overwrites files present in the ZIP. It does not delete unrelated user files from the installation directory.

## One-command Windows release build

From a clean working tree, run:

```powershell
.\build_release.ps1
```

The script runs the release preflight, the complete test suite, removes previous build output, builds the windowed single-file EXE, and creates the updater ZIP plus SHA-256 checksum. It reads the version from `src/config.py`; the API JSON publication time remains an external release setting and is not changed by the script.
