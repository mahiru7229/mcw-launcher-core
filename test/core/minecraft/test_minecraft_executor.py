from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.config.launcher_settings_manager import LauncherSettingsManager
from src.core.fs.paths import Paths
from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.instance.settings_manager import SettingsManager
from src.core.lan.lan_agent_manager import LanAgentManager
from src.core.lan.lan_hosting_manager import LanHostingManager
from src.core.java.java_resolver import JavaResolution, JavaResolver
from src.core.java.java_runtime import JavaRuntime, JavaStartupProbe
from src.core.java.java_selector import JavaSelector
from src.core.minecraft.asset_manager import AssetManager
from src.core.minecraft.context_builder import ContextBuilder
from src.core.minecraft.download_manager import DownloadClientManager
from src.core.minecraft.launcher_manager import LauncherManager
from src.core.minecraft.library_manager import DownloadLibraryManager
from src.core.minecraft.minecraft_executor import MinecraftExecutor
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.modloader.forge.forge_preflight_manager import ForgePreflightManager
from src.core.modloader.forge.compatibility_confirmation import CompatibilityConfirmationRequired
from src.core.curseforge.curseforge_content_manager import CurseForgeContentManager
from src.core.modrinth.modrinth_content_manager import ModrinthContentManager
from src.core.mod.modpack_dependency_resolver import ModpackDependencyResolver
from src.core.network.artifact_download_service import ArtifactDownloadError
from src.models.mod.dependency_resolution import DependencyResolutionResult
from src.core.runtime.process_supervisor import ProcessSupervisor
from src.core.minecraft.version_manager import VersionManager
from src.core.minecraft.version_manifest_manager import (
    VersionManifestManager,
)
from src.models.progress.progress_stage import ProgressStage
from src.models.network.artifact import ArtifactDownloadFailure, DownloadFailureReason
from src.core.progress.progress_reporter import ProgressReporter


class FakeRunLock:
    def __init__(self) -> None:
        self.token = "test-launch-lock-token"
        self.tracked_process = None
        self.released = False

    def track_process(self, process) -> bool:
        self.tracked_process = process
        return True

    def release(self) -> None:
        self.released = True


@pytest.fixture(autouse=True)
def patch_instance_run_lock(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(InstanceRunLock, "acquire", lambda instance: FakeRunLock())
    monkeypatch.setattr(ProcessSupervisor, "begin", lambda instance: SimpleNamespace(session_id="test-session"))
    monkeypatch.setattr(ProcessSupervisor, "attach", lambda session_id, process: None)
    monkeypatch.setattr(ProcessSupervisor, "abort", lambda session_id, detail="": None)
    monkeypatch.setattr(ProcessSupervisor, "stop_process", lambda process, graceful_timeout=2.5: True)
    monkeypatch.setattr(
        LauncherSettingsManager,
        "load",
        lambda self: {
            "managed_content": {
                "modrinth_failure_policy": "block",
                "curseforge_failure_policy": "block",
            }
        },
    )


def make_instance(
    *,
    version_id: str = "1.20.1",
):
    return SimpleNamespace(
        name="Test Instance",
        version_id=version_id,
    )


def make_version(
    *,
    version_id: str = "1.20.1",
    java_version: dict | None = None,
):
    return SimpleNamespace(
        id=version_id,
        java_version=(
            {"majorVersion": 17}
            if java_version is None
            else java_version
        ),
    )


def patch_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    version=None,
    java_path: Path | None = None,
):
    version = version or make_version()
    java_path = java_path or Path(
        "C:/Java/bin/javaw.exe"
    )

    settings = object()
    context = {
        "classpath": "libraries;client.jar",
    }
    command = [
        "-Xmx2G",
        "-cp",
        "libraries;client.jar",
        "net.minecraft.client.main.Main",
    ]

    monkeypatch.setattr(
        VersionManifestManager,
        "get",
        lambda: [],
    )
    monkeypatch.setattr(
        VersionManager,
        "load",
        lambda version_id: version,
    )
    monkeypatch.setattr(
        DownloadClientManager,
        "load",
        lambda **kwargs: Path("client.jar"),
    )
    monkeypatch.setattr(
        DownloadLibraryManager,
        "load",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        AssetManager,
        "load",
        lambda **kwargs: Path("assets"),
    )
    monkeypatch.setattr(
        SettingsManager,
        "load",
        lambda instance: settings,
    )
    monkeypatch.setattr(
        ContextBuilder,
        "build",
        lambda instance, version, authentication: context,
    )
    monkeypatch.setattr(
        LauncherManager,
        "build",
        lambda version, context, settings, account: command,
    )
    monkeypatch.setattr(
        JavaSelector,
        "select_java",
        lambda major: java_path,
    )
    monkeypatch.setattr(
        JavaRuntime,
        "run",
        lambda java, command, instance: object(),
    )

    return {
        "version": version,
        "java_path": java_path,
        "settings": settings,
        "context": context,
        "command": command,
    }



