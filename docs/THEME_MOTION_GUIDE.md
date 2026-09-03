# MCW Theme Motion Guide

MCW Launcher v0.11.0-alpha.5 uses theme schema 5 for interface motion, toast notifications, and animation performance limits. Motion metadata never executes code; it only selects validated transition types, timings, easing curves, distances, effect strengths, and FPS limits.

## Manifest example

```json
{
  "schema_version": 5,
  "motion": {
    "page": {
      "type": "fade_slide",
      "duration_ms": 170,
      "easing": "out_cubic",
      "distance_px": 18
    },
    "button": {
      "hover_duration_ms": 100,
      "press_duration_ms": 70,
      "easing": "out_quad",
      "hover_strength": 0.08,
      "press_strength": 0.18
    },
    "dialog": {
      "type": "fade",
      "duration_ms": 160,
      "easing": "out_cubic"
    },
    "sidebar": {
      "duration_ms": 220,
      "easing": "out_cubic",
      "collapsed_width": 72
    },
    "launch_control": {
      "type": "fade",
      "duration_ms": 140,
      "easing": "out_cubic"
    },
    "toast": {
      "type": "slide_fade",
      "duration_ms": 180,
      "visible_duration_ms": 3000,
      "easing": "out_cubic",
      "distance_px": 24,
      "max_visible": 3
    },
    "performance": {
      "full_fps": 60,
      "reduced_fps": 30,
      "pause_when_hidden": true
    }
  }
}
```

## Page transitions

Supported `page.type` values:

- `none`
- `fade`
- `slide_left`
- `slide_right`
- `fade_slide`

`distance_px` is limited to `0..256`. Page duration is limited to `0..3000 ms`.

## Dialog and Launch Control transitions

`dialog.type` and `launch_control.type` support `none` and `fade`. Dialogs fade when shown. Launch Control uses the configured transition when Cancel appears or disappears, and status badges pulse when their state changes.

## Button interaction

Button hover and press effects use a subtle color-strength animation so PNG and CSS themes keep their original shapes. `hover_strength` and `press_strength` use values from `0.0` to `1.0`; press strength cannot be lower than hover strength.

## Sidebar

The sidebar can collapse to icon-only navigation. `collapsed_width` is limited to `56..160 px`. Labels remain available as tooltips while collapsed.

## Toast notifications

Supported `toast.type` values:

- `none`
- `fade`
- `slide`
- `slide_fade`

`visible_duration_ms` is limited to `500..30000`, while `max_visible` is limited to `1..8`. Toast icons resolve the following optional animation keys before falling back to static assets:

- `state.ready`
- `state.success`
- `state.warning`
- `state.error`

## Animation performance

- `full_fps`: `15..120`
- `reduced_fps`: `10..60`, and it cannot exceed `full_fps`
- `pause_when_hidden`: pauses the shared animation clock when every launcher window is hidden or minimized

The timeline is frozen while paused, so sprite animations do not jump forward after the window is restored.

## Easing values

- `linear`
- `in_quad`
- `out_quad`
- `in_out_quad`
- `in_cubic`
- `out_cubic`
- `in_out_cubic`
- `out_back`

## User motion modes

Launcher Settings provides three modes:

- **Full**: uses all theme motion values and `full_fps`.
- **Reduced**: shortens durations, softens button effects, and uses `reduced_fps`.
- **Off**: freezes sprite animation and changes state immediately.

Theme authors do not need separate manifests for these modes. The launcher applies the user's preference at runtime.

## Previewing a theme

Open **Launcher Settings → Appearance**. The Motion Preview card displays state animations, determinate progress, indeterminate progress, and a test toast without launching Minecraft.

## Compatibility and fallback

Themes using schema 1–4 remain valid. A theme without `motion` receives the built-in safe motion defaults. Invalid motion metadata is ignored and reported as a theme issue; the launcher continues using defaults.
