# MCW Launcher update packages

Automatic updates use a GitHub Release ZIP. The ZIP must contain the packaged launcher executable and may contain any other file or directory that should overwrite the current installation.

## Build a release package

After building the EXE with PyInstaller, pass the target version to the package builder. The version must match `src.config.VERSION_ID`:

```powershell
python -m tools.build_release_zip --exe ".\dist\MCW Launcher.exe" --version "0.7.3-beta.1"
```

The command creates:

```text
MCW-Launcher-v0.7.3-beta.1-windows-x64.zip
MCW-Launcher-v0.7.3-beta.1-windows-x64.zip.sha256
```

The package contains a single wrapper directory:

```text
MCW-Launcher-v0.7.3-beta.1-windows-x64/
├── MCW Launcher.exe
├── mcw-update.json
├── lang/
├── themes/
├── docs/
├── README.md
└── LICENSE
```

`mcw-update.json` lets the updater verify that the downloaded package matches the selected GitHub release before replacing files.

## Test an updater transition

1. Build and publish the newer ZIP as an asset of a GitHub release with a higher semantic version.
2. The asset name should contain `MCW`, `windows`, and `x64`.
3. Start a packaged launcher build that contains the current updater but reports an older test version.
4. Use **Launcher Settings → Check for updates** if the automatic check has already run recently.
5. Confirm the update prompt, release notes, package size, backup, overwrite, restart, and `logs/updater.log`.
6. Confirm `config`, `instances`, `accounts`, and other user data remain intact.

The updater copies and overwrites files present in the ZIP. It does not delete unrelated files from the installation directory.

## One-command Windows release build

From a clean working tree, run:

```powershell
.\build_release.ps1
```

The script runs the release preflight, the complete test suite, removes previous build output, builds the windowed EXE, and creates the updater ZIP plus SHA-256 checksum. It reads the version from `src/config.py`; the API JSON publication time remains an external release setting and is not changed by the script.
