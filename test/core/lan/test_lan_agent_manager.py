from pathlib import Path
from types import SimpleNamespace
import hashlib

import pytest

from src.core.lan.lan_agent_manager import LanAgentInstallResult, LanAgentManager
from src.core.lan.lan_agent_target_resolver import LanAgentTarget, LanAgentTargetResolution, LanAgentTargetResolver


def make_version(version_id: str = "26.2") -> SimpleNamespace:
    return SimpleNamespace(id=version_id, raw_json={}, downloads={}, libraries=[])


def make_instance(tmp_path: Path, version_id: str = "26.2", loader: str = "fabric") -> SimpleNamespace:
    return SimpleNamespace(name="Pack", instance_dir=tmp_path / "Pack", version_id=version_id, mod_loader=(loader, "test"))


def test_bundled_agent_matches_pinned_sha256() -> None:
    path = Path(__file__).resolve().parents[3] / "runtime" / LanAgentManager.AGENT_FILENAME

    assert path.is_file()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == LanAgentManager.AGENT_SHA256


def test_install_copies_verified_agent_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = Path(__file__).resolve().parents[3] / "runtime" / LanAgentManager.AGENT_FILENAME
    destination = tmp_path / "cache" / LanAgentManager.AGENT_FILENAME
    monkeypatch.setattr(LanAgentManager, "_bundled_agent_path", classmethod(lambda cls: source))
    monkeypatch.setattr(LanAgentManager, "runtime_agent_path", classmethod(lambda cls: destination))

    first = LanAgentManager.install()
    second = LanAgentManager.install()

    assert first == LanAgentInstallResult(destination, True)
    assert second == LanAgentInstallResult(destination, False)
    assert destination.read_bytes() == source.read_bytes()
    assert not destination.with_suffix(destination.suffix + ".part").exists()


def test_runtime_arguments_are_emitted_only_for_private_offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    installed = tmp_path / "mcw-lan-agent.jar"
    agent_log = tmp_path / "logs" / LanAgentManager.AGENT_LOG_FILENAME
    instance = make_instance(tmp_path, "1.20.1")
    resolution = LanAgentTargetResolution(
        game_version="1.20.1",
        loader="fabric",
        targets=(
            LanAgentTarget("intermediary", "net/minecraft/server/MinecraftServer", "method_3864"),
            LanAgentTarget("official", "net/minecraft/server/MinecraftServer", "d"),
        ),
    )

    monkeypatch.setattr(LanAgentManager, "install", classmethod(lambda cls: LanAgentInstallResult(installed, False)))
    monkeypatch.setattr(LanAgentManager, "log_path", classmethod(lambda cls, _instance: agent_log))
    monkeypatch.setattr(LanAgentManager, "prepare_log", classmethod(lambda cls, _instance, _auth_mode=None: agent_log))
    monkeypatch.setattr(LanAgentTargetResolver, "resolve", classmethod(lambda cls, _version, _instance, _reporter=None: resolution))

    assert LanAgentManager.runtime_arguments(make_version("1.20.1"), "microsoft_only", instance) == []
    arguments = LanAgentManager.runtime_arguments(make_version("1.20.1"), "private_offline", instance)

    assert arguments == [
        "-Dmcw.lan.offline=true",
        "-Dmcw.lan.loader=fabric",
        "-Dmcw.lan.targets=net/minecraft/server/MinecraftServer#method_3864;net/minecraft/server/MinecraftServer#d",
        f"-Dmcw.lan.log={agent_log.resolve().as_posix()}",
        f"-javaagent:{installed}",
    ]


def test_runtime_arguments_skip_unsupported_legacy_version_without_blocking_launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agent_log = tmp_path / "logs" / LanAgentManager.AGENT_LOG_FILENAME
    instance = make_instance(tmp_path, "1.16.5")
    resolution = LanAgentTargetResolution(
        game_version="1.16.5",
        loader="fabric",
        targets=(),
        warnings=("MCW LAN Agent supports Minecraft 1.17 or newer.",),
    )
    install_called = False

    def install(cls):
        nonlocal install_called
        install_called = True
        raise AssertionError("install must not run for unsupported versions")

    monkeypatch.setattr(LanAgentManager, "install", classmethod(install))
    monkeypatch.setattr(LanAgentManager, "log_path", classmethod(lambda cls, _instance: agent_log))
    monkeypatch.setattr(LanAgentManager, "prepare_log", classmethod(lambda cls, _instance, _auth_mode=None: agent_log))
    monkeypatch.setattr(LanAgentTargetResolver, "resolve", classmethod(lambda cls, _version, _instance, _reporter=None: resolution))

    assert LanAgentManager.runtime_arguments(make_version("1.16.5"), "private_offline", instance) == []
    assert install_called is False
    assert "outside the supported 1.17+ range" in agent_log.read_text(encoding="utf-8")


