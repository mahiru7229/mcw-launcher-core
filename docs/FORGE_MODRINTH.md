# Forge + Modrinth workflow

MCW Launcher `v0.6.0` supports Modrinth mods and `.mrpack` modpacks for both Fabric and Forge.

## Browse Mods

Open an instance, select **Manage Mods**, then choose **Browse Modrinth**.

The loader selector defaults to the current instance:

```text
Fabric instance → Fabric filter
Forge instance  → Forge filter
```

Search and version requests include both the Minecraft version and loader. Required dependencies are resolved with the same filters.

A different loader may be browsed, but installation is blocked until the selected loader matches the instance.

## Browse Modpacks

The existing **Browse Modrinth modpacks** action now includes:

```text
Loader: Fabric | Forge
```

The selected project version must contain a matching dependency in `modrinth.index.json`:

```json
{
  "dependencies": {
    "minecraft": "1.20.1",
    "forge": "47.4.21"
  }
}
```

or:

```json
{
  "dependencies": {
    "minecraft": "1.20.1",
    "fabric-loader": "0.16.0"
  }
}
```

A pack declaring both loader families, or declaring NeoForge/Quilt, is rejected.

## Deferred downloads

Installing a modpack prepares the declared loader, creates the instance, extracts safe override files, and stores the managed-file registry. The large mod/file set is downloaded when Launch is pressed:

```text
Check all
→ Download missing
→ Check again
→ Retry up to 3 rounds
→ Launch or report missing files
```

Valid files are checked and skipped. Pause/Resume, HTTP Range, aggregate speed, bandwidth limiting, and manual fallback use the same shared downloader as other launcher content.

## Updating

Mod and modpack updates use the loader saved in the instance/registry. A managed modpack update may change Minecraft or loader version within the same family, but it cannot automatically change from Fabric to Forge or from Forge to Fabric.

The updater creates a full safety backup, preserves user-modified conflicts, removes obsolete unmodified managed files, and rolls back the instance when applying the target version fails.

RC 1 avoids downloading or copying files that already match the target manifest. Preserved files remain in the managed registry so later scans and repairs can still explain their state.

## Repairing

Use **Instances → Backup and Modrinth pack lifecycle → Repair modpack** to restore the currently installed pack version.

Repair performs a forced checksum verification, downloads the current `.mrpack` manifest, restores missing or modified managed files, prepares the declared Fabric/Forge runtime, and writes a fresh verification cache. A full backup is created before the first instance file is replaced. Worlds and files not managed by the pack are not removed.

If repair fails after local changes begin, MCW Launcher restores the backup, runtime profile, and previous registry metadata.

## Verification cache

The managed-pack registry schema is now version 4. Successful checks store each file's expected hashes, size, and modification timestamp. Later scans and launch checks can accept unchanged files without reading their full contents again. A changed size or timestamp invalidates the cache and triggers normal checksum verification.
