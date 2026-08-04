from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import inspect

from src.core.config.launcher_settings_manager import LauncherSettingsManager
from src.core.config.managed_content_policy import ManagedContentPolicy
from src.core.fs.paths import Paths
from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.instance.settings_manager import SettingsManager
from src.core.lan.lan_agent_manager import LanAgentManager
from src.core.lan.lan_hosting_manager import LanHostingManager
from src.core.java.java_major_policy import JavaMajorPolicy
from src.core.java.java_resolver import JavaResolver
from src.core.java.java_runtime import JavaRuntime
from src.core.minecraft.asset_manager import AssetManager
from src.core.minecraft.context_builder import ContextBuilder
from src.core.minecraft.download_manager import DownloadClientManager
from src.core.minecraft.launcher_manager import LauncherManager
from src.core.minecraft.library_manager import DownloadLibraryManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.modloader.forge.forge_preflight_manager import ForgePreflightManager
from src.core.modloader.forge.compatibility_confirmation import CompatibilityConfirmationRequired
from src.core.curseforge.curseforge_content_manager import CurseForgeContentManager
from src.core.ftb.ftb_content_manager import FTBContentManager
from src.core.modrinth.modrinth_content_manager import ModrinthContentManager
from src.core.minecraft.version_manifest_manager import VersionManifestManager
from src.core.network.download_pause import download_pause_controller
from src.core.progress.progress_reporter import ProgressReporter
from src.core.package.portable_content_manager import PortableContentManager
from src.core.repair.verification_cache import VerificationCache
from src.core.runtime.game_runtime_manager import GameRuntimeManager
from src.core.runtime.process_supervisor import ProcessSupervisor
from src.models.account.account import Account
from src.models.auth.authentication import Authentication
from src.models.instance.instance import Instance
from src.models.progress.progress_callback import ProgressCallback
from src.models.progress.progress_stage import ProgressStage
from src.models.runtime.game_exit_result import GameExitResult


