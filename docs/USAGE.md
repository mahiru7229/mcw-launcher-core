# Using MCW Core

## Progress reporting

Most long-running operations accept a progress callback. The callback receives
`ProgressEvent` objects with a stage, message, current/total values, and percentage.

## Provider-native modpack import

Use the public package APIs to import:
- Modrinth `.mrpack`
- CurseForge `manifest.json` ZIP packages
- Provider-preserving profile bundles
- Portable MCWPack archives

## Portable export

The portable content manager supports referenced, embedded, and manual-download entries.
For public sharing, callers should surface provider and license warnings to the user.
