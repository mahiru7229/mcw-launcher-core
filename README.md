# MCW Core 1.0.2

MCW Core 1.0.2 is a metadata-alignment hotfix released with MCW Launcher v1.0.2. The launcher restart fix lives in the PySide6 GUI layer, so the public core API and runtime behavior remain unchanged from 1.0.1.

## Install

```bash
python -m pip install mcw_core-1.0.2-py3-none-any.whl
```

Verify:

```bash
python -c "import mcw_core; print(mcw_core.__version__)"
```

Expected output:

```text
1.0.2
```

## Compatibility

- Public imports from `mcw_core` and `mcw_core.api.*` remain compatible with 1.0.1.
- No new public class, method, field, exception, or behavior is introduced.
- The default CurseForge gateway remains empty.
- Existing instance, package, language, theme, and provider formats are unchanged.

## Tiếng Việt

MCW Core 1.0.2 chỉ đồng bộ metadata phiên bản với MCW Launcher v1.0.2. Lỗi restart nằm ở lớp GUI PySide6, vì vậy public API và hành vi runtime của core không thay đổi so với 1.0.1.

Ứng dụng bên ngoài vẫn nên import từ `mcw_core` hoặc `mcw_core.api.*`.

Xem [`docs/RELEASE-v1.0.2.md`](docs/RELEASE-v1.0.2.md).