def test_load_client_forces_full_hash_for_legacy_forge(monkeypatch: pytest.MonkeyPatch) -> None:
    version = SimpleNamespace(
        main_class="net.minecraft.launchwrapper.Launch",
        raw_json={"forge": {"gameVersion": "1.6.4", "loaderVersion": "9.11.1.1345"}},
    )
    reporter = object()
    verification_cache = object()
    received = {}

    def fake_load(**kwargs):
        received.update(kwargs)
        return Path("1.6.4.jar")

    monkeypatch.setattr(DownloadClientManager, "load", fake_load)

    result = MinecraftExecutor._load_client(version, reporter, verification_cache)

    assert result == Path("1.6.4.jar")
    assert received == {
        "version": version,
        "reporter": reporter,
        "verification_cache": verification_cache,
        "fast_verify": False,
    }


def test_load_client_keeps_fast_verification_for_non_legacy_profiles(monkeypatch: pytest.MonkeyPatch) -> None:
    version = SimpleNamespace(main_class="net.minecraft.client.main.Main", raw_json={})
    reporter = object()
    verification_cache = object()
    received = {}

    def fake_load(**kwargs):
        received.update(kwargs)
        return Path("client.jar")

    monkeypatch.setattr(DownloadClientManager, "load", fake_load)

    result = MinecraftExecutor._load_client(version, reporter, verification_cache)

    assert result == Path("client.jar")
    assert received == {
        "version": version,
        "reporter": reporter,
        "verification_cache": verification_cache,
        "fast_verify": True,
    }

def test_run_returns_launch_information(
    monkeypatch: pytest.MonkeyPatch,
):
    pipeline = patch_pipeline(monkeypatch)

    result = MinecraftExecutor.run(
        instance=make_instance(),
        authentication=object(),
        account=object(),
    )

    assert result == {
        "javaPath": pipeline["java_path"],
        "minecraftJavaMajorVersion": 17,
        "minecraftVersion": "1.20.1",
    }


def test_run_calls_pipeline_in_expected_order(
    monkeypatch: pytest.MonkeyPatch,
):
    instance = make_instance()
    authentication = object()
    account = object()
    version = make_version()
    settings = object()
    context = object()
    command = ["command"]
    java_path = Path("javaw.exe")
    calls = []

    monkeypatch.setattr(
        VersionManifestManager,
        "get",
        lambda: calls.append(("manifest",)),
    )

    def load_version(version_id):
        calls.append(("version", version_id))
        return version

    monkeypatch.setattr(
        VersionManager,
        "load",
        load_version,
    )

    def load_client(**kwargs):
        calls.append(
            (
                "client",
                kwargs["version"],
                kwargs["reporter"],
            )
        )

    monkeypatch.setattr(
        DownloadClientManager,
        "load",
        load_client,
    )

    def load_libraries(**kwargs):
        calls.append(
            (
                "libraries",
                kwargs["version"],
                kwargs["reporter"],
            )
        )

    monkeypatch.setattr(
        DownloadLibraryManager,
        "load",
        load_libraries,
    )

    def load_assets(**kwargs):
        calls.append(
            (
                "assets",
                kwargs["version"],
                kwargs["reporter"],
            )
        )

    monkeypatch.setattr(
        AssetManager,
        "load",
        load_assets,
    )

    def load_settings(received_instance):
        calls.append(
            ("settings", received_instance)
        )
        return settings

    monkeypatch.setattr(
        SettingsManager,
        "load",
        load_settings,
    )

    def build_context(
        received_instance,
        received_version,
        received_authentication,
    ):
        calls.append(
            (
                "context",
                received_instance,
                received_version,
                received_authentication,
            )
        )
        return context

    monkeypatch.setattr(
        ContextBuilder,
        "build",
        build_context,
    )

    def build_command(
        received_version,
        received_context,
        received_settings,
        received_account,
    ):
        calls.append(
            (
                "command",
                received_version,
                received_context,
                received_settings,
                received_account,
            )
        )
        return command

    monkeypatch.setattr(
        LauncherManager,
        "build",
        build_command,
    )

    def select_java(major):
        calls.append(("java", major))
        return java_path

    monkeypatch.setattr(
        JavaSelector,
        "select_java",
        select_java,
    )

    def run_java(
        received_java,
        received_command,
        received_instance,
    ):
        calls.append(
            (
                "launch",
                received_java,
                received_command,
                received_instance,
            )
        )

    monkeypatch.setattr(
        JavaRuntime,
        "run",
        run_java,
    )

    MinecraftExecutor.run(
        instance=instance,
        authentication=authentication,
        account=account,
    )

    assert [
        call[0]
        for call in calls
    ] == [
        "settings",
        "manifest",
        "version",
        "client",
        "libraries",
        "assets",
        "context",
        "command",
        "java",
        "launch",
    ]

    assert next(call for call in calls if call[0] == "version") == (
        "version",
        "1.20.1",
    )
    assert calls[-1] == (
        "launch",
        java_path,
        command,
        instance,
    )


