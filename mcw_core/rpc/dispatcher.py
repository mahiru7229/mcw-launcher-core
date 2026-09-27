from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
import re
from threading import RLock
from typing import Any
import zipfile

from src.config import VERSION, VERSION_ID
from mcw_core.facade import MCWCore
from mcw_core.models import InstanceCreateRequest
from mcw_core.paths import CorePaths
from mcw_core.rpc.protocol import RpcError, RpcEvent, RpcRequest, RpcResponse, to_json_compatible

try:
    from mcw_core.api.instance.settings_manager import SettingsManager
    from mcw_core.api.update.hotfix_manager import HotfixManager
    from mcw_core.api.mod.mod_manager import ModManager
    from mcw_core.api.mod.mod_compatibility_manager import ModCompatibilityManager
    from mcw_core.api.content.content_pack_manager import ContentPackManager
    from mcw_core.api.instance.world_manager import WorldManager
    from mcw_core.api.instance.screenshot_manager import ScreenshotManager
    from mcw_core.api.backup.instance_backup_manager import InstanceBackupManager
    from mcw_core.api.security.sensitive_data_redactor import SensitiveDataRedactor
    from mcw_core.api.diagnostics.diagnostics_manager import DiagnosticsManager
    from mcw_core.api.modrinth.modrinth_client import ModrinthClient
except Exception:
    SettingsManager = None  # type: ignore[assignment]
    HotfixManager = None  # type: ignore[assignment]
    ModManager = None  # type: ignore[assignment]
    ModCompatibilityManager = None  # type: ignore[assignment]
    ContentPackManager = None  # type: ignore[assignment]
    WorldManager = None  # type: ignore[assignment]
    ScreenshotManager = None  # type: ignore[assignment]
    InstanceBackupManager = None  # type: ignore[assignment]
    SensitiveDataRedactor = None  # type: ignore[assignment]
    DiagnosticsManager = None  # type: ignore[assignment]
    ModrinthClient = None  # type: ignore[assignment]


