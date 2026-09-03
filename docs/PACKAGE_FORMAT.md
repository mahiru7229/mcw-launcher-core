# MCW Package Format 
> This document was created with assistance from ChatGPT.
## Overview

The launcher uses its own package format:

```
.mcwpack
```

The package format is designed to:

- Share instances
- Backup instances
- Import instances between launchers
- Preserve metadata and runtime settings

Internally, a `.mcwpack` file is a standard ZIP archive with a custom extension.

---

# Directory Structure

Example:

```text
My Instance.mcwpack
│
├── package.json
├── instance.json
├── settings.json
├── .mcw/
│   └── instance-icon.png
├── mods/
├── resourcepacks/
├── shaderpacks/
├── config/
├── saves/
└── ...
```

---

# package.json

This file describes the package itself.

Example:

```json
{
    "format": "mcwpack",
    "format_version": 1,

    "package_type": "instance",

    "launcher_name": "MCW Launcher",
    "launcher_version": "0.2.3-alpha",

    "created_at": "...",

    "include_saves": false,
    "instance_name": "My Instance",
    "instance_icon": ".mcw/instance-icon.png"
}
```

## Fields

| Field | Description |
|--------|-------------|
| format | Package identifier |
| format_version | Package format version |
| package_type | Package type |
| launcher_name | Launcher that generated the package |
| launcher_version | Launcher version |
| created_at | Export time |
| include_saves | Whether world saves are included |
| instance_name | Optional display name for package previews |
| instance_icon | Optional built-in icon key or archive-relative icon path |

---

# instance.json

Contains metadata describing the instance.

Example:

```json
{
    "id": "...",
    "name": "...",
    "version_id": "1.21.8",
    "mod_loader": [
        "vanilla",
        "-1"
    ]
}
```

---

# settings.json

Contains runtime settings.

Example:

```json
{
    "java": {
        "path": "",
        "min_memory": 1024,
        "max_memory": 2048,
        "arguments": []
    },

    "window": {
        "width": 1280,
        "height": 720,
        "fullscreen": false
    },

    "launch": {
        "game_arguments": []
    }
}
```

---

# Validation

Before importing, the launcher validates:

- package.json exists
- instance.json exists
- format == "mcwpack"
- supported format_version
- supported package_type

Packages failing validation are rejected.

---

# Future Compatibility

Future versions may introduce additional package types.

Possible examples:

- Instance Package
- World Package
- Modpack Package
- Resource Pack Package

Older launchers should reject packages with unsupported format versions.

---

# Design Decisions

## ZIP-based format

`.mcwpack` is based on the ZIP archive format.

Advantages:

- No custom compression algorithm
- Easy debugging
- Widely supported
- Cross-platform

---

## Separation of Metadata

Package metadata is stored in:

```
package.json
```

Instance metadata is stored in:

```
instance.json
```

This separation allows package information and instance information to evolve independently.

Custom instance icons are stored inside the instance and are exported with the other instance files. Legacy absolute icon paths are converted to an archive-relative `.mcw/instance-icon.<ext>` path during export.

---

# Current Format Version

```
Format: mcwpack

Version: 1
```