def test_run_passes_same_reporter_to_download_managers(
    monkeypatch: pytest.MonkeyPatch,
):
    version = make_version()
    reporters = []

    monkeypatch.setattr(
        VersionManifestManager,
        "get",
        lambda: [],
    )
    monkeypatch.setattr(
        VersionManager,
        "load",
        lambda version_id: version,
    )

    def capture_reporter(**kwargs):
        reporters.append(kwargs["reporter"])

    monkeypatch.setattr(
        DownloadClientManager,
        "load",
        capture_reporter,
    )
    monkeypatch.setattr(
        DownloadLibraryManager,
        "load",
        capture_reporter,
    )
    monkeypatch.setattr(
        AssetManager,
        "load",
        capture_reporter,
    )
    monkeypatch.setattr(
        SettingsManager,
        "load",
        lambda instance: object(),
    )
    monkeypatch.setattr(
        ContextBuilder,
        "build",
        lambda *args: {},
    )
    monkeypatch.setattr(
        LauncherManager,
        "build",
        lambda *args: [],
    )
    monkeypatch.setattr(
        JavaSelector,
        "select_java",
        lambda major: Path("javaw.exe"),
    )
    monkeypatch.setattr(
        JavaRuntime,
        "run",
        lambda *args: None,
    )

    MinecraftExecutor.run(
        instance=make_instance(),
        authentication=object(),
        account=object(),
    )

    assert len(reporters) == 3
    assert reporters[0] is reporters[1]
    assert reporters[1] is reporters[2]


def test_run_emits_progress_stages_in_expected_order(
    monkeypatch: pytest.MonkeyPatch,
):
    patch_pipeline(monkeypatch)
    events = []

    MinecraftExecutor.run(
        instance=make_instance(),
        authentication=object(),
        account=object(),
        on_progress=events.append,
    )

    assert [
        event.stage
        for event in events
    ] == [
        ProgressStage.PREPARING,
        ProgressStage.LOADING_VERSION,
        ProgressStage.DOWNLOADING_CLIENT,
        ProgressStage.DOWNLOADING_LIBRARIES,
        ProgressStage.DOWNLOADING_ASSETS,
        ProgressStage.BUILDING_CONTEXT,
        ProgressStage.BUILDING_COMMAND,
        ProgressStage.SELECTING_JAVA,
        ProgressStage.LAUNCHING,
        ProgressStage.FINISHED,
    ]


def test_run_emits_expected_progress_messages(
    monkeypatch: pytest.MonkeyPatch,
):
    patch_pipeline(monkeypatch)
    events = []

    MinecraftExecutor.run(
        instance=make_instance(
            version_id="1.20.1"
        ),
        authentication=object(),
        account=object(),
        on_progress=events.append,
    )

    assert [
        event.message
        for event in events
    ] == [
        "Preparing Minecraft...",
        "Loading Minecraft 1.20.1...",
        "Checking Minecraft client...",
        "Checking Minecraft libraries...",
        "Checking Minecraft assets...",
        "Building launch context...",
        "Building launch command...",
        "Selecting Java runtime...",
        "Launching Minecraft 1.20.1...",
        (
            "Minecraft 1.20.1 "
            "launched successfully."
        ),
    ]


def test_run_uses_required_java_major_version(
    monkeypatch: pytest.MonkeyPatch,
):
    version = make_version(
        java_version={
            "majorVersion": 21
        }
    )
    selected = []

    patch_pipeline(
        monkeypatch,
        version=version,
    )
    monkeypatch.setattr(
        JavaSelector,
        "select_java",
        lambda major: (
            selected.append(major)
            or Path("java21/javaw.exe")
        ),
    )

    result = MinecraftExecutor.run(
        instance=make_instance(),
        authentication=object(),
        account=object(),
    )

    assert selected == [21]
    assert (
        result["minecraftJavaMajorVersion"]
        == 21
    )


def test_run_defaults_to_java_8_when_major_version_is_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    version = make_version(
        java_version={}
    )
    selected = []

    patch_pipeline(
        monkeypatch,
        version=version,
    )
    monkeypatch.setattr(
        JavaSelector,
        "select_java",
        lambda major: (
            selected.append(major)
            or Path("java8/javaw.exe")
        ),
    )

    result = MinecraftExecutor.run(
        instance=make_instance(),
        authentication=object(),
        account=object(),
    )

    assert selected == [8]
    assert (
        result["minecraftJavaMajorVersion"]
        == 8
    )


