# MCW Core 1.0.1 API additions

This document lists public API changes introduced in MCW Core 1.0.1. Existing 1.0.0 APIs remain available.

## First-run recommendations

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

`inspect()` is best-effort. Java discovery failures return an empty runtime list instead of preventing application startup. `fallback()` returns safe memory defaults without scanning Java.

## Compatibility confirmation

```python
from mcw_core import CompatibilityConfirmationRequired, LaunchRequest, get_default_core

core = get_default_core()
try:
    result = core.launch(LaunchRequest(instance="My Pack", offline_username="Player"))
except CompatibilityConfirmationRequired as request:
    print(request.instance_name)
    for issue in request.issues:
        print(issue.message)

    # Retry only after the UI receives explicit user consent.
    result = core.launch(
        LaunchRequest(
            instance=request.instance_name,
            offline_username="Player",
            allow_compatibility_issues_once=True,
        )
    )
```

Hard loader/runtime, integrity, archive-safety, and security failures never use this bypassable exception.

## Managed-content policies

```python
from mcw_core.api.config.managed_content_policy import ManagedContentPolicy

policy = ManagedContentPolicy.resolve(instance.settings, launcher_settings, "forge_preflight")
# "inherit", "ask", "block", or "allow", depending on scope.
```

Global settings support `ask`, `block`, and `allow`. Instance settings also support `inherit`.

## Text palette helpers

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

Semantic warning, error, success, link, and selection colors are preserved.

## Resource and shader pack migration

`ContentPackManager` now uses `<instance>/resourcepacks` and `<instance>/shaderpacks`. `migrate_legacy_location()` safely migrates files created under the incorrect v1.0.0 `<instance>/minecraft/...` location without overwriting conflicts.

Adding a new resource or shader pack is allowed while the instance runs. Destructive replacement, state changes, and removal remain blocked until Minecraft closes.
