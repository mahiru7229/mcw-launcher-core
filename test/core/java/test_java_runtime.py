from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.fs.paths import Paths
from src.core.java.java_runtime import JavaRuntime


class FixedDateTime:
    @classmethod
    def now(cls):
        return cls()

    def strftime(self, format_string: str) -> str:
        assert format_string == "%Y-%m-%d_%H-%M-%S"
        return "2026-07-12_14-30-45"


@pytest.fixture
def instance():
    return SimpleNamespace(
        name="Test Instance"
    )


@pytest.fixture
def instance_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    path = tmp_path / "instances" / "Test Instance"

    monkeypatch.setattr(
        Paths,
        "load_instance_dir",
        lambda name: path,
    )

    return path


def test_run_returns_process_from_popen(
    monkeypatch: pytest.MonkeyPatch,
    instance,
    instance_dir: Path,
):
    expected_process = object()

    monkeypatch.setattr(
        "src.core.java.java_runtime.datetime",
        FixedDateTime,
    )
    monkeypatch.setattr(
        "src.core.java.java_runtime.subprocess.Popen",
        lambda *args, **kwargs: expected_process,
    )

    result = JavaRuntime.run(
        java=Path("C:/Java/bin/javaw.exe"),
        command=["-version"],
        instance=instance,
    )

    assert result is expected_process


def test_run_builds_command_with_java_first(
    monkeypatch: pytest.MonkeyPatch,
    instance,
    instance_dir: Path,
):
    received = {}

    monkeypatch.setattr(
        "src.core.java.java_runtime.datetime",
        FixedDateTime,
    )

    def fake_popen(command, **kwargs):
        received["command"] = command
        return object()

    monkeypatch.setattr(
        "src.core.java.java_runtime.subprocess.Popen",
        fake_popen,
    )

    JavaRuntime.run(
        java=Path("C:/Java/bin/javaw.exe"),
        command=[
            "-Xmx2G",
            "-cp",
            "libraries;client.jar",
            "net.minecraft.client.main.Main",
        ],
        instance=instance,
    )

    assert received["command"] == [
        str(Path("C:/Java/bin/javaw.exe")),
        "-Xmx2G",
        "-cp",
        "libraries;client.jar",
        "net.minecraft.client.main.Main",
    ]


def test_run_uses_instance_directory_as_cwd(
    monkeypatch: pytest.MonkeyPatch,
    instance,
    instance_dir: Path,
):
    received = {}

    monkeypatch.setattr(
        "src.core.java.java_runtime.datetime",
        FixedDateTime,
    )

    def fake_popen(command, **kwargs):
        received.update(kwargs)
        return object()

    monkeypatch.setattr(
        "src.core.java.java_runtime.subprocess.Popen",
        fake_popen,
    )

    JavaRuntime.run(
        java=Path("javaw.exe"),
        command=[],
        instance=instance,
    )

    assert received["cwd"] == instance_dir