def test_run_passes_authentication_to_context_builder(
    monkeypatch: pytest.MonkeyPatch,
):
    instance = make_instance()
    authentication = object()
    account = object()
    version = make_version()
    received = {}

    patch_pipeline(
        monkeypatch,
        version=version,
    )

    def fake_build(
        received_instance,
        received_version,
        received_authentication,
    ):
        received.update(
            {
                "instance": received_instance,
                "version": received_version,
                "authentication": (
                    received_authentication
                ),
            }
        )
        return {}

    monkeypatch.setattr(
        ContextBuilder,
        "build",
        fake_build,
    )

    MinecraftExecutor.run(
        instance=instance,
        authentication=authentication,
        account=account,
    )

    assert received == {
        "instance": instance,
        "version": version,
        "authentication": authentication,
    }


def test_run_passes_account_to_launcher_manager(
    monkeypatch: pytest.MonkeyPatch,
):
    account = object()
    received = {}

    pipeline = patch_pipeline(monkeypatch)

    def fake_build(
        version,
        context,
        settings,
        received_account,
    ):
        received["account"] = received_account
        return pipeline["command"]

    monkeypatch.setattr(
        LauncherManager,
        "build",
        fake_build,
    )

    MinecraftExecutor.run(
        instance=make_instance(),
        authentication=object(),
        account=account,
    )

    assert received["account"] is account


def test_run_passes_selected_java_command_and_instance_to_runtime(
    monkeypatch: pytest.MonkeyPatch,
):
    instance = make_instance()
    java_path = Path(
        "C:/Java/bin/javaw.exe"
    )
    pipeline = patch_pipeline(
        monkeypatch,
        java_path=java_path,
    )
    received = {}

    def fake_run(
        java,
        command,
        received_instance,
    ):
        received.update(
            {
                "java": java,
                "command": command,
                "instance": received_instance,
            }
        )

    monkeypatch.setattr(
        JavaRuntime,
        "run",
        fake_run,
    )

    MinecraftExecutor.run(
        instance=instance,
        authentication=object(),
        account=object(),
    )

    assert received == {
        "java": java_path,
        "command": pipeline["command"],
        "instance": instance,
    }


def test_run_does_not_print_debug_information_by_default(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
):
    patch_pipeline(monkeypatch)

    MinecraftExecutor.run(
        instance=make_instance(),
        authentication=object(),
        account=object(),
    )

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == ""


def test_run_prints_native_debug_information_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
):
    version = make_version()
    patch_pipeline(
        monkeypatch,
        version=version,
    )

    native_dir = tmp_path / "natives"
    native_dir.mkdir()
    native_file = native_dir / "lwjgl.dll"
    native_file.write_bytes(b"native")

    monkeypatch.setattr(
        Paths,
        "natives",
        lambda received_version: native_dir,
    )

    MinecraftExecutor.run(
        instance=make_instance(),
        authentication=object(),
        account=object(),
        debug_mode=True,
    )

    output = capsys.readouterr().out

    assert (
        f"Native directory: {native_dir}"
        in output
    )
    assert "Exists: True" in output
    assert "lwjgl.dll" in output


def test_run_debug_mode_handles_missing_native_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
):
    patch_pipeline(monkeypatch)

    native_dir = (
        tmp_path
        / "missing-natives"
    )

    monkeypatch.setattr(
        Paths,
        "natives",
        lambda version: native_dir,
    )

    MinecraftExecutor.run(
        instance=make_instance(),
        authentication=object(),
        account=object(),
        debug_mode=True,
    )

    output = capsys.readouterr().out

    assert (
        f"Native directory: {native_dir}"
        in output
    )
    assert "Exists: False" in output
    assert "Native files:" not in output


def test_run_propagates_pipeline_exception_and_does_not_emit_finished(
    monkeypatch: pytest.MonkeyPatch,
):
    patch_pipeline(monkeypatch)
    events = []
    expected_error = RuntimeError(
        "library download failed"
    )

    def fail_libraries(**kwargs):
        raise expected_error

    monkeypatch.setattr(
        DownloadLibraryManager,
        "load",
        fail_libraries,
    )

    with pytest.raises(RuntimeError) as error:
        MinecraftExecutor.run(
            instance=make_instance(),
            authentication=object(),
            account=object(),
            on_progress=events.append,
        )

    assert error.value is expected_error
    assert (
        ProgressStage.FINISHED
        not in [
            event.stage
            for event in events
        ]
    )
    assert [
        event.stage
        for event in events
    ][-1] is (
        ProgressStage.DOWNLOADING_LIBRARIES
    )

