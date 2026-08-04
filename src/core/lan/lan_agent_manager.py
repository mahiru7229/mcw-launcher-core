from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import hashlib
import os
import shutil
import sys

from src.core.fs.paths import Paths
from src.core.lan.lan_agent_target_resolver import LanAgentTargetResolver
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.minecraft.version import Version


@dataclass(frozen=True, slots=True)
class LanAgentInstallResult:
    path: Path
    installed: bool


class LanAgentManager:
    """Install and attach the bundled host-side LAN agent.

    The agent is intentionally narrow: it only changes
    ``MinecraftServer#setUsesAuthentication(boolean)`` inside the Minecraft
    client process. It never replaces Authlib and is attached only when the
    selected instance uses the explicit ``private_offline`` LAN policy.
    """

    AUTH_PRIVATE_OFFLINE = "private_offline"
    AGENT_FILENAME = "mcw-lan-agent.jar"
    AGENT_LOG_FILENAME = "mcw-lan-agent.log"
    AGENT_SHA256 = "c682cd51fbfc9b5e3ed34520eb38a667212c183a68e37ad17694f14f4eace4dc"
    TARGET_CLASS = "net/minecraft/server/MinecraftServer"
    TARGET_METHOD = "setUsesAuthentication"
    TARGET_DESCRIPTOR = "(Z)V"
    RESERVED_ARGUMENT_PREFIXES = (
        "-Dmcw.lan.",
        "-javaagent:",
    )

    @classmethod
    def is_enabled(cls, auth_mode: object) -> bool:
        return str(auth_mode or "").strip().lower() in {cls.AUTH_PRIVATE_OFFLINE, "friends"}

    @classmethod
    def install(cls) -> LanAgentInstallResult:
        source = cls._bundled_agent_path()
        cls._verify_file(source, "Bundled MCW LAN Agent")

        destination = cls.runtime_agent_path()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_file() and cls._sha256(destination) == cls.AGENT_SHA256:
            return LanAgentInstallResult(path=destination, installed=False)

        temporary = destination.with_suffix(destination.suffix + ".part")
        try:
            shutil.copyfile(source, temporary)
            cls._verify_file(temporary, "Copied MCW LAN Agent")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

        return LanAgentInstallResult(path=destination, installed=True)

    @classmethod
    def runtime_arguments(cls, version: Version, auth_mode: object, instance: Instance, reporter: ProgressReporter | None = None) -> list[str]:
        path = cls.log_path(instance)
        if not path.is_file():
            path = cls.prepare_log(instance, auth_mode)
        if not cls.is_enabled(auth_mode):
            cls.append_log_path(path, f"Agent not attached because LAN authentication mode is {auth_mode!r}.")
            return []

        cls.append_log_path(path, "Private LAN mode is enabled; resolving runtime mappings for the MCW LAN Agent.")
        try:
            resolution = LanAgentTargetResolver.resolve(version, instance, reporter)
            cls.append_log_path(
                path,
                f"Mapping profile: Minecraft {resolution.game_version}; loader={resolution.loader}; candidates={len(resolution.targets)}.",
            )
            for warning in resolution.warnings:
                cls.append_log_path(path, f"WARNING: {warning}")
            for target in resolution.targets:
                cls.append_log_path(
                    path,
                    f"Resolved target [{target.namespace}]: {target.class_name.replace('/', '.')}#{target.method_name}{cls.TARGET_DESCRIPTOR}",
                )

            if not resolution.targets:
                cls.append_log_path(
                    path,
                    "Agent was not attached because this Minecraft version is outside the supported 1.17+ range. Minecraft will launch unchanged.",
                )
                return []

            installation = cls.install()
            cls.append_log_path(
                path,
                f"Agent {'installed' if installation.installed else 'reused'}: {installation.path.resolve()}",
            )
            arguments = [
                "-Dmcw.lan.offline=true",
                f"-Dmcw.lan.loader={resolution.loader}",
                f"-Dmcw.lan.targets={resolution.encoded_targets}",
                f"-Dmcw.lan.log={path.resolve().as_posix()}",
                f"-javaagent:{installation.path}",
            ]
            cls.append_log_path(path, "Agent JVM arguments were prepared successfully.")
            return arguments
        except Exception as error:
            cls.append_log_path(path, f"ERROR while preparing the agent: {type(error).__name__}: {error}")
            raise

    @classmethod
    def log_path(cls, instance: Instance) -> Path:
        instance_dir = Path(getattr(instance, "instance_dir", Paths.load_instance_dir(instance.name)))
        directory = instance_dir / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / cls.AGENT_LOG_FILENAME

    @classmethod
    def prepare_log(cls, instance: Instance, auth_mode: object = "unknown") -> Path:
        path = cls.log_path(instance)
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        bundled_path = cls._bundled_agent_path()
        runtime_path = cls.runtime_agent_path()
        path.write_text(
            "[MCW Launcher] MCW LAN Agent launch diagnostics\n"
            f"[MCW Launcher] Started: {timestamp}\n"
            f"[MCW Launcher] Instance: {instance.name}\n"
            f"[MCW Launcher] Instance directory: {Path(getattr(instance, 'instance_dir', Paths.load_instance_dir(instance.name))).resolve()}\n"
            f"[MCW Launcher] LAN authentication mode: {auth_mode}\n"
            f"[MCW Launcher] Agent requested: {cls.is_enabled(auth_mode)}\n"
            f"[MCW Launcher] Launcher mode: {'frozen executable' if getattr(sys, 'frozen', False) else 'source'}\n"
            f"[MCW Launcher] Bundled agent: {bundled_path.resolve()}\n"
            f"[MCW Launcher] Runtime agent: {runtime_path.resolve()}\n"
            f"[MCW Launcher] Named target aliases: {cls.TARGET_CLASS.replace('/', '.')}#setUsesAuthentication{cls.TARGET_DESCRIPTOR}; "
            f"{cls.TARGET_CLASS.replace('/', '.')}#setOnlineMode{cls.TARGET_DESCRIPTOR}\n"
            "[MCW Launcher] Runtime targets: resolved from Mojang, Fabric, Quilt, Forge, and NeoForge mappings during launch\n",
            encoding="utf-8",
        )
        return path

    @classmethod
    def append_log(cls, instance: Instance, message: str) -> None:
        cls.append_log_path(cls.log_path(instance), message)

    @staticmethod
    def append_log_path(path: Path, message: str) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
            with path.open("a", encoding="utf-8") as stream:
                stream.write(f"[MCW Launcher] {timestamp} {message}\n")
        except OSError:
            return

    @classmethod
    def read_log(cls, instance: Instance) -> str:
        path = cls.log_path(instance)
        if not path.is_file():
            return ""
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    @classmethod
    def sanitize_user_jvm_arguments(cls, arguments: list[str]) -> list[str]:
        sanitized: list[str] = []
        for argument in arguments:
            value = str(argument)
            if value.startswith("-Dmcw.lan."):
                continue
            if value.startswith("-javaagent:") and cls.AGENT_FILENAME.casefold() in value.casefold():
                continue
            sanitized.append(value)
        return sanitized

    @classmethod
    def runtime_agent_path(cls) -> Path:
        return Paths.CACHE_ROOT / "runtime" / "agents" / "mcw-lan-agent" / cls.AGENT_FILENAME

    @classmethod
    def _bundled_agent_path(cls) -> Path:
        if getattr(sys, "frozen", False):
            bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
            return bundle_root / "runtime" / cls.AGENT_FILENAME

        project_candidate = Paths.root() / "runtime" / cls.AGENT_FILENAME
        if project_candidate.is_file():
            return project_candidate

        package_candidate = Path(__file__).resolve().parents[3] / "mcw_core" / "resources" / cls.AGENT_FILENAME
        return package_candidate


    @classmethod
    def _verify_file(cls, path: Path, label: str) -> None:
        if not path.is_file():
            raise RuntimeError(f"{label} is missing: {path}")
        digest = cls._sha256(path)
        if digest != cls.AGENT_SHA256:
            raise RuntimeError(f"{label} failed SHA-256 verification and will not be loaded.")

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
