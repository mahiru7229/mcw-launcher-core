from __future__ import annotations

from pathlib import Path

from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.lan.lan_agent_manager import LanAgentManager
from src.core.mod.mod_manager import ModManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.modrinth.modrinth_client import ModrinthClient
from src.core.modrinth.modrinth_mod_installer import ModrinthModInstaller
from src.core.modrinth.modrinth_registry import ModrinthRegistry
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.lan.lan_hosting import LanHostingComponent, LanHostingPlan, LanHostingPrepareResult
from src.models.progress.progress_stage import ProgressStage


class LanHostingManager:
    """Prepare per-instance LAN hosting support.

    Authentication policy and connection transport are intentionally separate:

    * ``microsoft_only`` keeps vanilla session verification.
    * ``private_offline`` attaches MCW's bundled host-side Java agent when the
      game launches. The agent forces only the integrated Minecraft server to
      keep authentication disabled; Authlib and Microsoft tokens stay untouched.
    * ``manual`` leaves networking to LAN, VPN, port forwarding, or another relay.
    * ``e4mc`` installs e4mc as the current convenience tunnel provider.

    The agent is bundled and SHA-256 verified. Third-party connection components
    are downloaded as public release builds from Modrinth.
    """

    AUTH_MICROSOFT_ONLY = "microsoft_only"
    AUTH_PRIVATE_OFFLINE = "private_offline"
    AUTH_FRIENDS_LEGACY = "friends"
    CONNECTION_MANUAL = "manual"
    CONNECTION_E4MC = "e4mc"

    ROLE_AUTH_BRIDGE = "auth_bridge"
    ROLE_CONNECTION = "connection"
    MANAGED_BY = "mcw_lan_hosting"

    # Kept only so a previous v0.8.0-beta.1 test install can be disabled
    # automatically when the agent-based design replaces it.
    LEGACY_LAN_WORLD_PNP = LanHostingComponent(
        role=ROLE_AUTH_BRIDGE,
        project_slug="mcwifipnp",
        title="LAN World Plug-n-Play",
    )
    E4MC = LanHostingComponent(
        role=ROLE_CONNECTION,
        project_slug="e4mc",
        title="e4mc",
    )

    SUPPORTED_LOADERS = ModLoaderManager.MODDED_LOADERS

    @staticmethod
    def normalize_auth_mode(value: object) -> str:
        normalized = str(value or "").strip().lower()
        if normalized == LanHostingManager.AUTH_FRIENDS_LEGACY:
            return LanHostingManager.AUTH_PRIVATE_OFFLINE
        return normalized if normalized in {LanHostingManager.AUTH_MICROSOFT_ONLY, LanHostingManager.AUTH_PRIVATE_OFFLINE} else LanHostingManager.AUTH_MICROSOFT_ONLY

    @staticmethod
    def normalize_connection_provider(value: object) -> str:
        normalized = str(value or "").strip().lower()
        return normalized if normalized in {LanHostingManager.CONNECTION_MANUAL, LanHostingManager.CONNECTION_E4MC} else LanHostingManager.CONNECTION_MANUAL

    @staticmethod
    def plan(instance: Instance, auth_mode: object, connection_provider: object) -> LanHostingPlan:
        normalized_auth = LanHostingManager.normalize_auth_mode(auth_mode)
        normalized_connection = LanHostingManager.normalize_connection_provider(connection_provider)
        components: list[LanHostingComponent] = []

        if normalized_connection == LanHostingManager.CONNECTION_E4MC:
            components.append(LanHostingManager.E4MC)

        if components:
            loader_name, _ = ModLoaderManager.normalize(instance.mod_loader)
            if loader_name not in LanHostingManager.SUPPORTED_LOADERS:
                raise RuntimeError("The selected tunnel provider requires a Fabric, Quilt, Forge, or NeoForge instance.")

        return LanHostingPlan(
            auth_mode=normalized_auth,
            connection_provider=normalized_connection,
            components=tuple(components),
        )

    @staticmethod
    def prepare(instance: Instance, auth_mode: object, connection_provider: object, reporter: ProgressReporter | None = None) -> LanHostingPrepareResult:
        if InstanceRunLock.is_active(instance):
            raise RuntimeError("Close Minecraft before changing LAN hosting support.")

        plan = LanHostingManager.plan(instance, auth_mode, connection_provider)
        loader_name, _ = ModLoaderManager.normalize(instance.mod_loader)
        required_components = {(component.role, component.project_slug) for component in plan.components}
        installed_projects: list[str] = []
        reused_projects: list[str] = []
        disabled_projects: list[str] = []
        installed_files: list[str] = []
        warnings: list[str] = []
        includes_agent = plan.auth_mode == LanHostingManager.AUTH_PRIVATE_OFFLINE
        total_steps = len(plan.components) + (1 if includes_agent else 0)
        completed_steps = 0

        if reporter is not None:
            reporter.files(
                ProgressStage.CHECKING_MODS,
                "Preparing LAN hosting support...",
                current=0,
                total=max(1, total_steps),
            )

        if includes_agent:
            agent_result = LanAgentManager.install()
            if agent_result.installed:
                installed_projects.append("MCW LAN Agent")
                installed_files.append(str(agent_result.path))
            else:
                reused_projects.append("MCW LAN Agent")
            completed_steps += 1
            if reporter is not None:
                reporter.files(
                    ProgressStage.CHECKING_MODS,
                    "Prepared MCW LAN Agent.",
                    current=completed_steps,
                    total=max(1, total_steps),
                )

        for component in plan.components:
            selected_version = ModrinthClient.select_version(
                component.project_slug,
                game_version=instance.version_id,
                loader=loader_name,
                version_types=("release",),
            )
            registry = ModrinthRegistry.load(instance)
            entry = registry.get("mods", {}).get(selected_version.project_id)

            if LanHostingManager._entry_matches_installed_file(instance, entry, selected_version.version_id):
                LanHostingManager._enable_entry_if_needed(instance, entry)
                reused_projects.append(component.title)
            else:
                result = ModrinthModInstaller.install(
                    instance,
                    selected_version.version_id,
                    install_dependencies=True,
                    allowed_version_types=("release",),
                    reporter=reporter,
                )
                installed_projects.extend(result.installed_projects)
                installed_files.extend(result.installed_files)
                warnings.extend(result.warnings)

            LanHostingManager._mark_component(instance, selected_version.project_id, component)
            completed_steps += 1
            if reporter is not None:
                reporter.files(
                    ProgressStage.CHECKING_MODS,
                    f"Prepared {component.title}.",
                    current=completed_steps,
                    total=max(1, total_steps),
                )

        disabled_projects.extend(LanHostingManager._disable_unused_managed_components(instance, required_components))

        if reporter is not None:
            reporter.files(
                ProgressStage.FINISHED,
                "LAN hosting support is ready.",
                current=max(1, total_steps),
                total=max(1, total_steps),
            )

        return LanHostingPrepareResult(
            instance_name=instance.name,
            auth_mode=plan.auth_mode,
            connection_provider=plan.connection_provider,
            installed_projects=tuple(dict.fromkeys(installed_projects)),
            reused_projects=tuple(dict.fromkeys(reused_projects)),
            disabled_projects=tuple(dict.fromkeys(disabled_projects)),
            installed_files=tuple(dict.fromkeys(installed_files)),
            warnings=tuple(dict.fromkeys(warnings)),
        )


    @staticmethod
    def disable_legacy_auth_bridges(instance: Instance) -> tuple[str, ...]:
        """Disable auth-bridge mods installed by the superseded beta design."""
        registry = ModrinthRegistry.load(instance)
        disabled_titles: list[str] = []
        for entry in registry.get("mods", {}).values():
            if not isinstance(entry, dict) or entry.get("managedBy") != LanHostingManager.MANAGED_BY:
                continue
            if str(entry.get("lanHostingRole") or "") != LanHostingManager.ROLE_AUTH_BRIDGE:
                continue
            filename = str(entry.get("fileName") or "").strip()
            enabled = ModrinthRegistry.safe_tracked_path(instance, filename)
            if enabled is None or not enabled.is_file():
                continue
            ModManager.set_enabled(instance, [enabled], False)
            disabled_titles.append(str(entry.get("title") or entry.get("lanHostingProjectSlug") or filename))
        return tuple(disabled_titles)

    @staticmethod
    def _entry_matches_installed_file(instance: Instance, entry: object, version_id: str) -> bool:
        if not isinstance(entry, dict) or str(entry.get("versionId") or "") != str(version_id):
            return False
        filename = str(entry.get("fileName") or "").strip()
        if not filename:
            return False
        enabled = ModrinthRegistry.safe_tracked_path(instance, filename)
        disabled = enabled.with_name(enabled.name + ModManager.DISABLED_SUFFIX) if enabled is not None else None
        return bool((enabled is not None and enabled.is_file()) or (disabled is not None and disabled.is_file()))

    @staticmethod
    def _enable_entry_if_needed(instance: Instance, entry: object) -> None:
        if not isinstance(entry, dict):
            return
        filename = str(entry.get("fileName") or "").strip()
        enabled = ModrinthRegistry.safe_tracked_path(instance, filename)
        if enabled is None or enabled.is_file():
            return
        disabled = enabled.with_name(enabled.name + ModManager.DISABLED_SUFFIX)
        if disabled.is_file():
            ModManager.set_enabled(instance, [disabled], True)

    @staticmethod
    def _mark_component(instance: Instance, project_id: str, component: LanHostingComponent) -> None:
        registry = ModrinthRegistry.load(instance)
        entry = registry.setdefault("mods", {}).get(str(project_id))
        if not isinstance(entry, dict):
            return
        entry["managedBy"] = LanHostingManager.MANAGED_BY
        entry["lanHostingRole"] = component.role
        entry["lanHostingProjectSlug"] = component.project_slug
        ModrinthRegistry.save(instance, registry)

    @staticmethod
    def _disable_unused_managed_components(instance: Instance, required_components: set[tuple[str, str]]) -> tuple[str, ...]:
        registry = ModrinthRegistry.load(instance)
        disabled_titles: list[str] = []

        for entry in registry.get("mods", {}).values():
            if not isinstance(entry, dict) or entry.get("managedBy") != LanHostingManager.MANAGED_BY:
                continue
            role = str(entry.get("lanHostingRole") or "")
            project_slug = str(entry.get("lanHostingProjectSlug") or "")
            if (role, project_slug) in required_components:
                continue

            filename = str(entry.get("fileName") or "").strip()
            enabled = ModrinthRegistry.safe_tracked_path(instance, filename)
            if enabled is None or not enabled.is_file():
                continue
            ModManager.set_enabled(instance, [enabled], False)
            disabled_titles.append(str(entry.get("title") or entry.get("lanHostingProjectSlug") or filename))

        return tuple(disabled_titles)
