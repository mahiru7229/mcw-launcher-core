# MCW Core v1.1.2

## Tiếng Việt

MCW Core **1.1.2** đồng bộ toàn bộ thay đổi core đã được kiểm thử trong nhánh MCW Launcher v1.1.2 và đưa chúng lên stable.

### Dependency correctness

- Scope dependency theo active loader và xử lý `java`, `minecraft`, Forge/NeoForge/Fabric/Quilt loader IDs như environment capabilities thay vì downloadable mods.
- Giữ quyền ưu tiên của manifest đối với artifact được modpack pin; foreign-loader metadata không còn tự tạo blocker giả.
- CurseForge candidate selection loại file sai loader/Minecraft version trước khi chọn.
- Forge/NeoForge mixed metadata được parse theo active loader.
- Embedded/JarJar capability được đưa vào dependency satisfaction, nên nested dependency như `expandability` có thể thỏa requirement mà không cần JAR top-level riêng.

### Mod preflight và version matching

- Duplicate detection chỉ so sánh primary/top-level mod IDs; embedded/provided capability vẫn thỏa dependency nhưng không tạo false duplicate warning.
- Cải thiện Forge/Maven-style version comparison cho numeric revision, qualifier, combined loader version và danh sách version alternatives.
- Optional recommendations/foreign-provider notices không còn bị nâng thành warning launch không cần thiết.
- Resolver có thể dọn stale required dependency do chính launcher quản lý khi manifest/capability mới đã thay thế nó, nhưng giữ file nếu provenance không an toàn hoặc hash cho thấy người dùng đã sửa.

### Performance và mod-loader installation

- CurseForge modpack download dùng bounded concurrency; batch lớn dùng worker thận trọng hơn để giảm contention.
- Dependency progress của pack lớn được batch/throttle để giảm áp lực event loop.
- Fabric/Quilt resolve metadata library song song có giới hạn.
- Forge/NeoForge staging tái sử dụng Vanilla libraries trong cache.
- Java installer retry giới hạn cho lỗi mạng tạm thời và báo timeout bằng diagnostic có ngữ cảnh.

### Legacy metadata và manual recovery

- `mcmod.info` legacy có control characters/malformed JSON nhưng còn salvage được identity sẽ được đọc tolerant thay vì tạo false invalid warning.
- CurseForge/Modrinth manual dependency có thể pause cùng launch session, cho phép import nhiều file, revalidate rồi resume mà không chạy lại toàn bộ instance.
- Manual import trong lúc pause chỉ được phép với đúng preparing-lock token của phiên launch; cancel vẫn được tôn trọng.
- Hotfix cuối của Beta 5 loại deadlock khi manual import dùng chung download pause controller.

### Compatibility / validation

- Không thay đổi chủ đích các public API hiện có của v1.1.1; `LaunchRequest` được mở rộng để hỗ trợ callback manual-content recovery.
- Fix dependency đã được runtime xác nhận trên SkyFactory 5 và All The Mods 9 trong quá trình beta.
- Stable source/wheel được validate lại trước khi phát hành; kết quả cụ thể nằm trong `TEST-RESULTS.txt`.

### Release metadata

- Distribution metadata: `1.1.2`
- Runtime metadata: `1.1.2`
- Channel: `stable`

---

## English

MCW Core **1.1.2** synchronizes the full core changes validated through the MCW Launcher v1.1.2 beta line and promotes them to stable.

### Dependency correctness

- Scopes dependency metadata to the active loader and treats Java, Minecraft, and loader IDs as environment capabilities rather than downloadable mods.
- Preserves manifest authority for pack-pinned artifacts so foreign-loader metadata does not become a false blocker.
- Rejects wrong-loader/wrong-Minecraft-version CurseForge candidates before selection.
- Parses mixed Forge/NeoForge metadata according to the active loader.
- Uses embedded/JarJar capabilities for dependency satisfaction, allowing nested dependencies such as `expandability` to satisfy requirements without a separate top-level JAR.

### Mod preflight and version matching

- Duplicate detection compares primary/top-level mod IDs only; embedded/provided capabilities still satisfy dependencies without false duplicate warnings.
- Improves Forge/Maven-style matching for numeric revisions, qualifiers, combined loader versions, and alternative-version lists.
- Optional recommendations and non-actionable foreign-provider notices are no longer promoted to launch warnings.
- Safely removes stale resolver-managed required dependencies when a current manifest/capability replaces them, while preserving files with unsafe provenance or user-modified hashes.

### Performance and mod-loader installation

- Uses bounded concurrency for CurseForge modpack downloads, with a more conservative worker policy for large batches.
- Batches/throttles dependency progress for large packs to reduce event-loop pressure.
- Resolves Fabric/Quilt library metadata concurrently with bounded workers.
- Reuses cached Vanilla libraries during Forge/NeoForge installer staging.
- Retries Java installers once for clearly transient network failures and reports timeouts with contextual diagnostics.

### Legacy metadata and manual recovery

- Tolerantly salvages usable legacy `mcmod.info` metadata with control characters or malformed JSON instead of emitting false invalid warnings.
- CurseForge/Modrinth manual dependency recovery can pause the current launch, import multiple files, revalidate, and resume without restarting the entire instance flow.
- Paused-launch manual imports require the exact preparing-lock token and still honor cancellation.
- The final Beta 5 hotfix removes the shared-pause deadlock that could leave a manual batch task stuck as already running.

### Compatibility / validation

- Existing v1.1.1 public APIs are not intentionally removed; `LaunchRequest` is extended with manual-content recovery callback support.
- Dependency fixes were runtime-validated with SkyFactory 5 and All The Mods 9 during the beta cycle.
- Stable source/wheel validation results are recorded in `TEST-RESULTS.txt`.

### Release metadata

- Distribution metadata: `1.1.2`
- Runtime metadata: `1.1.2`
- Channel: `stable`
