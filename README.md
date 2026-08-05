# MCW Core 1.1.0-beta.2

MCW Core 1.1.0-beta.2 is the runtime package released with MCW Launcher v1.1.0-beta.2. This beta adds bounded Java-selection recovery while preserving the existing instance settings format and public launch result contract.

## Install

```bash
python -m pip install mcw_core-1.1.0b2-py3-none-any.whl
```

Verify:

```bash
python -c "import mcw_core; print(mcw_core.__version__)"
```

Expected output:

```text
1.1.0-beta.2
```

## Java selection and recovery

- An empty per-instance Java path continues to mean automatic selection.
- A configured Java path is validated against the Minecraft runtime requirement.
- If the configured path is missing, unreadable, or incompatible, MCW attempts automatic selection instead.
- MCW briefly observes the spawned Java process for strong runtime-mismatch signatures such as `UnsupportedClassVersionError`.
- A Java-specific early startup failure is retried once with another compatible installation or a launcher-managed runtime.
- Successful recovery clears the failed custom path so future launches remain on automatic selection.
- If no valid alternative can be selected or installed, launch fails with an actionable `JavaRecoveryError`.
- Same-second retry attempts receive separate log files so the rejected Java output is not overwritten.

## Compatibility

- Existing `settings.json` files remain valid; no schema migration is required.
- `JavaResolver.resolve(...)` keeps its existing strict return type and behavior for current callers.
- Recovery is exposed through additive internal methods and does not remove existing public imports.
- `JavaManager.find_installation()` still returns one preferred installation per major version; recovery uses a separate all-candidates scan.
- The default CurseForge gateway remains empty.

## Tiếng Việt

MCW Core 1.1.0-beta.2 bổ sung cơ chế tự phục hồi Java có giới hạn. Nếu đường dẫn Java đã cấu hình không hợp lệ hoặc Java thoát sớm do lỗi runtime/không tương thích phiên bản, core sẽ thử đúng một lần bằng Java tương thích khác hoặc Java do launcher quản lý. Nếu phục hồi thành công, đường dẫn tùy chọn bị lỗi được xóa để instance quay về chế độ tự động.

Định dạng `settings.json` và các import công khai hiện có vẫn tương thích.

Xem [`docs/RELEASE-v1.1.0-beta.2.md`](docs/RELEASE-v1.1.0-beta.2.md).