class MinecraftExecutor:
    @staticmethod
    def _load_with_fast_verification(loader: Callable, version: object, reporter: ProgressReporter, verification_cache: VerificationCache):
        try:
            parameters = inspect.signature(loader).parameters.values()
            supports_cache = any(parameter.name == "verification_cache" or parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters)
        except (TypeError, ValueError):
            supports_cache = False
        if supports_cache:
            return loader(version=version, reporter=reporter, verification_cache=verification_cache, fast_verify=True)
        return loader(version=version, reporter=reporter)

    @staticmethod
    def run(instance: Instance, authentication: Authentication, account: Account, debug_mode: bool = False, on_progress: ProgressCallback | None = None, on_exit: Callable[[GameExitResult], None] | None = None, allow_compatibility_issues_once: bool = False) -> dict:
        run_lock = InstanceRunLock.acquire(instance)
        process_started = False
        process = None
        process_session = None
        lan_log_path = None
        verification_cache: VerificationCache | None = None

        try:
            process_session = ProcessSupervisor.begin(instance)
            reporter = ProgressReporter(on_progress)
            download_pause_controller.raise_if_requested()
            reporter.status(stage=ProgressStage.PREPARING, message="Preparing Minecraft...")

            settings = SettingsManager.load(instance)
            lan_auth_mode = getattr(settings, "lan_auth_mode", "microsoft_only")
            lan_log_path = LanAgentManager.prepare_log(instance, lan_auth_mode)
            LanAgentManager.append_log_path(lan_log_path, "Launcher settings were loaded successfully.")
            if LanAgentManager.is_enabled(lan_auth_mode):
                LanHostingManager.disable_legacy_auth_bridges(instance)
                LanAgentManager.append_log_path(lan_log_path, "Legacy LAN authentication bridges were checked and disabled if present.")
            download_pause_controller.raise_if_requested()
            launcher_settings = LauncherSettingsManager().load()
            block_modrinth_failure = ManagedContentPolicy.blocks_launch(settings, launcher_settings, "modrinth")
            block_curseforge_failure = ManagedContentPolicy.blocks_launch(settings, launcher_settings, "curseforge")
            forge_preflight_policy = ManagedContentPolicy.resolve(settings, launcher_settings, "forge_preflight")
            launch_lock_token = getattr(run_lock, "token", None)
            PortableContentManager.ensure(instance)
            PortableContentManager.prefetch_referenced(instance, reporter)
            modrinth_warnings = ModrinthContentManager.ensure(instance, reporter, block_launch_on_failure=block_modrinth_failure, launch_lock_token=launch_lock_token)
            curseforge_warnings = CurseForgeContentManager.ensure(instance, reporter, block_launch_on_failure=block_curseforge_failure, launch_lock_token=launch_lock_token)
            ftb_warnings = FTBContentManager.ensure(instance, reporter, launch_lock_token=launch_lock_token)
            PortableContentManager.finalize_disabled(instance)

            download_pause_controller.raise_if_requested()
            VersionManifestManager.get()
            download_pause_controller.raise_if_requested()
            reporter.status(stage=ProgressStage.LOADING_VERSION, message=f"Loading Minecraft {instance.version_id}...")
            version = ModLoaderManager.load(instance, reporter)
            verification_cache = VerificationCache(Paths.instance_repair_cache(instance))
            download_pause_controller.raise_if_requested()

            forge_preflight = ForgePreflightManager.scan(instance, version, verify_files=False)
            # Loader/runtime installation failures are never bypassable.
            ForgePreflightManager.raise_for_errors(forge_preflight, False)
            compatibility_errors = tuple(
                issue for issue in getattr(forge_preflight, "errors", ())
                if issue.code not in {"forge-installation", "neoforge-installation"}
            )
            if compatibility_errors:
                if forge_preflight_policy == ManagedContentPolicy.BLOCK:
                    ForgePreflightManager.raise_for_errors(forge_preflight, True)
                if forge_preflight_policy == ManagedContentPolicy.ASK and not allow_compatibility_issues_once:
                    raise CompatibilityConfirmationRequired(instance.name, forge_preflight)

            reporter.status(stage=ProgressStage.DOWNLOADING_CLIENT, message="Checking Minecraft client...")
            MinecraftExecutor._load_with_fast_verification(DownloadClientManager.load, version, reporter, verification_cache)
            download_pause_controller.raise_if_requested()

            reporter.status(stage=ProgressStage.DOWNLOADING_LIBRARIES, message="Checking Minecraft libraries...")
            MinecraftExecutor._load_with_fast_verification(DownloadLibraryManager.load, version, reporter, verification_cache)
            download_pause_controller.raise_if_requested()

            forge_runtime_issues = ForgePreflightManager.validate_runtime_files(instance, version)
            if forge_runtime_issues:
                details = "\n".join(f"- {issue}" for issue in forge_runtime_issues)
                raise RuntimeError(f"Forge runtime verification failed:\n{details}")

            reporter.status(stage=ProgressStage.DOWNLOADING_ASSETS, message="Checking Minecraft assets...")
            MinecraftExecutor._load_with_fast_verification(AssetManager.load, version, reporter, verification_cache)
            download_pause_controller.raise_if_requested()

            reporter.status(stage=ProgressStage.BUILDING_CONTEXT, message="Building launch context...")
            context = ContextBuilder.build(instance, version, authentication)
            download_pause_controller.raise_if_requested()

            reporter.status(stage=ProgressStage.BUILDING_COMMAND, message="Building launch command...")
            lan_runtime_arguments = LanAgentManager.runtime_arguments(version, lan_auth_mode, instance, reporter)
            if lan_runtime_arguments:
                command = LauncherManager.build(version, context, settings, account, runtime_jvm_arguments=lan_runtime_arguments)
            else:
                command = LauncherManager.build(version, context, settings, account)
            LanAgentManager.append_log_path(
                lan_log_path,
                f"Launch command built; agent attached: {bool(lan_runtime_arguments)}; main class: {getattr(version, 'main_class', 'unknown')}",
            )
            download_pause_controller.raise_if_requested()

            reporter.status(stage=ProgressStage.SELECTING_JAVA, message="Selecting Java runtime...")
            required_java_major = int(version.java_version.get("majorVersion") or 8)
            java_major = JavaMajorPolicy.resolve(required_java_major)
            preferred_java = str(getattr(settings, "java_path", "") or "").strip()
            java = JavaResolver.resolve(required_java_major, reporter, preferred_java) if preferred_java else JavaResolver.resolve(required_java_major, reporter)
            LanAgentManager.append_log_path(lan_log_path, f"Java selected: {java} (required {required_java_major}; compatibility target {java_major}).")
            download_pause_controller.raise_if_requested()

            reporter.status(stage=ProgressStage.LAUNCHING, message=f"Launching Minecraft {version.id}...")
            crash_report_snapshot = GameRuntimeManager.crash_report_snapshot(instance)
            started_at = datetime.now(timezone.utc)
            process = JavaRuntime.run(java, command, instance)
            process_started = True
            LanAgentManager.append_log_path(lan_log_path, f"Minecraft process started; pid={getattr(process, 'pid', 'unknown')}.")
            run_lock.track_process(process)
            ProcessSupervisor.attach(process_session.session_id, process)
            GameRuntimeManager.record_start(instance, started_at, process_session.session_id)
            watched = GameRuntimeManager.watch(process, instance, version.id, started_at, on_exit, process_session.session_id, crash_report_snapshot)
            if watched is False and callable(getattr(process, "poll", None)):
                raise RuntimeError("Minecraft process could not be registered with the runtime manager.")
            reporter.status(stage=ProgressStage.FINISHED, message=f"Minecraft {version.id} launched successfully.")

            if debug_mode:
                native_dir = Paths.natives(version)
                print("Native directory:", native_dir)
                print("Exists:", native_dir.exists())
                if native_dir.exists():
                    print("Native files:", list(native_dir.rglob("*")))

            result = {
                "javaPath": java,
                "minecraftJavaMajorVersion": java_major,
                "minecraftVersion": version.id,
            }
            bypassed_compatibility = tuple(
                issue.message for issue in getattr(forge_preflight, "errors", ())
                if issue.code not in {"forge-installation", "neoforge-installation"}
                and (forge_preflight_policy == ManagedContentPolicy.ALLOW or allow_compatibility_issues_once)
            )
            forge_warnings = tuple(issue.message for issue in forge_preflight.warnings) + bypassed_compatibility
            warnings = tuple(modrinth_warnings) + tuple(curseforge_warnings) + tuple(ftb_warnings) + forge_warnings
            if warnings:
                result["warnings"] = warnings
            return result
        except Exception as error:
            if lan_log_path is not None:
                LanAgentManager.append_log_path(
                    lan_log_path,
                    f"Launcher aborted: {type(error).__name__}: {error}",
                )
            if process_started and process is not None:
                try:
                    ProcessSupervisor.stop_process(process, 1.5)
                except Exception:
                    pass
                if process_session is not None:
                    ProcessSupervisor.abort(process_session.session_id, f"{type(error).__name__}: {error}")
                run_lock.release()
            elif not process_started:
                if process_session is not None:
                    ProcessSupervisor.abort(process_session.session_id, f"{type(error).__name__}: {error}")
                run_lock.release()
            raise
        finally:
            if verification_cache is not None:
                try:
                    verification_cache.save()
                except OSError as error:
                    if lan_log_path is not None:
                        LanAgentManager.append_log_path(lan_log_path, f"Verification cache could not be saved: {error}")