def test_run_tracks_java_process_with_instance_lock(monkeypatch: pytest.MonkeyPatch):
    instance = make_instance()
    process = object()
    run_lock = FakeRunLock()

    patch_pipeline(monkeypatch)
    monkeypatch.setattr(InstanceRunLock, "acquire", lambda received_instance: run_lock)
    monkeypatch.setattr(JavaRuntime, "run", lambda java, command, received_instance: process)

    MinecraftExecutor.run(instance=instance, authentication=object(), account=object())

    assert run_lock.tracked_process is process
    assert run_lock.released is False


def test_disk_full_during_managed_content_releases_preparing_lock_without_manual_pause(monkeypatch: pytest.MonkeyPatch):
    run_lock = FakeRunLock()
    failure = ArtifactDownloadFailure(
        provider="curseforge",
        filename="example.jar",
        reason=DownloadFailureReason.DISK_SPACE_ERROR,
        detail="No space left on device",
        retryable=False,
    )
    expected = ArtifactDownloadError(failure)
    manual_requests = []

    patch_pipeline(monkeypatch)
    monkeypatch.setattr(InstanceRunLock, "acquire", lambda instance: run_lock)
    monkeypatch.setattr(ModrinthContentManager, "ensure", lambda *args, **kwargs: ())
    monkeypatch.setattr(CurseForgeContentManager, "ensure", lambda *args, **kwargs: (_ for _ in ()).throw(expected))

    with pytest.raises(ArtifactDownloadError) as captured:
        MinecraftExecutor.run(
            instance=make_instance(),
            authentication=object(),
            account=object(),
            on_manual_content_required=manual_requests.append,
        )

    assert captured.value is expected
    assert manual_requests == []
    assert run_lock.released is True
    assert run_lock.tracked_process is None


def test_run_releases_instance_lock_when_preparation_fails(monkeypatch: pytest.MonkeyPatch):
    run_lock = FakeRunLock()
    expected_error = RuntimeError("version manifest failed")

    patch_pipeline(monkeypatch)
    monkeypatch.setattr(InstanceRunLock, "acquire", lambda instance: run_lock)

    def fail_manifest():
        raise expected_error

    monkeypatch.setattr(VersionManifestManager, "get", fail_manifest)

    with pytest.raises(RuntimeError) as error:
        MinecraftExecutor.run(instance=make_instance(), authentication=object(), account=object())

    assert error.value is expected_error
    assert run_lock.released is True
    assert run_lock.tracked_process is None


def test_fabric_instance_uses_resolved_knot_client(monkeypatch: pytest.MonkeyPatch):
    instance = SimpleNamespace(name="Fabric Test", version_id="1.21.1", mod_loader=("fabric", "0.19.3"))
    fabric_version = SimpleNamespace(
        id="fabric-loader-0.19.3-1.21.1",
        java_version={"majorVersion": 21},
        main_class="net.fabricmc.loader.impl.launch.knot.KnotClient",
    )
    launched = {}

    monkeypatch.setattr(VersionManifestManager, "get", lambda: [])
    monkeypatch.setattr(ModLoaderManager, "load", lambda received_instance, reporter=None: fabric_version)
    monkeypatch.setattr(DownloadClientManager, "load", lambda **kwargs: Path("client.jar"))
    monkeypatch.setattr(DownloadLibraryManager, "load", lambda **kwargs: [])
    monkeypatch.setattr(AssetManager, "load", lambda **kwargs: Path("assets"))
    monkeypatch.setattr(SettingsManager, "load", lambda received_instance: object())
    monkeypatch.setattr(ContextBuilder, "build", lambda *args: {})
    monkeypatch.setattr(LauncherManager, "build", lambda version, *args: [version.main_class])
    monkeypatch.setattr(JavaSelector, "select_java", lambda major: Path("javaw.exe"))
    monkeypatch.setattr(JavaRuntime, "run", lambda java, command, received_instance: launched.update(command=command) or object())

    result = MinecraftExecutor.run(instance=instance, authentication=object(), account=object())

    assert launched["command"] == ["net.fabricmc.loader.impl.launch.knot.KnotClient"]
    assert result["minecraftVersion"] == "fabric-loader-0.19.3-1.21.1"
    assert result["minecraftJavaMajorVersion"] == 21


