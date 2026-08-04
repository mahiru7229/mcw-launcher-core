# MCW Core v1.0.1

## English

MCW Core 1.0.1 is a backward-compatible maintenance release for the stable 1.0 API.

### Added

- `FirstRunRecommendationService`, `FirstRunRecommendation`, and `JavaRuntimeSummary`.
- `CompatibilityConfirmationRequired` for bypassable pre-launch compatibility reports.
- `LaunchRequest.allow_compatibility_issues_once` for an explicit, user-confirmed retry.
- `ManagedContentPolicy.ASK` and `asks_before_launch()`.
- Theme text fields and `derive_custom_text`, `contrast_ratio`, `is_readable_text`.
- Best-effort provider artwork support for imported Modrinth and CurseForge modpacks.

### Changed

- Resource and shader pack roots are now `<instance>/resourcepacks` and `<instance>/shaderpacks`.
- Legacy v1.0.0 locations are migrated without overwriting conflicts.
- New pack installation is allowed while Minecraft runs; destructive operations remain blocked.
- FTB versions are sorted newest-first.
- Version metadata reports `1.0.1` and the stable channel.


### Localization runtime refresh

- Resolve already-rendered strings from any installed language back to their semantic translation key.
- Match placeholder-based rendered messages, allowing dynamic progress text such as provider and modpack names to be translated without changing the public `ProgressEvent` API.
- Keep the 1.0.1 public API and package version unchanged.

### Compatibility

Existing 1.0.0 public imports remain supported. Applications should continue using only `mcw_core` and `mcw_core.api.*`.

## Tiếng Việt

MCW Core 1.0.1 là bản bảo trì tương thích ngược cho public API stable 1.0.

### Bổ sung

- `FirstRunRecommendationService`, `FirstRunRecommendation` và `JavaRuntimeSummary`.
- `CompatibilityConfirmationRequired` cho lỗi tương thích có thể hỏi người dùng để bỏ qua.
- `LaunchRequest.allow_compatibility_issues_once` cho lần retry đã được xác nhận.
- `ManagedContentPolicy.ASK` và `asks_before_launch()`.
- Các field màu chữ cùng `derive_custom_text`, `contrast_ratio`, `is_readable_text`.
- Lấy icon provider theo cơ chế best-effort khi import modpack Modrinth/CurseForge.

### Thay đổi

- Resource pack và shader pack dùng `<instance>/resourcepacks` và `<instance>/shaderpacks`.
- Dữ liệu ở vị trí sai của v1.0.0 được migration mà không ghi đè xung đột.
- Có thể thêm pack mới khi Minecraft đang chạy; thao tác phá hủy vẫn bị chặn.
- Phiên bản FTB được sắp xếp mới nhất trước.
- Metadata version là `1.0.1` trên channel stable.


### Làm mới runtime bản dịch

- Nhận diện chuỗi đã render ở mọi language pack và ánh xạ lại về semantic translation key.
- Hỗ trợ nhận diện template có placeholder, nhờ đó progress động chứa tên provider/modpack có thể được dịch mà không thay đổi public API `ProgressEvent`.
- Giữ nguyên public API và version package `1.0.1`.

### Tương thích

Các public import 1.0.0 vẫn hoạt động. Ứng dụng bên ngoài chỉ nên dùng `mcw_core` và `mcw_core.api.*`.

## CurseForge gateway hotfix

- Removed the bundled default CurseForge gateway URL from `src/config.py`.
- Kept all CurseForge public APIs and provider modules unchanged.
- `CurseForgeConfigManager.gateway_urls()` now returns an empty tuple when no user, local, or environment configuration exists.
- `CurseForgeConfigManager.gateway_url()` raises a clear configuration error when no endpoint is available.

## Hotfix cấu hình CurseForge gateway

- Đã xóa đường dẫn CurseForge gateway mặc định khỏi `src/config.py`.
- Giữ nguyên toàn bộ public API và provider module CurseForge.
- `CurseForgeConfigManager.gateway_urls()` trả về tuple rỗng khi chưa có cấu hình từ người dùng, file local hoặc biến môi trường.
- `CurseForgeConfigManager.gateway_url()` báo lỗi cấu hình rõ ràng khi chưa có endpoint.

## Language catalog hotfix

- Added semantic keys for launcher language restart notifications.
- Added explicit language-settings labels for external launcher frontends.
- Preserved `Instance` as a domain term through `navigation.instances` in every built-in locale.
- Standardized the Vietnamese launcher settings label as `Cài đặt launcher`.
- No public Python API signature changed in this rebuild.
