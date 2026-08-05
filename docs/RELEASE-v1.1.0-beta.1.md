# MCW Core v1.1.0-beta.1

## English

MCW Core v1.1.0-beta.1 is the core package aligned with MCW Launcher v1.1.0-beta.1.

### Changes

- Package metadata now reports `1.1.0b1`; runtime metadata reports `1.1.0-beta.1`.
- The bundled English and Vietnamese language sources include semantic entries for Minecraft library/assets preparation and CurseForge file-check progress.
- Source-package integrity files omitted from the uploaded core archive (`src/core/config`, release-preflight tool, and generated theme-contract documents) are restored so core imports and release tests remain runnable.
- Public imports, launch contracts, instance formats, provider formats, and runtime behavior remain compatible with v1.0.2.

Validation: `18 passed`; the built wheel passed a target-install import smoke test.

The GUI consumes these language entries to render progress in the active launcher language. No Java selection, retry, Forge legacy, or account-security behavior is changed in this beta.

---

## Tiếng Việt

MCW Core v1.1.0-beta.1 là package core được đồng bộ với MCW Launcher v1.1.0-beta.1.

### Thay đổi

- Metadata package chuyển thành `1.1.0b1`; metadata runtime chuyển thành `1.1.0-beta.1`.
- Nguồn language pack English và Tiếng Việt bổ sung key cho progress chuẩn bị thư viện/assets Minecraft và kiểm tra file CurseForge.
- Khôi phục các file toàn vẹn source bị thiếu trong archive core đã tải lên (`src/core/config`, công cụ release-preflight và tài liệu theme contract) để import core và chạy test phát hành bình thường.
- Public API, contract launch, định dạng instance/provider và hành vi runtime vẫn tương thích với v1.0.2.

Beta này chưa thay đổi logic chọn Java, retry mạng, Forge legacy hay bảo vệ tài khoản.

Xác minh: `18 passed`; wheel đã vượt qua smoke test cài vào target riêng và import public API.
