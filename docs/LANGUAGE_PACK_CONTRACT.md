# MCW Core Language Pack Contract

MCW Core language packs are UTF-8 JSON files stored under `lang/`.

```json
{
  "meta": {
    "locale": "vi-VN",
    "name": "Tiếng Việt"
  },
  "translations": {
    "navigation.instances": "Instance",
    "navigation.launcher_settings": "Cài đặt launcher"
  },
  "aliases": {}
}
```

## Rules for external launchers

1. Use semantic keys such as `navigation.launcher_settings` in source code.
2. Do not persist rendered English text as an identifier.
3. Keep the same translation-key set in every locale.
4. Preserve placeholder names exactly between locales.
5. Treat aliases as migration compatibility only.
6. Reload language packs before selecting a locale if files may have changed.
7. For large widget trees, prefer applying language changes after restarting the frontend process rather than partially retranslating live widgets.

## Relevant runtime API

```python
from mcw_core.api.language.language_manager import language_manager, tr

language_manager.reload()
language_manager.set_language("vi-VN", notify=False)
print(tr("navigation.launcher_settings"))
```

Expected output:

```text
Cài đặt launcher
```
