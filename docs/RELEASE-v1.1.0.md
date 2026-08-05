# MCW Launcher v1.1.0

## Tiếng Việt

MCW Launcher **v1.1.0** là bản stable đầu tiên của nhánh 1.1. Bản phát hành này tập trung vào độ ổn định khi cài mod loader, lựa chọn Java, khả năng phục hồi lỗi mạng và tương thích Forge legacy.

### Điểm mới ở bản stable

#### Chọn chính xác phiên bản mod loader khi tạo instance

- Khi chọn Fabric, Quilt, Forge hoặc NeoForge, hộp thoại **Add Instance** tải danh sách phiên bản loader tương thích với phiên bản Minecraft đã chọn.
- Người dùng chọn chính xác phiên bản loader trước khi tạo instance.
- Nút **Create Instance** bị khóa khi loader không có phiên bản tương thích hoặc metadata chưa tải xong.
- Vanilla không yêu cầu phiên bản loader riêng.
- Danh sách được cập nhật lại khi đổi Minecraft version, loader hoặc bộ lọc snapshot.

Thay đổi này ngăn trường hợp instance được tạo trước rồi mới thất bại vì loader không phát hành bản tương thích cho phiên bản Minecraft đó.

#### Sửa liên kết tải thủ công CurseForge đôi lúc mở trang 404

- Ưu tiên mở trang file CurseForge ổn định thay vì URL CDN vừa tải thất bại hoặc đã hết hiệu lực.
- Dùng URL project theo slug do metadata CurseForge cung cấp.
- Loại bỏ fallback project URL dạng ID số vốn có thể dẫn tới trang không tồn tại.
- Nếu không lấy được metadata project, launcher mở trang tìm kiếm CurseForge theo project ID thay vì tạo một URL project không chắc chắn.
- Lưu `projectUrl` vào registry để những lần repair, retry và manual download sau dùng lại đúng liên kết.

### Tổng hợp thay đổi của nhánh v1.1.0

#### Bản dịch và giao diện

- Rà soát các status/progress còn hardcode tiếng Anh và đưa chúng qua hệ thống ngôn ngữ.
- Cửa sổ quản lý instance nâng cao responsive hơn ở màn hình nhỏ và display scaling.
- Khu vực mod loader tự đổi bố cục ngang/dọc và các nút tự xếp 3/2/1 cột.
- Xóa form tạo instance trùng lặp khỏi Advanced Instance Management; việc tạo instance chỉ còn ở luồng Add Instance chính.

#### Java theo instance và tự phục hồi

- Thêm lựa chọn Java **Tự động** hoặc **Đường dẫn tùy chọn**.
- Java tùy chọn được kiểm tra trước khi lưu và trước khi launch.
- Khi Java sai đường dẫn, sai major hoặc lỗi runtime đáng tin cậy, launcher tự chọn Java tương thích và thử lại một lần.
- Forge/NeoForge installer dùng cùng lựa chọn Java của instance trong các luồng cài, đổi, repair và restore.

#### Retry mạng có giới hạn

- Metadata network task tự thử tối đa 3 lần với backoff ngắn.
- Chỉ retry timeout, DNS/kết nối tạm thời, rate limit và lỗi server có khả năng phục hồi.
- Sau khi tự động retry thất bại, launcher hiện nút **Retry** để chạy lại đúng tác vụ và tham số trước đó.
- Ngăn chạy trùng task và giới hạn số callback được giữ trong bộ nhớ.

#### Forge legacy

- Chuẩn hóa game arguments để các tùy chọn đơn trị như `--gameDir` chỉ xuất hiện một lần.
- Nhận diện runtime Forge rất cũ dùng artifact `net.minecraftforge:minecraftforge`.
- Khôi phục dependency Maven legacy không có metadata `downloads.artifact` hiện đại.
- Xử lý đúng native classifier của LWJGL/JInput và áp dụng OS rule trước khi tải.
- Bổ sung LaunchWrapper vào classpath khi profile Forge legacy yêu cầu.
- Xác minh SHA-1 client JAR trước khi bật cờ tương thích chứng chỉ cho Forge/FML cũ.

#### Progress bảo vệ tài khoản

- Tác vụ reprotect tài khoản luôn trả progress về trạng thái thành công hoặc thất bại rõ ràng.
- Không còn giữ thanh progress ở trạng thái đang xử lý sau khi tác vụ kết thúc.

### Phiên bản và gói phát hành

- Launcher runtime: `v1.1.0`
- Update channel: `stable`
- Python distribution: `mcw-core 1.1.0`
- Existing public MCW Core calls remain compatible; this release does not intentionally remove or rename existing public contracts.

### Xác thực

- Launcher test suite: `1336 passed, 86 skipped, 2 warnings`.
- MCW Core test suite: `1291 passed, 2 warnings`.
- Python `compileall`: đạt cho cả launcher và core.
- Wheel `mcw-core 1.1.0` được cài thử vào thư mục độc lập; runtime version, distribution metadata và public CurseForge API đều được xác minh.
- Các GUI test cần PySide6 bị skip trong môi trường build headless; cần smoke test Windows cho hộp thoại Add Instance và mở trang CurseForge.

---

## English

MCW Launcher **v1.1.0** is the first stable release in the 1.1 line. It focuses on mod-loader installation reliability, per-instance Java selection, bounded network recovery, and legacy Forge compatibility.

### Stable-release additions

#### Explicit loader-version selection during instance creation

- Selecting Fabric, Quilt, Forge, or NeoForge now loads the exact loader versions compatible with the selected Minecraft version.
- A loader version must be selected before the instance can be created.
- **Create Instance** remains disabled while metadata is loading or when no compatible loader release exists.
- Vanilla does not require a separate loader version.
- The list refreshes when the Minecraft version, loader, or snapshot filter changes.

This prevents creating an instance that later fails because the chosen loader has no release for that Minecraft version.

#### CurseForge manual-download links no longer prefer intermittent 404 targets

- The launcher prefers the stable CurseForge file page instead of a CDN URL that has just failed or expired.
- Project pages use the slug-based URL provided by CurseForge metadata.
- Numeric project-ID URL fallbacks that may not resolve to a real page are no longer generated.
- When project metadata cannot be resolved, the launcher opens a CurseForge search page for the project ID.
- `projectUrl` is persisted for later repair, retry, and manual-download flows.

### v1.1.0 branch summary

- Translation audit for remaining hardcoded runtime status strings.
- Responsive advanced instance/mod-loader management and removal of the duplicate create-instance form.
- Automatic/custom Java selection with one bounded runtime recovery attempt.
- Forge/NeoForge installers use the instance Java choice.
- Three-round metadata retry with a manual Retry action after exhaustion.
- Forge legacy singleton-argument normalization, runtime recognition, LaunchWrapper/classpath recovery, native classifier handling, OS-rule filtering, and certificate compatibility after client SHA-1 verification.
- Account-security reprotection progress always reaches a final success or failure state.

### Release metadata

- Launcher runtime: `v1.1.0`
- Update channel: `stable`
- Python distribution: `mcw-core 1.1.0`
- Existing public MCW Core calls remain compatible; no existing public contract is intentionally removed or renamed.

### Validation

- Launcher test suite: `1336 passed, 86 skipped, 2 warnings`.
- MCW Core test suite: `1291 passed, 2 warnings`.
- Python `compileall`: passed for both launcher and core.
- The `mcw-core 1.1.0` wheel is installed into an isolated directory; runtime version, distribution metadata, and the public CurseForge API are verified.
- PySide6 GUI tests are skipped in the headless build environment, so Windows smoke testing is still required for the Add Instance dialog and CurseForge page opening.