def test_prepare_log_replaces_previous_run_and_read_log_returns_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "logs" / LanAgentManager.AGENT_LOG_FILENAME
    path.parent.mkdir(parents=True)
    path.write_text("stale log", encoding="utf-8")
    instance = make_instance(tmp_path)
    monkeypatch.setattr(LanAgentManager, "log_path", classmethod(lambda cls, _instance: path))

    prepared = LanAgentManager.prepare_log(instance)

    assert prepared == path
    text = LanAgentManager.read_log(instance)
    assert "stale log" not in text
    assert "MCW LAN Agent launch diagnostics" in text
    assert "Instance: Pack" in text
    assert "Runtime targets: resolved from Mojang, Fabric, Quilt, Forge, and NeoForge mappings" in text


def test_sanitize_user_arguments_removes_only_mcw_agent_overrides() -> None:
    arguments = LanAgentManager.sanitize_user_jvm_arguments(
        [
            "-Dmcw.lan.offline=false",
            "-Dmcw.lan.targets=example/Evil#run",
            "-javaagent:C:/cache/mcw-lan-agent.jar",
            "-javaagent:C:/tools/other-agent.jar",
            "-Dexample=true",
        ]
    )

    assert arguments == ["-javaagent:C:/tools/other-agent.jar", "-Dexample=true"]


def test_runtime_arguments_identify_neoforge_loader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    installed = tmp_path / "mcw-lan-agent.jar"
    agent_log = tmp_path / "logs" / LanAgentManager.AGENT_LOG_FILENAME
    instance = make_instance(tmp_path, "1.21.1", loader="neoforge")
    resolution = LanAgentTargetResolution(
        game_version="1.21.1",
        loader="neoforge",
        targets=(LanAgentTarget("neoforge-srg", "net/minecraft/server/MinecraftServer", "m_129985_"),),
    )
    monkeypatch.setattr(LanAgentManager, "install", classmethod(lambda cls: LanAgentInstallResult(installed, False)))
    monkeypatch.setattr(LanAgentManager, "log_path", classmethod(lambda cls, _instance: agent_log))
    monkeypatch.setattr(LanAgentManager, "prepare_log", classmethod(lambda cls, _instance, _auth_mode=None: agent_log))
    monkeypatch.setattr(LanAgentTargetResolver, "resolve", classmethod(lambda cls, _version, _instance, _reporter=None: resolution))

    arguments = LanAgentManager.runtime_arguments(make_version("1.21.1"), "private_offline", instance)

    assert "-Dmcw.lan.loader=neoforge" in arguments
    assert "-Dmcw.lan.targets=net/minecraft/server/MinecraftServer#m_129985_" in arguments


def test_runtime_arguments_identify_quilt_loader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    installed = tmp_path / "mcw-lan-agent.jar"
    agent_log = tmp_path / "logs" / LanAgentManager.AGENT_LOG_FILENAME
    instance = make_instance(tmp_path, "1.20.1", loader="quilt")
    resolution = LanAgentTargetResolution(
        game_version="1.20.1",
        loader="quilt",
        targets=(LanAgentTarget("quilt-hashed", "net/minecraft/unmapped/C_abcdef", "m_hashonline"),),
    )
    monkeypatch.setattr(LanAgentManager, "install", classmethod(lambda cls: LanAgentInstallResult(installed, False)))
    monkeypatch.setattr(LanAgentManager, "log_path", classmethod(lambda cls, _instance: agent_log))
    monkeypatch.setattr(LanAgentManager, "prepare_log", classmethod(lambda cls, _instance, _auth_mode=None: agent_log))
    monkeypatch.setattr(LanAgentTargetResolver, "resolve", classmethod(lambda cls, _version, _instance, _reporter=None: resolution))

    arguments = LanAgentManager.runtime_arguments(make_version("1.20.1"), "private_offline", instance)

    assert "-Dmcw.lan.loader=quilt" in arguments
    assert "-Dmcw.lan.targets=net/minecraft/unmapped/C_abcdef#m_hashonline" in arguments
