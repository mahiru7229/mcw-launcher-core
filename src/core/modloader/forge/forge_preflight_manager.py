from __future__ import annotations

from src.core.mod.mod_compatibility_manager import ModCompatibilityManager
from src.core.modloader.forge.forge_version_manager import ForgeVersionManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.modloader.neoforge.neoforge_version_manager import NeoForgeVersionManager
from src.models.instance.instance import Instance
from src.models.minecraft.version import Version
from src.models.mod.mod_issue import ModIssue
from src.models.modloader.forge_preflight_report import ForgePreflightReport


class ForgePreflightManager:
    @staticmethod
    def scan(instance: Instance, version: Version, verify_files: bool = False) -> ForgePreflightReport:
        loader_name, loader_version = ModLoaderManager.normalize(getattr(instance, "mod_loader", (ModLoaderManager.VANILLA, "-1")))
        manager = ForgePreflightManager._manager(loader_name)
        if manager is None:
            return ForgePreflightReport(issues=(), loader=loader_name)

        issues = [
            ModIssue(severity="error", code=f"{loader_name}-installation", message=message)
            for message in manager.validate_installation(version, instance.version_id, loader_version, verify_files=verify_files)
        ]
        issues.extend(ModCompatibilityManager.scan(instance).issues)
        issues.sort(key=lambda item: ({"error": 0, "warning": 1, "info": 2}.get(item.severity, 3), item.message.casefold()))
        return ForgePreflightReport(issues=tuple(issues), loader=loader_name)

    @staticmethod
    def validate_runtime_files(instance: Instance, version: Version) -> tuple[str, ...]:
        loader_name, loader_version = ModLoaderManager.normalize(getattr(instance, "mod_loader", (ModLoaderManager.VANILLA, "-1")))
        manager = ForgePreflightManager._manager(loader_name)
        if manager is None:
            return ()
        return tuple(manager.validate_installation(version, instance.version_id, loader_version, verify_files=True))

    @staticmethod
    def raise_for_errors(report: ForgePreflightReport, block_compatibility_errors: bool = True) -> None:
        blocking_errors = tuple(
            issue for issue in report.errors
            if block_compatibility_errors or issue.code in {"forge-installation", "neoforge-installation"}
        )
        if not blocking_errors:
            return
        details = "\n".join(f"- {issue.message}" for issue in blocking_errors)
        loader_name = str(getattr(report, "loader", "")).strip().casefold()
        if loader_name not in ModLoaderManager.FORGE_FAMILY:
            loader_name = ModLoaderManager.NEOFORGE if any(issue.code == "neoforge-installation" for issue in blocking_errors) else ModLoaderManager.FORGE
        loader = "NeoForge" if loader_name == ModLoaderManager.NEOFORGE else "Forge"
        raise RuntimeError(
            f"{loader} pre-launch check failed:\n"
            f"{len(blocking_errors)} blocking error(s), {getattr(report, 'warning_count', len(getattr(report, 'warnings', ())))} warning(s)\n"
            f"{details}"
        )

    @staticmethod
    def _manager(loader_name: str):
        if loader_name == ModLoaderManager.FORGE:
            return ForgeVersionManager
        if loader_name == ModLoaderManager.NEOFORGE:
            return NeoForgeVersionManager
        return None
