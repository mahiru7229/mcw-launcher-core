# MCW Core v1.1.0-beta.2

## English

MCW Core v1.1.0-beta.2 adds bounded Java runtime recovery for MCW Launcher v1.1.0-beta.2.

### Changes

- Add `JavaResolution` and `JavaRecoveryError` for additive recovery workflows.
- Add `JavaResolver.resolve_with_recovery(...)` for custom-path fallback.
- Add `JavaResolver.resolve_alternative(...)` for one-time runtime replacement.
- Preserve the historic one-Java-per-major result of `JavaManager.find_installation()` while adding an all-path candidate scan for recovery.
- Detect strong Java-specific early process failures without treating normal Minecraft crashes as Java selection errors.
- Retry once with another compatible runtime or launcher-managed Java.
- Preserve separate log files for same-second retry attempts.
- Add semantic progress and warning translations in English and Vietnamese.
- Package metadata reports `1.1.0b2`; runtime metadata reports `1.1.0-beta.2`.

### Validation

- Core test suite: **130 passed**.
- Wheel built as `mcw_core-1.1.0b2-py3-none-any.whl`.
- Isolated installation verified runtime `1.1.0-beta.2`, distribution `1.1.0b2`, and public API imports.

### Compatibility

- No existing public import is removed.
- `JavaResolver.resolve(...)` still returns a `Path` and remains strict for explicitly supplied paths.
- Instance settings require no migration.
- Provider, account, package, theme, and modpack formats are unchanged.

## Tiếng Việt

MCW Core v1.1.0-beta.2 bổ sung cơ chế phục hồi Java có giới hạn cho MCW Launcher v1.1.0-beta.2.

### Thay đổi

- Bổ sung `JavaResolution` và `JavaRecoveryError` cho luồng phục hồi mới.
- Thêm fallback khi đường dẫn Java tùy chọn bị thiếu hoặc không tương thích.
- Thêm lựa chọn Java thay thế khi runtime thoát sớm với dấu hiệu lỗi Java rõ ràng.
- Chỉ retry một lần, ưu tiên Java tương thích khác trên máy rồi mới chuẩn bị Java do launcher quản lý.
- Giữ nguyên hành vi cũ của `JavaManager.find_installation()`; danh sách đầy đủ chỉ dùng nội bộ cho phục hồi.
- Giữ riêng log của từng lần thử Java.
- Bổ sung progress và cảnh báo bằng tiếng Anh/Việt.
- Metadata package là `1.1.0b2`; metadata runtime là `1.1.0-beta.2`.

### Xác thực

- Bộ test Core: **130 passed**.
- Wheel được build thành `mcw_core-1.1.0b2-py3-none-any.whl`.
- Đã cài wheel vào thư mục độc lập và xác nhận runtime `1.1.0-beta.2`, distribution `1.1.0b2` cùng public API.

### Tương thích

Không thay đổi schema instance, provider, tài khoản, package, theme hoặc modpack. Caller hiện tại của `JavaResolver.resolve(...)` vẫn nhận `Path` như trước.