def test_complete_managed_dependencies_repeats_until_graph_converges(monkeypatch: pytest.MonkeyPatch):
    instance = make_instance()
    reporter = object()
    resolutions = iter((
        DependencyResolutionResult(added_files=("Dependency A",)),
        DependencyResolutionResult(added_files=("Dependency B",)),
        DependencyResolutionResult(),
    ))
    calls: list[str] = []

    monkeypatch.setattr(ModpackDependencyResolver, "resolve", lambda received_instance, received_reporter: calls.append("resolve") or next(resolutions))
    monkeypatch.setattr(ModrinthContentManager, "ensure", lambda *args, **kwargs: calls.append("modrinth") or ("modrinth warning",))
    monkeypatch.setattr(CurseForgeContentManager, "ensure", lambda *args, **kwargs: calls.append("curseforge") or ("curseforge warning",))

    result, modrinth_warnings, curseforge_warnings = MinecraftExecutor._complete_managed_dependencies(
        instance,
        reporter,
        True,
        True,
        "launch-token",
        ("initial Modrinth warning",),
        ("initial CurseForge warning",),
    )

    assert result.changed is False
    assert calls == ["resolve", "modrinth", "curseforge", "resolve", "modrinth", "curseforge", "resolve"]
    assert modrinth_warnings == ("initial Modrinth warning", "modrinth warning", "modrinth warning")
    assert curseforge_warnings == ("initial CurseForge warning", "curseforge warning", "curseforge warning")


def test_complete_managed_dependencies_surfaces_late_manual_requirement(monkeypatch: pytest.MonkeyPatch):
    instance = make_instance()
    expected = RuntimeError("manual dependency required")

    monkeypatch.setattr(ModpackDependencyResolver, "resolve", lambda *_args, **_kwargs: DependencyResolutionResult(added_files=("Manual dependency",)))
    monkeypatch.setattr(ModrinthContentManager, "ensure", lambda *args, **kwargs: ())
    monkeypatch.setattr(CurseForgeContentManager, "ensure", lambda *args, **kwargs: (_ for _ in ()).throw(expected))

    with pytest.raises(RuntimeError) as error:
        MinecraftExecutor._complete_managed_dependencies(instance, object(), True, True, "launch-token", (), ())

    assert error.value is expected

def test_run_uses_instance_failure_policies_before_launcher_defaults(monkeypatch: pytest.MonkeyPatch):
    patch_pipeline(monkeypatch)
    settings = SimpleNamespace(
        modrinth_failure_policy="allow",
        curseforge_failure_policy="block",
    )
    received = {}

    monkeypatch.setattr(SettingsManager, "load", lambda instance: settings)

    def fake_modrinth_ensure(instance, reporter, block_launch_on_failure=True, launch_lock_token=None):
        received["modrinth_block"] = block_launch_on_failure
        received["launch_lock_token"] = launch_lock_token
        return ("mods/example.jar must be installed manually",)

    def fake_curseforge_ensure(instance, reporter, block_launch_on_failure=True, launch_lock_token=None):
        received["curseforge_block"] = block_launch_on_failure
        return ()

    monkeypatch.setattr(ModrinthContentManager, "ensure", fake_modrinth_ensure)
    monkeypatch.setattr(CurseForgeContentManager, "ensure", fake_curseforge_ensure)

    result = MinecraftExecutor.run(instance=make_instance(), authentication=object(), account=object())

    assert received["modrinth_block"] is False
    assert received["curseforge_block"] is True
    assert received["launch_lock_token"] == "test-launch-lock-token"
    assert result["warnings"] == ("mods/example.jar must be installed manually",)


def test_run_inherits_source_specific_launcher_failure_policies(monkeypatch: pytest.MonkeyPatch):
    patch_pipeline(monkeypatch)
    settings = SimpleNamespace(
        modrinth_failure_policy="inherit",
        curseforge_failure_policy="inherit",
    )
    received = {}

    monkeypatch.setattr(SettingsManager, "load", lambda instance: settings)
    monkeypatch.setattr(
        LauncherSettingsManager,
        "load",
        lambda self: {
            "managed_content": {
                "modrinth_failure_policy": "block",
                "curseforge_failure_policy": "allow",
            }
        },
    )
    monkeypatch.setattr(ModrinthContentManager, "ensure", lambda instance, reporter, block_launch_on_failure=True, launch_lock_token=None: received.update(modrinth=block_launch_on_failure) or ())
    monkeypatch.setattr(CurseForgeContentManager, "ensure", lambda instance, reporter, block_launch_on_failure=True, launch_lock_token=None: received.update(curseforge=block_launch_on_failure) or ())

    MinecraftExecutor.run(instance=make_instance(), authentication=object(), account=object())

    assert received == {"modrinth": True, "curseforge": False}



