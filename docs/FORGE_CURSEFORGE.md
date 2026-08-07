# CurseForge Gateway integration

MCW Launcher `v0.10.0-beta.1` provides Fabric and Forge CurseForge browsing and installation through the public MCW gateway without bundling a CurseForge API key in the source, EXE, or updater package.

## Architecture

```text
MCW Launcher
    │ HTTPS JSON
    ▼
MCW public CurseForge Gateway
    │ unavailable? try configured custom gateways
    ▼
CurseForge API
```

The CurseForge API key remains on the gateway server. Mod files are not proxied through the gateway: it returns metadata or download URLs and MCW Launcher's downloader fetches the file directly, reports progress, retries, and verifies SHA-1.

## Default and custom endpoints

Fresh installations use:

```text
https://mcw-curseforge-gateway.vercel.app/api/curseforge
```

Custom HTTPS endpoints can still be configured in **Launcher Settings → CurseForge gateways**. Environment or locally protected configuration takes priority over the public default.

The launcher stores local overrides in:

```text
config/private/curseforge_endpoints.json
```

Values are protected with Windows DPAPI and can only be decrypted by the Windows account that saved them. The file is excluded from Git and is not copied into release packages.

For managed deployments, these environment variables are supported:

```text
MCW_CURSEFORGE_GATEWAY_URL_1
MCW_CURSEFORGE_GATEWAY_URL_2
MCW_CURSEFORGE_GATEWAY_URL_3
MCW_CURSEFORGE_GATEWAY_URL_4
MCW_CURSEFORGE_GATEWAY_URL_5
MCW_CURSEFORGE_CLIENT_TOKEN
```

The legacy single variable `MCW_CURSEFORGE_GATEWAY_URL` remains readable for compatibility.

## Provider metadata compatibility policy

CurseForge Minecraft-version and loader labels are treated as **advisory metadata**, not final proof that a JAR is incompatible.

For modpacks, the selected browser loader filters discovery, while the downloaded `manifest.json` is authoritative. The launcher accepts a single supported primary `fabric-<version>` or `forge-<version>` entry, rejects unsupported or ambiguous manifests, and creates the instance with that exact loader version.

For standalone mods, the launcher now:

1. Requests files without strict Minecraft-version or Fabric/Forge filters.
2. Ranks the selected loader first, followed by exact and nearby Minecraft patch labels.
3. Keeps universal, unknown, and differently labelled files visible.
4. Downloads the selected JAR.
5. Inspects the real loader metadata inside the archive before adding it to the instance.

A JAR containing both:

```text
fabric.mod.json
META-INF/mods.toml
```

is recognized as a Fabric/Forge universal mod. For a Fabric instance the launcher reads `fabric.mod.json`; for a Forge instance it reads `META-INF/mods.toml`.

A differently loader-labelled file is allowed to reach JAR validation. For a standalone mod, MCW Launcher shows a clear loader warning and requires explicit confirmation before installing it. Minecraft-version labels never produce this warning or block installation. For a managed modpack, its exact project/file declaration is authoritative and the provider labels are retained only for diagnostics.

This behavior also applies to managed files inside CurseForge modpacks, fixing packs whose universal dependencies are indexed under only one loader.

Forge language providers and managed libraries may not contain `mods.toml`. MCW Launcher additionally recognizes these `META-INF/MANIFEST.MF` values:

```text
FMLModType: LANGPROVIDER
FMLModType: LIBRARY
FMLModType: GAMELIBRARY
```

Unknown JARs remain blocked by default. They are copied only when the user explicitly accepts the standalone-mod warning or when an exact, checksum-verified file is declared by a managed modpack.

## Open in browser

The CurseForge browser and Mods page expose an **Open in browser** action for the selected project.

Only HTTPS links on `curseforge.com` or its subdomains are accepted. Invalid or unsafe URLs returned by a gateway are ignored; the launcher falls back to an official CurseForge project URL generated from the project slug.

## Failover policy

Requests use endpoints in the configured order. The launcher tries the next endpoint when the current one has:

- a connection or TLS failure;
- invalid JSON/invalid response data;
- HTTP `404`, `408`, `425`, `429`, or `5xx` status.

Authentication and request errors such as HTTP `400`, `401`, or `403` are not repeated across every endpoint.

Download failures are also classified by retryability. Missing gateway credentials, unavailable files, disabled third-party distribution, and manual-download requirements are treated as permanent for the current run and are not retried three times.

## Download fallback order

For a managed file, the launcher uses this order:

1. Reuse a verified file already present in the shared CurseForge cache.
2. Use the `downloadUrl` already stored in the instance registry.
3. Ask the configured CurseForge gateway for the official file/download URL.
4. When a SHA-1 is known, query Modrinth for a file with the **same SHA-1** and use its direct URL only when the hash and expected size match.
5. Open the CurseForge project in the browser and let the user import the exact file manually.

The launcher does not construct undocumented CurseForge CDN paths. Every automatic or manual result is verified against the expected SHA-1 when one is available.

## Supported workflow

- Search CurseForge projects through the gateway.
- Select Fabric or Forge, then filter by release channel while ranking loader and advisory Minecraft-version metadata.
- Fetch project/file metadata in batches where possible.
- Install required CurseForge mod dependencies.
- Download automatically when `downloadUrl` is available and third-party distribution is permitted.
- If automatic distribution is unavailable, open the official project page and allow the user to select the downloaded `.jar`.
- Validate manually selected files by expected byte size and SHA-1 before adding them to the instance.
- Track installed and pending files in the CurseForge registry.
- Install Fabric and Forge modpacks by validating `manifest.json`, preparing the declared loader, extracting overrides safely, and recording managed files for launch-time verification.

The verified manual-download flow supports both restricted mod JARs and restricted modpack ZIP archives. CurseForge modpack handling remains experimental and should be tested with non-critical worlds.

## Transactional standalone-mod installation

`v0.10.0-beta.1` prepares and validates every automatically downloadable standalone mod before changing the target instance.

The selected root file may use an explicit unverified-file approval from the user. That approval is deliberately not inherited by dependencies: every dependency must independently contain metadata compatible with the target Fabric or Forge instance.

During apply, the launcher snapshots only the files that can be replaced:

- the CurseForge registry and its temporary file;
- destination JARs and disabled variants;
- installed JARs with the same mod ID;
- the previously tracked filename for each CurseForge project.

If copying a JAR or saving the registry fails, those affected paths are removed and the snapshot is restored. Download cache files are retained so a later retry does not need to fetch verified data again.

## Local JSON cache

CurseForge responses are stored under:

```text
cache/content/curseforge/api-v2/
├── index.json
└── entries/
```

Policy:

- Maximum disk size: `10 MiB`.
- Cleanup target: `8 MiB`.
- Eviction: least recently used entries first.
- Download URLs are resolved at install time and are not retained as permanent download authority.
- Cache writes use temporary files and atomic replacement.
- Invalid cache schema/data is discarded safely.

If every gateway is temporarily unavailable, stale cached data may remain visible instead of clearing the page.

## Security and privacy

The cache and diagnostics must never contain:

- CurseForge API keys;
- client authorization tokens;
- Microsoft access or refresh tokens;
- account databases;
- private worlds or instance saves.

Only public project/file metadata is cached. The server-side CurseForge API key is never returned to the launcher.