class CoreRpcDispatcher:
    """Headless JSON-RPC 2.0 command dispatcher for MCW Core v1.8.0.

    Provides a single, GUI-independent JSON gateway for all MCW Core operations
    so any UI frontend (PySide6, Tauri/TypeScript, C#, CLI) can interact with
    the engine without importing internal ``src.core`` modules.
    """

    def __init__(
        self,
        core: MCWCore | None = None,
        root: Path | str | None = None,
        data_root: Path | str | None = None,
    ) -> None:
        resolved_root = root if root is not None else data_root
        if core is not None:
            self.core = core
        else:
            paths = CorePaths.from_root(resolved_root) if resolved_root is not None else CorePaths.current()
            self.core = MCWCore(paths)
        self._lock = RLock()
        self._listeners: list[Callable[[RpcEvent], None]] = []

    def subscribe(self, callback: Callable[[RpcEvent], None]) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(callback)

        def _unsubscribe() -> None:
            with self._lock:
                if callback in self._listeners:
                    self._listeners.remove(callback)

        return _unsubscribe

    def emit_event(self, event_name: str, data: dict[str, Any] | None = None) -> RpcEvent:
        evt = RpcEvent(event=event_name, data=data or {})
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(evt)
            except Exception:
                pass
        return evt

    def handle_json(self, raw_payload: str | bytes | dict[str, Any]) -> str:
        """Executes a JSON-RPC 2.0 request and returns a serialized JSON-RPC 2.0 response string."""
        response = self.dispatch(raw_payload)
        return response.to_json()

    def dispatch(self, raw_payload: str | bytes | dict[str, Any] | RpcRequest) -> RpcResponse:
        req_id: str | int | None = None
        try:
            req = raw_payload if isinstance(raw_payload, RpcRequest) else RpcRequest.from_raw(raw_payload)
            req_id = req.id
        except Exception as exc:
            return RpcResponse(id=req_id, error=RpcError(code=-32700, message=f"Invalid JSON-RPC request: {exc}"))

        handler_map: dict[str, Callable[[dict[str, Any]], Any]] = {
            "system.ping": self._rpc_system_ping,
            "system.version": self._rpc_system_version,
            "system.hotfix_status": self._rpc_system_hotfix_status,
            "instances.list": self._rpc_instances_list,
            "instances.get": self._rpc_instances_get,
            "instances.create": self._rpc_instances_create,
            "instances.rename": self._rpc_instances_rename,
            "instances.clone": self._rpc_instances_clone,
            "instances.delete": self._rpc_instances_delete,
            "instances.set_icon": self._rpc_instances_set_icon,
            "instances.reset_icon": self._rpc_instances_reset_icon,
            "instances.set_metadata": self._rpc_instances_set_metadata,
            "instances.health": self._rpc_instances_health,
            "instances.runtime_profile": self._rpc_instances_runtime_profile,
            "instances.set_java_runtime": self._rpc_instances_set_java_runtime,
            "instances.set_memory": self._rpc_instances_set_memory,
            "instances.set_jvm_args": self._rpc_instances_set_jvm_args,
            "instances.change_loader": self._rpc_instances_change_loader,
            "instances.kill": self._rpc_instances_kill,
            "java.scan": self._rpc_java_scan,
            "java.install": self._rpc_java_install,
            "content.list": self._rpc_content_list,
            "content.compatibility": self._rpc_content_compatibility,
            "catalog.search": self._rpc_catalog_search_modrinth,
            "catalog.search_modrinth": self._rpc_catalog_search_modrinth,
            "worlds.list": self._rpc_worlds_list,
            "screenshots.list": self._rpc_screenshots_list,
            "diagnostics.redact": self._rpc_diagnostics_redact,
            "diagnostics.export_bundle": self._rpc_diagnostics_export_bundle,
            "operations.pause": self._rpc_operations_pause,
            "operations.resume": self._rpc_operations_resume,
            "operations.cancel": self._rpc_operations_cancel,
            "operations.state": self._rpc_operations_state,
        }

        handler = handler_map.get(req.method)
        if handler is None:
            return RpcResponse(
                id=req_id,
                error=RpcError(code=-32601, message=f"Unknown RPC method: '{req.method}'"),
            )

        try:
            result = handler(req.params)
            return RpcResponse(id=req_id, result=to_json_compatible(result))
        except Exception as exc:
            return RpcResponse(
                id=req_id,
                error=RpcError(code=-32000, message=str(exc), data={"type": type(exc).__name__}),
            )

    # --- System & Hotfix ---

    def _rpc_system_ping(self, _params: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "pong": True,
            "version": VERSION,
            "version_id": VERSION_ID,
            "protocol": "jsonrpc-2.0",
            "data_root": str(self.core.paths.root),
        }

    def _rpc_system_version(self, _params: dict[str, Any]) -> dict[str, Any]:
        return {
            "version": VERSION,
            "version_id": VERSION_ID,
            "data_root": str(self.core.paths.root),
        }

    def _rpc_system_hotfix_status(self, _params: dict[str, Any]) -> dict[str, Any]:
        patch_label = f"v{VERSION_ID} Live"
        if HotfixManager is not None:
            try:
                mgr = HotfixManager()
                state = mgr.load_state() if hasattr(mgr, "load_state") else None
                if state and getattr(state, "target_version", ""):
                    patch_label = f"v{state.target_version} Live"
            except Exception:
                pass
        return {
            "patch_label": patch_label,
            "cdn_label": "HKG / SIN OK",
            "version_id": VERSION_ID,
        }

    # --- Instances ---

    def _serialize_instance(self, inst: Any) -> dict[str, Any]:
        loader_name, loader_ver = self.core.loaders.normalize(getattr(inst, "mod_loader", None))
        settings = SettingsManager.load(inst) if SettingsManager else None
        mem_mb = int(getattr(settings, "max_memory", 4096)) if settings else 4096
        java_p = str(getattr(settings, "java_path", "") or "").strip() if settings else ""
        icon_file = self.core.paths.instances_root / inst.name / "icon.png"
        return {
            "name": inst.name,
            "version_id": str(getattr(inst, "version_id", "1.21.1")),
            "loader_name": loader_name,
            "loader_version": loader_ver,
            "favorite": bool(getattr(inst, "favorite", False)),
            "group": str(getattr(inst, "group", "Default") or "Default"),
            "memory_mb": mem_mb,
            "java_path": java_p,
            "icon_path": str(icon_file) if icon_file.is_file() else None,
        }

    def _rpc_instances_list(self, _params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            return [self._serialize_instance(i) for i in self.core.instances.list()]
        except Exception:
            return []

    def _rpc_instances_get(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name", "")).strip()
        inst = self.core.instances.load(name)
        return self._serialize_instance(inst)

    def _rpc_instances_create(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name", "")).strip()
        version_id = str(params.get("version_id", "1.21.1")).strip()
        loader_name = str(params.get("loader_name", "vanilla")).strip()
        loader_version = str(params.get("loader_version", "auto")).strip() or "auto"
        created = self.core.instances.create(
            InstanceCreateRequest(
                name=name,
                version_id=version_id,
                loader_name=loader_name,
                loader_version=loader_version,
            )
        )
        return self._serialize_instance(created)

    def _rpc_instances_rename(self, params: dict[str, Any]) -> dict[str, Any]:
        old_name = str(params.get("old_name", "")).strip()
        new_name = str(params.get("new_name", "")).strip()
        path = self.core.instances.rename(old_name, new_name)
        return {"old_name": old_name, "new_name": new_name, "path": str(path)}

    def _rpc_instances_clone(self, params: dict[str, Any]) -> dict[str, Any]:
        source_name = str(params.get("source_name", "")).strip()
        target_name = str(params.get("target_name", "")).strip()
        include_saves = bool(params.get("include_saves", True))
        cloned = self.core.instances.clone(source_name, target_name, include_saves=include_saves)
        return self._serialize_instance(cloned)

    def _rpc_instances_delete(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name", "")).strip()
        deleted = bool(self.core.instances.delete(name))
        return {"name": name, "deleted": deleted}

    def _rpc_instances_set_icon(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name", "")).strip()
        icon_path = Path(str(params.get("icon_path", "")))
        updated = self.core.instances.set_icon(name, icon_path)
        return self._serialize_instance(updated)

    def _rpc_instances_reset_icon(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name", "")).strip()
        updated = self.core.instances.reset_icon(name)
        return self._serialize_instance(updated)

    def _rpc_instances_set_metadata(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name", "")).strip()
        favorite = params.get("favorite")
        group = params.get("group")
        updated = self.core.instances.set_library_metadata(name, favorite=favorite, group=group)
        return self._serialize_instance(updated)

    def _rpc_instances_health(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name", "")).strip()
        report = self.core.instances.health(name)
        return {
            "healthy": bool(getattr(report, "healthy", True)),
            "required_java_major": int(getattr(report, "required_java_major", 21) or 21),
        }

    def _rpc_instances_runtime_profile(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name", "")).strip()
        return to_json_compatible(self.core.instances.runtime_profile(name))

    def _rpc_instances_set_java_runtime(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name", "")).strip()
        java_path = str(params.get("java_path", "")).strip()
        return to_json_compatible(self.core.instances.set_java_runtime(name, java_path))

    def _rpc_instances_set_memory(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name") or params.get("instance", "")).strip()
        max_mb = int(params.get("max_memory_mb") or params.get("max_mb", 4096))
        min_mb = int(params.get("min_memory_mb") or params.get("min_mb", 1024))
        if SettingsManager is not None:
            inst = self.core.instances.load(name)
            SettingsManager.update_memory(inst, min_mb, max_mb)
        return {"name": name, "min_memory_mb": min_mb, "max_memory_mb": max_mb}

    def _rpc_instances_set_jvm_args(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name") or params.get("instance", "")).strip()
        args = params.get("arguments") or params.get("args") or []
        if isinstance(args, str):
            args = args.split()
        if SettingsManager is not None:
            inst = self.core.instances.load(name)
            SettingsManager.update_jvm_arguments(inst, list(args))
        return {"name": name, "arguments": list(args)}

    def _rpc_instances_change_loader(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name") or params.get("instance", "")).strip()
        loader_name = str(params.get("loader_name", "vanilla")).strip()
        loader_version = str(params.get("loader_version", "auto")).strip() or "auto"
        updated = self.core.instances.change_loader(name, loader_name, loader_version)
        return self._serialize_instance(updated)

    def _rpc_instances_kill(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name") or params.get("instance", "")).strip()
        killed = bool(self.core.instances.kill(name))
        return {"name": name, "killed": killed}

    # --- Java ---

    def _rpc_java_scan(self, _params: dict[str, Any]) -> list[dict[str, Any]]:
        results = []
        for diag in self.core.java.scan():
            exe = str(getattr(diag, "executable", ""))
            if exe:
                major = int(getattr(diag, "major_version", 21) or 21)
                ver = str(getattr(diag, "version_string", f"{major}.0") or f"{major}.0")
                vendor = str(getattr(diag, "vendor", "OpenJDK") or "OpenJDK")
                results.append({
                    "name": f"Java {ver} ({vendor})",
                    "version": ver,
                    "vendor": vendor,
                    "major": major,
                    "path": exe,
                    "managed": False,
                })
        return results

    def _rpc_java_install(self, params: dict[str, Any]) -> dict[str, Any]:
        major = int(params.get("major", 21))
        installed_path = self.core.java.install(major)
        return {"major": major, "path": str(installed_path)}

    # --- Content, Mods, Worlds, Screenshots ---

    def _rpc_content_list(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        name = str(params.get("name") or params.get("instance", "")).strip()
        content_type = str(params.get("content_type") or params.get("type", "mods")).strip()
        inst = self.core.instances.load(name)
        if content_type in ("mods", "mod") and ModManager is not None:
            return [
                {
                    "name": getattr(m, "name", m.file_name),
                    "version": getattr(m, "version", "1.0"),
                    "author": ", ".join(getattr(m, "authors", ())) or "Community",
                    "category": getattr(m, "source", "Mod").capitalize(),
                    "size_mb": round(getattr(m, "file_size", 1048576) / (1024 * 1024), 2),
                    "enabled": bool(getattr(m, "enabled", True)),
                    "dep_ok": getattr(m, "status", "Ready") == "Ready",
                }
                for m in ModManager.list_mods(inst)
            ]
        if content_type in ("shaderpacks", "shader", "resourcepacks", "resourcepack") and ContentPackManager is not None:
            kind = "shader" if "shader" in content_type else "resourcepack"
            return [
                {
                    "name": getattr(e, "project_name", e.file_name),
                    "version": getattr(e, "version_number", "1.0") or "1.0",
                    "category": "Shader" if kind == "shader" else "ResourcePack",
                    "size_mb": round(getattr(e, "size", 1048576) / (1024 * 1024), 2),
                    "enabled": bool(getattr(e, "enabled", True)),
                }
                for e in ContentPackManager.list_entries(inst, kind)
            ]
        return []

    def _rpc_content_compatibility(self, params: dict[str, Any]) -> list[str]:
        name = str(params.get("name") or params.get("instance", "")).strip()
        if ModCompatibilityManager is None:
            return []
        inst = self.core.instances.load(name)
        report = ModCompatibilityManager.scan(inst)
        return [str(getattr(iss, "message", iss)) for iss in (getattr(report, "issues", None) or ())]

    def _rpc_catalog_search_modrinth(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        if ModrinthClient is None:
            return []
        query = str(params.get("query", "")).strip()
        project_type = str(params.get("project_type", "mod")).strip()
        hits = ModrinthClient.search_projects(query=query, project_type=project_type, limit=12)
        return [
            {
                "id": getattr(h, "slug", None) or getattr(h, "project_id", "mod"),
                "name": getattr(h, "title", "Modrinth Project"),
                "title": getattr(h, "title", "Modrinth Project"),
                "author": getattr(h, "author", "Community"),
                "provider": "Modrinth",
                "type": project_type,
                "downloads": f"{getattr(h, 'downloads', 1000):,}",
                "version": "Latest",
                "summary": getattr(h, "description", ""),
            }
            for h in (hits or ())
        ]

    def _rpc_worlds_list(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        name = str(params.get("name") or params.get("instance", "")).strip()
        if WorldManager is None:
            return []
        inst_dir = self.core.paths.instances_root / name
        return [
            {
                "name": w.display_name,
                "folder": w.folder_name,
                "mode": w.game_mode.capitalize(),
                "gamemode": w.game_mode.capitalize(),
                "last_played": "Gần đây",
                "size": f"{round(w.folder_size_bytes / (1024 * 1024), 1)} MB",
                "size_mb": round(w.folder_size_bytes / (1024 * 1024), 1),
                "seed": "N/A",
            }
            for w in WorldManager.list_worlds(inst_dir)
        ]

    def _rpc_screenshots_list(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        name = str(params.get("name") or params.get("instance", "")).strip()
        if ScreenshotManager is None:
            return []
        inst_dir = self.core.paths.instances_root / name
        return [
            {
                "name": s.file_name,
                "resolution": "1920x1080",
                "date": datetime.fromtimestamp(s.created_timestamp).strftime("%d/%m/%Y"),
                "caption": f"Ảnh chụp trong game ({round(s.file_size_bytes / 1024, 1)} KB)",
                "path": str(s.path),
            }
            for s in ScreenshotManager.list_screenshots(inst_dir)
        ]

    # --- Diagnostics & Security ---

    def _rpc_diagnostics_redact(self, params: dict[str, Any]) -> dict[str, str]:
        text = str(params.get("text", ""))
        out = text
        if SensitiveDataRedactor is not None:
            try:
                out = SensitiveDataRedactor.redact_text(out)
            except Exception:
                pass
        out = re.sub(r"(accessToken\s*[=:]\s*)([^\s\"']+)", r"\1[REDACTED_TOKEN]", out, flags=re.IGNORECASE)
        out = re.sub(r"C:\\Users\\[^\\]+", r"C:\\Users\\[USER]", out, flags=re.IGNORECASE)
        return {"redacted": out, "text": out}

    def _rpc_diagnostics_export_bundle(self, params: dict[str, Any]) -> dict[str, Any]:
        instance_name = str(params.get("instance_name", "Global"))
        log_text = str(params.get("log_text", ""))
        settings = params.get("settings") or {}
        redacted_log = self._rpc_diagnostics_redact({"text": log_text})["redacted"]
        diag_dir = self.core.paths.root / "diagnostics"
        diag_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        bundle_path = diag_dir / f"MCW_Diagnostics_{stamp}.zip"

        report_text = f"MCW Core {VERSION} Diagnostic Bundle\nInstance: {instance_name}\nTimestamp: {stamp}\n"
        if DiagnosticsManager is not None:
            try:
                report_text = DiagnosticsManager.build_report(
                    launcher_version=VERSION,
                    settings=settings,
                    activity_log=redacted_log,
                )
            except Exception:
                pass

        with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("diagnostic_report.txt", report_text)
            if redacted_log:
                zf.writestr("console_redacted.log", redacted_log)

        return {
            "path": str(bundle_path),
            "filename": bundle_path.name,
            "instance": instance_name,
            "size_kb": max(1.2, round(bundle_path.stat().st_size / 1024, 1)),
        }

    # --- Operations Lifecycle ---

    def _rpc_operations_pause(self, _params: dict[str, Any]) -> dict[str, Any]:
        self.core.operations.pause()
        self.emit_event("operation.state", {"state": "paused"})
        return {"paused": True}

    def _rpc_operations_resume(self, _params: dict[str, Any]) -> dict[str, Any]:
        self.core.operations.resume()
        self.emit_event("operation.state", {"state": "running"})
        return {"paused": False}

    def _rpc_operations_cancel(self, _params: dict[str, Any]) -> dict[str, Any]:
        self.core.operations.cancel()
        self.emit_event("operation.state", {"state": "cancelled"})
        return {"cancelled": True}

    def _rpc_operations_state(self, _params: dict[str, Any]) -> dict[str, Any]:
        return to_json_compatible(self.core.operations.state)
