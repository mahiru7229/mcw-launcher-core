# Modrinth integration

## Tiếng Việt

MCW Launcher hỗ trợ duyệt và cài nội dung Fabric/Forge trực tiếp từ Modrinth.

### Mod

Mở một instance Fabric hoặc Forge, chọn **Manage mods**, sau đó chọn **Browse Modrinth**.

Launcher sẽ:

- Tìm mod theo loader đã chọn nhưng không ẩn dự án chỉ vì nhãn phiên bản Minecraft.
- Ưu tiên version có nhãn Minecraft chính xác, kế đến bản vá gần cùng dòng; mọi nhãn chỉ để tham khảo và không chặn cài đặt.
- Cho phép chọn mọi instance dùng đúng loader, kể cả khi phiên bản Minecraft không xuất hiện trong nhãn của nhà cung cấp.
- Tự cài các dependency `required` có thể tải từ Modrinth.
- Kiểm tra SHA-1 và SHA-512 trước khi thêm file vào instance.
- Lưu nguồn gốc project/version tại `.mcw/modrinth.json` để lần cập nhật sau thay đúng file cũ.

### Modpack

Trong trang **Instances**, chọn **Browse Modrinth modpacks**.

Launcher sẽ tải file `.mrpack`, kiểm tra manifest và tự:

- Chọn Minecraft version được pack yêu cầu.
- Cài đúng Fabric Loader hoặc Forge version.
- Tải các file dành cho client.
- Áp dụng `overrides`, sau đó `client-overrides`.
- Tạo instance mới chỉ sau khi toàn bộ file đã được chuẩn bị thành công.

Modpack Fabric và Forge được hỗ trợ. Pack NeoForge và Quilt sẽ bị từ chối rõ ràng.

### An toàn

- Không cho đường dẫn trong `.mrpack` thoát khỏi folder instance.
- Chặn file override ghi đè `instance.json`, `settings.json` và metadata `.mcw`.
- Chỉ chấp nhận URL HTTPS từ danh sách host được định dạng `.mrpack` cho phép.
- Không giải nén symbolic link.
- Có giới hạn số file, tổng dung lượng, kích thước override và độ dài đường dẫn.

## English

MCW Launcher can browse and install Fabric and Forge content directly from Modrinth.

### Mods

Open a Fabric or Forge instance, choose **Manage mods**, then **Browse Modrinth**.

The launcher filters by the selected loader but treats provider Minecraft-version labels as advisory. Exact and nearby patch labels are ranked first without hiding or blocking other versions or loader-matching instances. It installs required Modrinth dependencies, verifies SHA-1/SHA-512, and stores project provenance for safe updates.

### Modpacks

On the **Instances** page, choose **Browse Modrinth modpacks**. The launcher downloads the `.mrpack`, treats its manifest as authoritative, installs the declared Minecraft and Fabric Loader/Forge versions, downloads client files, applies `overrides` and `client-overrides`, then creates a new instance.

Fabric and Forge modpacks are supported in this release. NeoForge and Quilt packs remain unsupported.
