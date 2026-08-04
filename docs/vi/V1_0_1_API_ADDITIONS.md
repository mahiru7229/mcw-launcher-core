# Các API mới của MCW Core 1.0.1

Tài liệu này liệt kê các thay đổi public API được bổ sung trong MCW Core 1.0.1. API của 1.0.0 vẫn tiếp tục hoạt động.

## Gợi ý cho lần chạy đầu

```python
from mcw_core.api.hardware.first_run_recommendation_service import FirstRunRecommendationService

recommendation = FirstRunRecommendationService.inspect()
print(recommendation.total_memory_mb)
print(recommendation.available_memory_mb)
print(recommendation.recommended_max_memory_mb)
print(recommendation.recommended_java_path)
for runtime in recommendation.java_installations:
    print(runtime.major, runtime.executable, runtime.source)
```

`inspect()` chạy theo cơ chế best-effort. Nếu quét Java lỗi, service trả danh sách runtime rỗng thay vì chặn ứng dụng khởi động. `fallback()` trả mức RAM an toàn mà không quét Java.

## Xác nhận lỗi tương thích

```python
from mcw_core import CompatibilityConfirmationRequired, LaunchRequest, get_default_core

core = get_default_core()
try:
    result = core.launch(LaunchRequest(instance="My Pack", offline_username="Player"))
except CompatibilityConfirmationRequired as request:
    print(request.instance_name)
    for issue in request.issues:
        print(issue.message)

    # Chỉ retry sau khi giao diện đã nhận xác nhận rõ ràng từ người dùng.
    result = core.launch(
        LaunchRequest(
            instance=request.instance_name,
            offline_username="Player",
            allow_compatibility_issues_once=True,
        )
    )
```

Lỗi loader/runtime hỏng, lỗi integrity, archive không an toàn và lỗi bảo mật không bao giờ trở thành lỗi có thể bỏ qua này.

## Chính sách managed content

```python
from mcw_core.api.config.managed_content_policy import ManagedContentPolicy

policy = ManagedContentPolicy.resolve(instance.settings, launcher_settings, "forge_preflight")
# "inherit", "ask", "block" hoặc "allow" tùy phạm vi.
```

Launcher Settings hỗ trợ `ask`, `block`, `allow`. Instance Settings hỗ trợ thêm `inherit`.

## Helper màu chữ

```python
from mcw_core.api.theme.theme_palette import (
    DEFAULT_THEME_PALETTE,
    contrast_ratio,
    derive_custom_text,
    is_readable_text,
)

palette = derive_custom_text(DEFAULT_THEME_PALETTE, "#f0e8ff")
print(palette.text_primary, palette.text_muted, palette.text_disabled)
print(contrast_ratio(palette.text_primary, "#20231f"))
print(is_readable_text(palette.text_primary, "#20231f"))
```

Các màu ngữ nghĩa như warning, error, success, link và selection không bị ghi đè.

## Migration resource pack và shader pack

`ContentPackManager` giờ dùng `<instance>/resourcepacks` và `<instance>/shaderpacks`. `migrate_legacy_location()` chuyển an toàn dữ liệu từng được v1.0.0 đặt nhầm trong `<instance>/minecraft/...` và không ghi đè file trùng tên.

Có thể thêm resource pack hoặc shader pack mới khi instance đang chạy. Thay thế, đổi trạng thái và xóa nội dung vẫn bị chặn đến khi Minecraft đóng.