def test_private_lan_attaches_agent_and_disables_legacy_auth_bridge(monkeypatch: pytest.MonkeyPatch):
    pipeline = patch_pipeline(monkeypatch)
    settings = SimpleNamespace(lan_auth_mode="private_offline", block_launch_on_modrinth_failure=True)
    instance = make_instance()
    events: list[object] = []
    runtime_arguments = ["-Dmcw.lan.offline=true", "-javaagent:C:/cache/mcw-lan-agent.jar"]

    monkeypatch.setattr(SettingsManager, "load", lambda _instance: settings)
    monkeypatch.setattr(LanHostingManager, "disable_legacy_auth_bridges", staticmethod(lambda received: events.append(("cleanup", received)) or ()))
    monkeypatch.setattr(LanAgentManager, "runtime_arguments", classmethod(lambda cls, version, mode, received_instance, reporter=None: events.append(("agent", version, mode, received_instance)) or runtime_arguments))

    def build(version, context, received_settings, account, runtime_jvm_arguments=None):
        events.append(("command", runtime_jvm_arguments))
        return pipeline["command"]

    monkeypatch.setattr(LauncherManager, "build", build)

    MinecraftExecutor.run(instance=instance, authentication=object(), account=object())

    assert events[0] == ("cleanup", instance)
    assert events[1] == ("agent", pipeline["version"], "private_offline", instance)
    assert events[2] == ("command", runtime_arguments)


def test_run_allows_forge_compatibility_errors_when_instance_policy_allows(monkeypatch: pytest.MonkeyPatch):
    pipeline = patch_pipeline(monkeypatch)
    settings = SimpleNamespace(
        forge_preflight_failure_policy="allow",
        modrinth_failure_policy="inherit",
        curseforge_failure_policy="inherit",
    )
    issue = SimpleNamespace(severity="error", code="dependency-missing", message="Create requires missing dependency 'flywheel'.")
    report = SimpleNamespace(errors=(issue,), warnings=(), warning_count=0)

    monkeypatch.setattr(SettingsManager, "load", lambda instance: settings)
    monkeypatch.setattr(ForgePreflightManager, "scan", lambda instance, version, verify_files=False: report)
    monkeypatch.setattr(ForgePreflightManager, "validate_runtime_files", lambda instance, version: ())

    result = MinecraftExecutor.run(instance=make_instance(), authentication=object(), account=object())

    assert result["minecraftVersion"] == pipeline["version"].id
    assert any("missing dependency" in warning for warning in result.get("warnings", ()))


def test_run_stops_started_process_when_supervision_registration_fails(monkeypatch: pytest.MonkeyPatch):
    patch_pipeline(monkeypatch)
    lock = FakeRunLock()
    aborted: list[tuple[str, str]] = []

    class Process:
        pid = 4242

        def __init__(self) -> None:
            self.return_code = None
            self.terminated = False

        def poll(self):
            return self.return_code

        def terminate(self) -> None:
            self.terminated = True
            self.return_code = 0

        def kill(self) -> None:
            self.return_code = -9

    process = Process()
    monkeypatch.setattr(InstanceRunLock, "acquire", lambda _instance: lock)
    monkeypatch.setattr(JavaRuntime, "run", lambda *args: process)
    monkeypatch.setattr(ProcessSupervisor, "begin", lambda _instance: SimpleNamespace(session_id="session-id"))
    monkeypatch.setattr(ProcessSupervisor, "attach", lambda _session_id, _process: (_ for _ in ()).throw(OSError("session disk full")))
    monkeypatch.setattr(ProcessSupervisor, "stop_process", lambda target, graceful_timeout=2.5: target.terminate() or True)
    monkeypatch.setattr(ProcessSupervisor, "abort", lambda session_id, detail="": aborted.append((session_id, detail)))

    with pytest.raises(OSError, match="session disk full"):
        MinecraftExecutor.run(instance=make_instance(), authentication=object(), account=object())

    assert process.terminated is True
    assert lock.released is True
    assert aborted and aborted[0][0] == "session-id"


def test_run_asks_before_bypassing_forge_compatibility_errors(monkeypatch: pytest.MonkeyPatch):
    patch_pipeline(monkeypatch)
    settings = SimpleNamespace(
        forge_preflight_failure_policy="ask",
        modrinth_failure_policy="inherit",
        curseforge_failure_policy="inherit",
    )
    issue = SimpleNamespace(severity="error", code="dependency-missing", message="Create requires Flywheel.")
    report = SimpleNamespace(errors=(issue,), warnings=(), warning_count=0, loader="forge")
    monkeypatch.setattr(SettingsManager, "load", lambda instance: settings)
    monkeypatch.setattr(ForgePreflightManager, "scan", lambda instance, version, verify_files=False: report)

    with pytest.raises(CompatibilityConfirmationRequired) as raised:
        MinecraftExecutor.run(instance=make_instance(), authentication=object(), account=object())

    assert raised.value.instance_name == "Test Instance"
    assert raised.value.issues == (issue,)


