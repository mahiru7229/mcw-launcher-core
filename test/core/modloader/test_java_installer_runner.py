from pathlib import Path
import subprocess
from types import SimpleNamespace

from src.core.java.java_resolver import JavaResolver
from src.core.modloader.java_installer_runner import ModLoaderJavaRunner


def test_retries_mod_loader_installer_once_after_java_runtime_failure(monkeypatch):
    first_java = Path("C:/Java/8/bin/javaw.exe")
    second_java = Path("C:/Java/17/bin/javaw.exe")
    calls: list[Path] = []

    monkeypatch.setattr(JavaResolver, "resolve_with_recovery", staticmethod(lambda required, reporter=None, preferred_path=None: SimpleNamespace(path=first_java)))
    monkeypatch.setattr(JavaResolver, "resolve_alternative", staticmethod(lambda required, excluded, reporter=None: second_java))

    def invoke(java, arguments, cwd, timeout):
        calls.append(java)
        if len(calls) == 1:
            return subprocess.CompletedProcess([str(java)], 1, stdout="UnsupportedClassVersionError", stderr="")
        return subprocess.CompletedProcess([str(java)], 0, stdout="installed", stderr="")

    monkeypatch.setattr(ModLoaderJavaRunner, "_invoke", staticmethod(invoke))

    result = ModLoaderJavaRunner.run(8, ["-jar", "installer.jar"], Path("."), preferred_java_path=first_java)

    assert calls == [first_java, second_java]
    assert result.returncode == 0
    assert result.java_path == second_java
    assert result.attempts == 2
    assert "Java attempt 1" in result.output
    assert "Java attempt 2" in result.output


def test_does_not_retry_non_java_installer_failure(monkeypatch):
    java = Path("C:/Java/17/bin/javaw.exe")
    calls: list[Path] = []
    monkeypatch.setattr(JavaResolver, "resolve_with_recovery", staticmethod(lambda required, reporter=None, preferred_path=None: SimpleNamespace(path=java)))

    def invoke(selected, arguments, cwd, timeout):
        calls.append(selected)
        return subprocess.CompletedProcess([str(selected)], 1, stdout="Installer data is invalid", stderr="")

    monkeypatch.setattr(ModLoaderJavaRunner, "_invoke", staticmethod(invoke))

    result = ModLoaderJavaRunner.run(17, ["-jar", "installer.jar"], Path("."))

    assert calls == [java]
    assert result.returncode == 1
    assert result.attempts == 1


def test_retries_transient_network_failure_once_with_same_java(monkeypatch):
    java = Path("C:/Java/17/bin/javaw.exe")
    calls: list[Path] = []
    monkeypatch.setattr(JavaResolver, "resolve_with_recovery", staticmethod(lambda required, reporter=None, preferred_path=None: SimpleNamespace(path=java)))

    def invoke(selected, arguments, cwd, timeout):
        calls.append(selected)
        if len(calls) == 1:
            return subprocess.CompletedProcess([str(selected)], 1, stdout="java.net.SocketTimeoutException: Read timed out", stderr="")
        return subprocess.CompletedProcess([str(selected)], 0, stdout="installed", stderr="")

    monkeypatch.setattr(ModLoaderJavaRunner, "_invoke", staticmethod(invoke))

    result = ModLoaderJavaRunner.run(17, ["-jar", "installer.jar"], Path("."))

    assert calls == [java, java]
    assert result.returncode == 0
    assert result.attempts == 2


def test_installer_timeout_becomes_java_recovery_error(monkeypatch):
    java = Path("C:/Java/17/bin/javaw.exe")
    monkeypatch.setattr(JavaResolver, "resolve_with_recovery", staticmethod(lambda required, reporter=None, preferred_path=None: SimpleNamespace(path=java)))
    monkeypatch.setattr(
        ModLoaderJavaRunner,
        "_invoke",
        staticmethod(lambda selected, arguments, cwd, timeout: subprocess.TimeoutExpired([str(selected)], timeout, output="partial output")),
    )

    from src.core.java.java_resolver import JavaRecoveryError

    try:
        ModLoaderJavaRunner.run(17, ["-jar", "installer.jar"], Path("."), timeout=5)
    except JavaRecoveryError as error:
        assert "exceeded its 5-second timeout" in str(error)
        assert "partial output" in str(error)
    else:
        raise AssertionError("Installer timeout must be reported as JavaRecoveryError")
