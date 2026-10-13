# MCW Core v1.8.1

MCW Core `1.8.1` is the Stable headless runtime and JSON-RPC 2.0 server shipped with MCW Launcher `v1.8.1`.

## Highlights

- **Direct CurseForge Countdown Download URL Resolution & Slug Resolver**:
  - `CurseForgeLinks.resolve_download_page_url`: Automatically constructs direct countdown download URLs (`/download/{file_id}`) to trigger exact jar downloads.
  - Slug resolution via fallback `cflookup.com` service for numeric project IDs without requiring a Gateway API key.
- **Maven Library Deduplication on Classpath**:
  - `ClasspathBuilder.deduplicate_maven_libraries`: Intelligent deduplication ensuring the latest version of Maven libraries (Log4j 2.15.0+, lwjgl) is loaded while maintaining classpath order.
- **Prism Launcher Direct Launch Execution**:
  - Preflight checks align with Prism Launcher behavior: non-blocking dependency resolution delegating final checks to the ModLoader runtime.
- **100% Core & GUI Decoupling via JSON-RPC 2.0 (`mcw_core.rpc`)**:
  - Headless JSON-RPC 2.0 servers (`--stdio` Sidecar and `--http` local daemon with SSE) and multi-transport `CoreRpcClient`.

## Distribution contract

- Distribution: `mcw-core 1.8.1` (`mcw_core-1.8.1-py3-none-any.whl`)
- Runtime: `mcw_core.__version__ == "1.8.1"`
- Python: `>=3.12`
- GUI dependency: none
- Public imports: `mcw_core`, `mcw_core.rpc`, `mcw_core.api.*`, and `mcw_core.api.models.*`
- CLI entrypoints: `mcw-core-launch` and `mcw-core-rpc`
- Bundled LAN Agent: included
- CurseForge gateway source archive: not bundled with MCW Core

The gateway is distributed/deployed separately. A deployment must supply its own `CURSEFORGE_API_KEY` and the Core must be configured with the resulting HTTPS URL.