def test_run_can_bypass_compatibility_errors_once_without_changing_policy(monkeypatch: pytest.MonkeyPatch):
    pipeline = patch_pipeline(monkeypatch)
    settings = SimpleNamespace(
        forge_preflight_failure_policy="ask",
        modrinth_failure_policy="inherit",
        curseforge_failure_policy="inherit",
    )
    issue = SimpleNamespace(severity="error", code="dependency-version", message="A dependency version may be incompatible.")
    report = SimpleNamespace(errors=(issue,), warnings=(), warning_count=0, loader="forge")
    monkeypatch.setattr(SettingsManager, "load", lambda instance: settings)
    monkeypatch.setattr(ForgePreflightManager, "scan", lambda instance, version, verify_files=False: report)
    monkeypatch.setattr(ForgePreflightManager, "validate_runtime_files", lambda instance, version: ())

    result = MinecraftExecutor.run(instance=make_instance(), authentication=object(), account=object(), allow_compatibility_issues_once=True)

    assert result["minecraftVersion"] == pipeline["version"].id
    assert "A dependency version may be incompatible." in result["warnings"]


def test_hard_loader_installation_errors_cannot_be_bypassed(monkeypatch: pytest.MonkeyPatch):
    patch_pipeline(monkeypatch)
    settings = SimpleNamespace(
        forge_preflight_failure_policy="allow",
        modrinth_failure_policy="inherit",
        curseforge_failure_policy="inherit",
    )
    issue = SimpleNamespace(severity="error", code="forge-installation", message="Forge runtime is damaged.")
    report = SimpleNamespace(errors=(issue,), warnings=(), warning_count=0, loader="forge")
    monkeypatch.setattr(SettingsManager, "load", lambda instance: settings)
    monkeypatch.setattr(ForgePreflightManager, "scan", lambda instance, version, verify_files=False: report)

    with pytest.raises(RuntimeError, match="Forge runtime is damaged"):
        MinecraftExecutor.run(instance=make_instance(), authentication=object(), account=object(), allow_compatibility_issues_once=True)


def test_start_with_java_recovery_retries_and_resets_custom_path(monkeypatch: pytest.MonkeyPatch):
    instance = make_instance()
    preferred = Path("C:/BrokenJava/bin/javaw.exe")
    recovered = Path("C:/ManagedJava/bin/javaw.exe")
    first_process = SimpleNamespace(pid=11)
    second_process = SimpleNamespace(pid=12)
    launched = []
    updated_paths = []

    monkeypatch.setattr(
        JavaResolver,
        "resolve_with_recovery",
        lambda required, reporter=None, preferred_path=None: JavaResolution(preferred, automatic=False),
    )
    monkeypatch.setattr(JavaResolver, "resolve_alternative", lambda required, excluded, reporter=None: recovered)
    monkeypatch.setattr(
        JavaRuntime,
        "run",
        lambda java, command, received_instance: launched.append(java) or (first_process if len(launched) == 1 else second_process),
    )
    probes = iter([
        JavaStartupProbe(1, None, "UnsupportedClassVersionError: class file version 65", True),
        None,
    ])
    monkeypatch.setattr(JavaRuntime, "probe_startup", lambda process: next(probes))
    monkeypatch.setattr(JavaRuntime, "close_process_log", lambda process: None)
    monkeypatch.setattr(SettingsManager, "update_java_path", lambda received_instance, path: updated_paths.append(path))
    monkeypatch.setattr(LanAgentManager, "append_log_path", lambda path, message: None)

    process, java, warnings = MinecraftExecutor._start_with_java_recovery(
        instance,
        ["example.Main"],
        17,
        ProgressReporter(None),
        str(preferred),
        None,
    )

    assert process is second_process
    assert java == recovered
    assert launched == [preferred, recovered]
    assert updated_paths == [""]
    assert warnings and "switched this instance back to Automatic" in warnings[0]


def test_complete_managed_dependencies_reuses_initial_resolution_when_no_download_was_pending(monkeypatch: pytest.MonkeyPatch):
    initial = DependencyResolutionResult()
    monkeypatch.setattr(ModpackDependencyResolver, "resolve", lambda *_args, **_kwargs: pytest.fail("unchanged initial dependency resolution must not be repeated"))
    monkeypatch.setattr(ModrinthContentManager, "ensure", lambda *_args, **_kwargs: pytest.fail("no additional provider pass is needed"))
    monkeypatch.setattr(CurseForgeContentManager, "ensure", lambda *_args, **_kwargs: pytest.fail("no additional provider pass is needed"))

    result, modrinth_warnings, curseforge_warnings = MinecraftExecutor._complete_managed_dependencies(
        make_instance(), object(), True, True, "launch-token", ("m",), ("c",), initial_resolution=initial, refresh_after_initial_ensure=False
    )

    assert result is initial
    assert modrinth_warnings == ("m",)
    assert curseforge_warnings == ("c",)
