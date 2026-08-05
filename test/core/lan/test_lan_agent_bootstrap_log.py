from pathlib import Path
from types import SimpleNamespace

from src.core.curseforge.curseforge_content_manager import CurseForgeContentManager
from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.instance.settings_manager import SettingsManager
from src.core.java.java_resolver import JavaResolver
from src.core.java.java_runtime import JavaRuntime
from src.core.lan.lan_agent_manager import LanAgentManager
from src.core.lan.lan_hosting_manager import LanHostingManager
from src.core.minecraft.asset_manager import AssetManager
from src.core.minecraft.context_builder import ContextBuilder
from src.core.minecraft.download_manager import DownloadClientManager
from src.core.minecraft.launcher_manager import LauncherManager
from src.core.minecraft.library_manager import DownloadLibraryManager
from src.core.minecraft.minecraft_executor import MinecraftExecutor
from src.core.minecraft.version_manifest_manager import VersionManifestManager
from src.core.modloader.forge.forge_preflight_manager import ForgePreflightManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.modrinth.modrinth_content_manager import ModrinthContentManager
from src.core.runtime.game_runtime_manager import GameRuntimeManager
from src.core.runtime.process_supervisor import ProcessSupervisor


class FakeRunLock:
    def track_process(self, process) -> None:
        return None

    def release(self) -> None:
        return None


def test_launcher_creates_agent_log_before_java_process_starts(monkeypatch, tmp_path: Path) -> None:
    instance = SimpleNamespace(name="Pack", version_id="26.2", instance_dir=tmp_path / "Pack")
    settings = SimpleNamespace(lan_auth_mode="private_offline", block_launch_on_modrinth_failure=True)
    version = SimpleNamespace(id="26.2", java_version={"majorVersion": 21}, main_class="net.minecraft.client.main.Main")
    preflight = SimpleNamespace(warnings=())
    process = SimpleNamespace(pid=1234)

    monkeypatch.setattr(InstanceRunLock, "acquire", lambda _instance: FakeRunLock())
    monkeypatch.setattr(ProcessSupervisor, "begin", lambda _instance: SimpleNamespace(session_id="test-session"))
    monkeypatch.setattr(ProcessSupervisor, "attach", lambda _session_id, _process: None)
    monkeypatch.setattr(SettingsManager, "load", lambda _instance: settings)
    monkeypatch.setattr(LanHostingManager, "disable_legacy_auth_bridges", lambda _instance: ())
    monkeypatch.setattr(ModrinthContentManager, "ensure", lambda *args, **kwargs: ())
    monkeypatch.setattr(CurseForgeContentManager, "ensure", lambda *args, **kwargs: ())
    monkeypatch.setattr(VersionManifestManager, "get", lambda: [])
    monkeypatch.setattr(ModLoaderManager, "load", lambda *args, **kwargs: version)
    monkeypatch.setattr(ForgePreflightManager, "scan", lambda *args, **kwargs: preflight)
    monkeypatch.setattr(ForgePreflightManager, "raise_for_errors", lambda _result, *_args, **_kwargs: None)
    monkeypatch.setattr(ForgePreflightManager, "validate_runtime_files", lambda *args, **kwargs: ())
    monkeypatch.setattr(DownloadClientManager, "load", lambda **kwargs: Path("client.jar"))
    monkeypatch.setattr(DownloadLibraryManager, "load", lambda **kwargs: [])
    monkeypatch.setattr(AssetManager, "load", lambda **kwargs: Path("assets"))
    monkeypatch.setattr(ContextBuilder, "build", lambda *args: {})
    monkeypatch.setattr(LanAgentManager, "runtime_arguments", classmethod(lambda cls, *args: ["-javaagent:test.jar"]))
    monkeypatch.setattr(LauncherManager, "build", lambda *args, **kwargs: ["-javaagent:test.jar", version.main_class])
    monkeypatch.setattr(JavaResolver, "resolve", lambda *args, **kwargs: Path("javaw.exe"))
    monkeypatch.setattr(JavaRuntime, "run", lambda *args: process)
    monkeypatch.setattr(GameRuntimeManager, "watch", lambda *args: None)

    MinecraftExecutor.run(instance, object(), object())

    log = (instance.instance_dir / "logs" / LanAgentManager.AGENT_LOG_FILENAME).read_text(encoding="utf-8")
    assert "LAN authentication mode: private_offline" in log
    assert "Launcher settings were loaded successfully" in log
    assert "Launch command built; agent attached: True" in log
    assert "Minecraft process started; pid=1234" in log
