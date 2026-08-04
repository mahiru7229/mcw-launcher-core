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

### Tương thích

Các public import 1.0.0 vẫn hoạt động. Ứng dụng bên ngoài chỉ nên dùng `mcw_core` và `mcw_core.api.*`.