def test_run_resolves_instance_directory_by_name(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    received_names = []
    expected_dir = tmp_path / "instances" / "Named Instance"
    instance = SimpleNamespace(
        name="Named Instance",
        instance_dir=tmp_path / "ignored-directory",
    )

    def fake_load_instance_dir(name: str) -> Path:
        received_names.append(name)
        return expected_dir

    monkeypatch.setattr(
        Paths,
        "load_instance_dir",
        fake_load_instance_dir,
    )
    monkeypatch.setattr(
        "src.core.java.java_runtime.datetime",
        FixedDateTime,
    )
    monkeypatch.setattr(
        "src.core.java.java_runtime.subprocess.Popen",
        lambda *args, **kwargs: object(),
    )

    JavaRuntime.run(
        java=Path("javaw.exe"),
        command=[],
        instance=instance,
    )

    assert received_names == [
        "Named Instance",
        "Named Instance",
    ]


def test_run_creates_logs_directory(
    monkeypatch: pytest.MonkeyPatch,
    instance,
    instance_dir: Path,
):
    monkeypatch.setattr(
        "src.core.java.java_runtime.datetime",
        FixedDateTime,
    )
    monkeypatch.setattr(
        "src.core.java.java_runtime.subprocess.Popen",
        lambda *args, **kwargs: object(),
    )

    logs_dir = instance_dir / "logs"

    assert not logs_dir.exists()

    JavaRuntime.run(
        java=Path("javaw.exe"),
        command=[],
        instance=instance,
    )

    assert logs_dir.exists()
    assert logs_dir.is_dir()


def test_run_creates_timestamped_log_file(
    monkeypatch: pytest.MonkeyPatch,
    instance,
    instance_dir: Path,
):
    monkeypatch.setattr(
        "src.core.java.java_runtime.datetime",
        FixedDateTime,
    )
    monkeypatch.setattr(
        "src.core.java.java_runtime.subprocess.Popen",
        lambda *args, **kwargs: object(),
    )

    JavaRuntime.run(
        java=Path("javaw.exe"),
        command=[],
        instance=instance,
    )

    expected_log = (
        instance_dir
        / "logs"
        / "minecraft-2026-07-12_14-30-45.log"
    )

    assert expected_log.exists()
    assert expected_log.is_file()


def test_run_redirects_stdout_to_log_file(
    monkeypatch: pytest.MonkeyPatch,
    instance,
    instance_dir: Path,
):
    received = {}

    monkeypatch.setattr(
        "src.core.java.java_runtime.datetime",
        FixedDateTime,
    )

    def fake_popen(command, **kwargs):
        received.update(kwargs)
        return object()

    monkeypatch.setattr(
        "src.core.java.java_runtime.subprocess.Popen",
        fake_popen,
    )

    JavaRuntime.run(
        java=Path("javaw.exe"),
        command=[],
        instance=instance,
    )

    log_file = received["stdout"]

    assert log_file.name.endswith(
        "minecraft-2026-07-12_14-30-45.log"
    )
    assert log_file.mode == "w"
    assert log_file.encoding.lower().replace("-", "") == "utf8"
    assert log_file.closed is True


def test_run_redirects_stderr_to_stdout(
    monkeypatch: pytest.MonkeyPatch,
    instance,
    instance_dir: Path,
):
    received = {}

    monkeypatch.setattr(
        "src.core.java.java_runtime.datetime",
        FixedDateTime,
    )

    def fake_popen(command, **kwargs):
        received.update(kwargs)
        return object()

    monkeypatch.setattr(
        "src.core.java.java_runtime.subprocess.Popen",
        fake_popen,
    )

    JavaRuntime.run(
        java=Path("javaw.exe"),
        command=[],
        instance=instance,
    )

    from src.core.java import java_runtime

    assert (
        received["stderr"]
        is java_runtime.subprocess.STDOUT
    )


def test_run_disables_standard_input(
    monkeypatch: pytest.MonkeyPatch,
    instance,
    instance_dir: Path,
):
    received = {}

    monkeypatch.setattr(
        "src.core.java.java_runtime.datetime",
        FixedDateTime,
    )

    def fake_popen(command, **kwargs):
        received.update(kwargs)
        return object()

    monkeypatch.setattr(
        "src.core.java.java_runtime.subprocess.Popen",
        fake_popen,
    )

    JavaRuntime.run(
        java=Path("javaw.exe"),
        command=[],
        instance=instance,
    )

    from src.core.java import java_runtime

    assert (
        received["stdin"]
        is java_runtime.subprocess.DEVNULL
    )


def test_run_uses_create_no_window_on_windows(
    monkeypatch: pytest.MonkeyPatch,
    instance,
    instance_dir: Path,
):
    received = {}

    monkeypatch.setattr(
        "src.core.java.java_runtime.datetime",
        FixedDateTime,
    )
    monkeypatch.setattr(
        "src.core.java.java_runtime.os.name",
        "nt",
    )
    monkeypatch.setattr(
        "src.core.java.java_runtime.subprocess.CREATE_NO_WINDOW",
        0x08000000,
        raising=False,
    )

    def fake_popen(command, **kwargs):
        received.update(kwargs)
        return object()

    monkeypatch.setattr(
        "src.core.java.java_runtime.subprocess.Popen",
        fake_popen,
    )

    JavaRuntime.run(
        java=Path("javaw.exe"),
        command=[],
        instance=instance,
    )

    assert received["creationflags"] == 0x08000000


def test_run_uses_zero_creation_flags_outside_windows(
    monkeypatch: pytest.MonkeyPatch,
    instance,
    instance_dir: Path,
):
    received = {}

    monkeypatch.setattr(
        "src.core.java.java_runtime.datetime",
        FixedDateTime,
    )
    monkeypatch.setattr(
        "src.core.java.java_runtime.os.name",
        "posix",
    )

    def fake_popen(command, **kwargs):
        received.update(kwargs)
        return object()

    monkeypatch.setattr(
        "src.core.java.java_runtime.subprocess.Popen",
        fake_popen,
    )

    JavaRuntime.run(
        java=Path("java"),
        command=[],
        instance=instance,
    )

    assert received["creationflags"] == 0


def test_run_closes_log_file_when_popen_fails(
    monkeypatch: pytest.MonkeyPatch,
    instance,
    instance_dir: Path,
):
    received = {}

    monkeypatch.setattr(
        "src.core.java.java_runtime.datetime",
        FixedDateTime,
    )

    def failing_popen(command, **kwargs):
        received.update(kwargs)
        raise OSError("cannot start Java")

    monkeypatch.setattr(
        "src.core.java.java_runtime.subprocess.Popen",
        failing_popen,
    )

    with pytest.raises(
        OSError,
        match="cannot start Java",
    ):
        JavaRuntime.run(
            java=Path("javaw.exe"),
            command=[],
            instance=instance,
        )

    assert received["stdout"].closed is True


def test_run_does_not_swallow_popen_exception(
    monkeypatch: pytest.MonkeyPatch,
    instance,
    instance_dir: Path,
):
    monkeypatch.setattr(
        "src.core.java.java_runtime.datetime",
        FixedDateTime,
    )

    expected_error = PermissionError(
        "Java executable is not permitted"
    )

    def failing_popen(*args, **kwargs):
        raise expected_error

    monkeypatch.setattr(
        "src.core.java.java_runtime.subprocess.Popen",
        failing_popen,
    )

    with pytest.raises(PermissionError) as error:
        JavaRuntime.run(
            java=Path("javaw.exe"),
            command=[],
            instance=instance,
        )

    assert error.value is expected_error


def test_run_passes_all_expected_popen_options(
    monkeypatch: pytest.MonkeyPatch,
    instance,
    instance_dir: Path,
):
    received = {}

    monkeypatch.setattr(
        "src.core.java.java_runtime.datetime",
        FixedDateTime,
    )
    monkeypatch.setattr(
        "src.core.java.java_runtime.os.name",
        "posix",
    )

    def fake_popen(command, **kwargs):
        received["command"] = command
        received["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(
        "src.core.java.java_runtime.subprocess.Popen",
        fake_popen,
    )

    JavaRuntime.run(
        java=Path("java"),
        command=["-version"],
        instance=instance,
    )

    from src.core.java import java_runtime

    assert received["command"] == [
        "java",
        "-version",
    ]
    assert set(received["kwargs"]) == {
        "cwd",
        "stdin",
        "stdout",
        "stderr",
        "creationflags",
    }
    assert received["kwargs"]["cwd"] == instance_dir
    assert (
        received["kwargs"]["stdin"]
        is java_runtime.subprocess.DEVNULL
    )
    assert (
        received["kwargs"]["stderr"]
        is java_runtime.subprocess.STDOUT
    )
    assert received["kwargs"]["creationflags"] == 0

def test_run_retries_winerror_206_with_compacted_classpath(monkeypatch: pytest.MonkeyPatch, instance, instance_dir: Path):
    received_commands = []
    expected_process = object()

    monkeypatch.setattr("src.core.java.java_runtime.datetime", FixedDateTime)
    monkeypatch.setattr("src.core.java.java_runtime.os.name", "nt")
    monkeypatch.setattr("src.core.java.java_runtime.subprocess.CREATE_NO_WINDOW", 0x08000000, raising=False)

    def fake_popen(command, **kwargs):
        received_commands.append(command)
        if len(received_commands) == 1:
            error = OSError("The filename or extension is too long")
            error.winerror = 206
            raise error
        return expected_process

    monkeypatch.setattr("src.core.java.java_runtime.subprocess.Popen", fake_popen)

    result = JavaRuntime.run(
        java=Path("C:/Java/bin/javaw.exe"),
        command=["-Xmx4G", "-cp", "first.jar;client.jar", "example.Main"],
        instance=instance,
    )

    assert result is expected_process
    assert len(received_commands) == 2
    assert received_commands[0][3] == "first.jar;client.jar"
    compacted_classpath = type(instance_dir)(received_commands[1][3])
    assert compacted_classpath.is_file()
    assert compacted_classpath.name.startswith("classpath-")
    assert compacted_classpath.suffix == ".jar"


def test_run_reports_actionable_error_when_winerror_206_cannot_be_compacted(monkeypatch: pytest.MonkeyPatch, instance, instance_dir: Path):
    monkeypatch.setattr("src.core.java.java_runtime.datetime", FixedDateTime)
    monkeypatch.setattr("src.core.java.java_runtime.os.name", "nt")
    monkeypatch.setattr("src.core.java.java_runtime.subprocess.CREATE_NO_WINDOW", 0x08000000, raising=False)

    def failing_popen(command, **kwargs):
        error = OSError("The filename or extension is too long")
        error.winerror = 206
        raise error

    monkeypatch.setattr("src.core.java.java_runtime.subprocess.Popen", failing_popen)

    with pytest.raises(RuntimeError, match="Move MCW Launcher to a shorter folder"):
        JavaRuntime.run(java=Path("javaw.exe"), command=["example.Main", "x" * 40_000], instance=instance)


def test_run_applies_saved_dedicated_gpu_preference(
    monkeypatch: pytest.MonkeyPatch,
    instance,
    instance_dir: Path,
):
    received = {}
    monkeypatch.setattr("src.core.java.java_runtime.datetime", FixedDateTime)
    monkeypatch.setattr(
        "src.core.java.java_runtime.LauncherSettingsManager.load",
        lambda self: {"launch": {"prefer_dedicated_gpu": True}},
    )
    monkeypatch.setattr(
        "src.core.java.java_runtime.GpuPreferenceManager.apply_to_java",
        lambda java, enabled: received.update(java=java, enabled=enabled) or True,
    )
    monkeypatch.setattr(
        "src.core.java.java_runtime.subprocess.Popen",
        lambda *args, **kwargs: object(),
    )

    java = Path("C:/Java/bin/javaw.exe")
    JavaRuntime.run(java=java, command=[], instance=instance)

    assert received == {"java": java, "enabled": True}


def test_java_runtime_failure_classifier_only_accepts_strong_java_signatures():
    assert JavaRuntime.is_java_runtime_failure(
        "java.lang.UnsupportedClassVersionError: compiled by a more recent version of the Java Runtime"
    ) is True
    assert JavaRuntime.is_java_runtime_failure("Exception in thread main: missing Minecraft library") is False


def test_probe_startup_reads_early_java_failure_log(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    process = type("Process", (), {"pid": 77, "poll": lambda self: 1})()
    log_path = tmp_path / "minecraft.log"
    log_path.write_text("Error: Could not create the Java Virtual Machine.", encoding="utf-8")
    monkeypatch.setattr(JavaRuntime, "log_path", classmethod(lambda cls, received: log_path))

    probe = JavaRuntime.probe_startup(process)

    assert probe is not None
    assert probe.exit_code == 1
    assert probe.java_runtime_failure is True
    assert probe.log_path == log_path


def test_unique_log_path_preserves_existing_log(tmp_path: Path):
    existing = tmp_path / "minecraft-2026-08-05_18-00-00.log"
    existing.write_text("first attempt", encoding="utf-8")

    selected = JavaRuntime._unique_log_path(tmp_path, "2026-08-05_18-00-00")

    assert selected == tmp_path / "minecraft-2026-08-05_18-00-00-1.log"
    assert existing.read_text(encoding="utf-8") == "first attempt"
