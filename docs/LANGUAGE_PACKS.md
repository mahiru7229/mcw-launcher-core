# MCW Launcher language packs

MCW Launcher discovers language packs from JSON files inside the `lang` directory.

Built-in packs:

- `lang/en-US.json` — English - US
- `lang/vi-VN.json` — Tiếng Việt - Việt Nam

## Translation keys

Language packs use stable semantic keys instead of using the English sentence as the key.

```json
{
  "translations": {
    "navigation.home": "Home",
    "instance.create.success": "Instance created successfully.",
    "instance.delete.confirm": "Delete {name}?"
  }
}
```

Application code can translate a key directly:

```python
tr("instance.create.success")
tr("instance.delete.confirm", name=instance.name)
```

Key format:

```text
<area>.<feature>.<element-or-state>
```

Examples:

```text
common.save
navigation.instances
account.create.success
instance.create.title
instance.create.success
instance.delete.confirm
mod_manager.add_files
launcher_settings.language.label
error.network.message
progress.stage.assets
```

Use specific keys such as `instance.create.success`, not broad keys such as `instance.success`, when several operations can succeed independently.

## Backward compatibility

`en-US.json` contains an `aliases` object. It maps the old English GUI text to semantic keys:

```json
{
  "aliases": {
    "Home": "navigation.home",
    "Create instance": "instance.create.title"
  }
}
```

This allows existing widgets to continue working while new code uses semantic keys directly. New language packs do not need to copy the `aliases` object.

## Add another language

1. Copy `lang/en-US.json`.
2. Rename it using a locale code, for example `ja-JP.json`.
3. Update `meta.locale` and `meta.name`.
4. Remove the `aliases` object from the copied file.
5. Translate values inside `translations` while keeping every semantic key unchanged.
6. Keep placeholders such as `{count}`, `{name}`, `{version}`, and `{path}` unchanged.
7. Place the JSON file in the `lang` folder next to the launcher.
8. Open **Launcher Settings** and choose **Reload language packs**.

Example:

```json
{
  "meta": {
    "locale": "ja-JP",
    "name": "日本語 - 日本",
    "version": 1
  },
  "translations": {
    "navigation.home": "ホーム",
    "navigation.launcher_settings": "ランチャー設定",
    "version.count_available": "{count} 個のバージョンが利用可能"
  }
}
```

## Fallback behavior

When a key is missing from the selected language, MCW Launcher uses this order:

1. Selected language.
2. `en-US` value for the same semantic key.
3. The supplied `default` value.
4. The key itself.

Example:

```python
tr("instance.create.success", default="Created")
```

## Validation helpers

`LanguageManager` provides helpers for validating packs:

```python
language_manager.missing_keys("vi-VN")
language_manager.placeholder_mismatches("vi-VN")
```

A placeholder mismatch such as `{name}` becoming `{instance}` is reported because it can break runtime formatting.

## Rules

- The filename should match `meta.locale`.
- `meta.version` must currently be `1`.
- Keep translation keys unchanged.
- Keep named placeholders unchanged.
- Missing entries fall back to `en-US`.
- Invalid JSON files are ignored instead of preventing launcher startup.
- In a packaged build, built-in packs are bundled with the EXE.
- Files in the external `lang` folder override bundled packs with the same locale.
