# Instance System
> This document was created with assistance from ChatGPT.
## Overview

The Instance System is the core of the launcher.

An **Instance** represents an independent Minecraft environment, including its own metadata, runtime settings, mods, resource packs, saves, and other files.

Unlike the legacy implementation where every instance was stored in a single `instances.json`, each instance is now completely isolated inside its own directory.

---

## Design Goals

The Instance System was designed with the following goals:

- Independent instances
- Easy backup
- Easy sharing
- Easy migration
- Minimal coupling
- Extensible architecture

---

## Directory Structure

```text
instances/
├── Gaming/
│   ├── instance.json
│   ├── settings.json
│   ├── mods/
│   ├── resourcepacks/
│   ├── shaderpacks/
│   ├── saves/
│   └── ...
│
└── Survival/
    ├── instance.json
    ├── settings.json
    └── ...
```

Each instance is completely self-contained.

---

# Metadata

Every instance stores its metadata in:

```text
instance.json
```

Example:

```json
{
    "id": "...",
    "name": "...",
    "version_id": "1.21.8",
    "mod_loader": [
        "vanilla",
        "-1"
    ],

    "created_at": "2026-07-15T10:00:00+00:00",
    "updated_at": "2026-07-15T12:00:00+00:00",
    "last_played": "2026-07-15T12:00:00+00:00",
    "total_play_time_seconds": 3600,
    "last_exit_code": 0,
    "last_launch_crashed": false,
    "last_launch_state": "finished",
    "last_started_at": "2026-07-15T11:00:00+00:00",
    "last_finished_at": "2026-07-15T12:00:00+00:00",
    "last_game_log": ".../logs/minecraft-2026-07-15_18-30-00.log",
    "last_crash_report": "",

    "icon": ".mcw/instance-icon.png",
    "notes": "",

    "launcher_version": "v0.12.0",
    "metadata_version": 3
}
```

Metadata only contains information describing the instance.

Runtime configuration is intentionally stored elsewhere.

## Icon storage

The default icon is represented by the built-in key `grass_block`. A custom icon selected through the public API or GUI is copied into the instance:

```text
.mcw/instance-icon.png
```

Keeping the file inside the instance makes clone, backup, export, and import behavior predictable.

## Runtime states

The display state is resolved with this precedence:

```text
live preparing lock -> loading
live Minecraft PID  -> running
last crashed session -> crashed
last normal session  -> finished
no previous session  -> ready
```

Only the result of the last completed session is persisted. Live `loading` and `running` state comes from the run-lock system.


---

# Runtime Settings

Runtime settings are stored inside:

```text
settings.json
```

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

This file controls how Minecraft is launched.

---

# Legacy Compatibility

Older versions of the launcher stored every instance inside:

```text
instances.json
```

The new implementation keeps compatibility through **lazy migration**.

Workflow:

```text
load()

↓

instance.json exists?
      │
      ├── Yes
      │      ↓
      │   Load metadata
      │
      └── No
             ↓
      Read instances.json
             ↓
      Create instance.json
             ↓
      Load new metadata
```

This allows existing users to migrate automatically without manual conversion.

---

# Instance Lifecycle

An instance can go through the following lifecycle.

```text
Create
    │
    ▼
Edit
    │
    ▼
Clone
    │
    ▼
Export
    │
    ▼
Import
    │
    ▼
Launch
    │
    ▼
Rename
    │
    ▼
Delete
```

---

# Clone

The launcher supports cloning an existing instance.

During cloning:

- Generate a new UUID
- Change instance name
- Preserve runtime settings
- Preserve descriptive metadata such as icon and notes
- Reset play time, exit state, runtime history, and repair history
- Optionally copy world saves

```python
clone(
    source_name,
    new_name,
    include_saves=False
)
```

---

# Package System

Instances can be exported into the launcher package format.

```text
.mcwpack
```

Package contents:

```text
package.json
instance.json
settings.json
mods/
resourcepacks/
shaderpacks/
...
```

Export and Import are handled by `PackageManager`.

The `InstanceManager` only manages instance creation and restoration.

---

# Architecture

The Instance System follows the Single Responsibility Principle.

```text
InstanceManager
│
├── Create
├── Load
├── Rename
├── Delete
├── Clone
├── Import
└── Export
```

Runtime settings are managed separately.

```text
SettingsManager
│
├── Load
├── Save
├── Edit
└── Default Settings
```

Package handling is isolated.

```text
PackageManager
│
├── Export
├── Extract
├── Validate
└── Package Metadata
```

---

# Design Decisions

## Per-instance Metadata

Metadata is stored inside each instance instead of a centralized file.

Advantages:

- Easier backup
- Easier sharing
- Independent instances
- Less coupling

---

## No Stored Instance Directory

The launcher never stores absolute instance paths.

Instead:

```python
Paths.load_instance_dir(instance.name)
```

is used whenever the directory is required.

This avoids duplicated information and keeps metadata portable.

---

## Separation of Responsibilities

The system separates three different responsibilities.

### Instance

Responsible for:

- Metadata
- Lifecycle
- Clone
- Import
- Export

### Settings

Responsible for:

- Java
- Window
- JVM Arguments
- Game Arguments

### Package

Responsible for:

- `.mcwpack`
- Validation
- Package Metadata
- Extraction

---

# Current Status

Implemented in **v0.2.3-alpha**

- ✅ Create Instance
- ✅ Load Instance
- ✅ Rename Instance
- ✅ Delete Instance
- ✅ Clone Instance
- ✅ Per-instance Metadata
- ✅ Per-instance Settings
- ✅ Export Package
- ✅ Import Package
- ✅ Legacy Migration
- ✅ Settings Editing