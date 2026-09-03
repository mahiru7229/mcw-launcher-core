# MCW Core v1.5.0 — Troubleshooting

## Core import được nhưng version sai

```python
import importlib.metadata
import mcw_core
print(importlib.metadata.version('mcw-core'))
print(mcw_core.__version__)
```

Nếu hai giá trị không phải `1.5.0`, kiểm tra virtual environment và package đang được
import thực tế (`python -m pip show mcw-core`).

## Core dùng nhầm data root

In root trước khi thao tác:

```python
print(core.paths)
```

Nếu app dùng nhiều `CorePaths` trong một process, nhớ rằng path registry bên dưới là
process-wide. Không chạy đồng thời hai Core root khác nhau trong cùng process.

## Linux vẫn ghi dữ liệu cạnh executable

Nếu bạn gọi `CorePaths.from_root(...)`, đây là explicit portable configuration. Nếu muốn
launcher bootstrap dùng XDG, không override path bằng portable root và bảo đảm
`MCW_PORTABLE` không được bật.

## Không mở được thư mục instance trên Linux

Không tự ghép path bằng backslash Windows. Luôn dùng `Path`/`CorePaths`/public path APIs.
Nếu UI mở thư mục bằng OS command, dùng platform-native opener (`xdg-open` trên Linux)
thay vì `explorer.exe` assumptions.

## Java không tương thích

```python
profile = core.instances.runtime_profile('Instance')
print(profile.required_java_major)
print(profile.configured_java_path)
```

Để Core tự chọn/provision, bỏ Java path thủ công. Nếu user chọn Java thủ công,
`set_java_runtime` sẽ validate major và có thể báo incompatibility.

## Forge/NeoForge yêu cầu xác nhận compatibility nhiều lần

Dùng `LaunchRequest.on_compatibility_confirmation` và trả quyết định cho chính exception
Core đưa ra. v1.5.0 hỗ trợ resumable confirmation để tránh resolve/check dependency lại
không cần thiết.

## CurseForge không hoạt động

Kiểm tra:

```python
from mcw_core.api.curseforge.curseforge_client import CurseForgeClient
print(CurseForgeClient.is_available())
print(CurseForgeClient.gateway_urls())
```

Core không bundle gateway URL hoặc API key. Deploy gateway source riêng, đặt
`CURSEFORGE_API_KEY` ở server và cấu hình HTTPS endpoint cho Core.

## Provider search bị lỗi khi offline

Kiểm tra connectivity snapshot và cache status của provider. Không xóa cache trước khi
chẩn đoán, vì cache có thể là dữ liệu duy nhất cho offline mode.

## Download pause không dừng ngay lập tức

Pause/cancel là cooperative. Task dừng tại checkpoint an toàn chứ không kill thread đang
ghi file. UI nên hiển thị trạng thái “pausing/cancelling” thay vì giả định synchronous stop.

## Instance báo đang chạy dù game đã tắt

Dùng runtime/run-lock/startup-recovery APIs. Không xóa lock thủ công trước khi kiểm tra PID
và stale state; startup recovery được thiết kế để làm việc đó an toàn hơn.

## Repair làm thay đổi nhiều file

Luôn chạy `scan` và review plan trước. Có thể tạo backup thủ công trước repair lớn. Không
xây nút “repair everything” bằng cách xóa thư mục libraries/assets/mods rồi download lại.

## Update prepare xong nhưng không apply được

Dùng `AutomaticUpdateInstaller.is_supported()` và platform installer tương ứng. Không unzip
thủ công package đã prepare vào thư mục đang chạy; updater cần verify/backup/rollback/restart
logic của platform.

## Diagnostics có dữ liệu nhạy cảm

Trước khi đưa payload tự tạo vào log/report:

```python
from mcw_core.api.security.sensitive_data_redactor import SensitiveDataRedactor
safe = SensitiveDataRedactor.redact_json(payload)
```

Không gửi token, password, API key hoặc credential store secret trong issue công khai.

## API trong docs không khớp source

Chạy:

```bash
python tools/generate_public_api_docs.py
```

Sau đó kiểm tra `docs/API_COVERAGE.json`. Generator lấy chữ ký trực tiếp từ public re-export
và implementation module tương ứng của source hiện tại.
