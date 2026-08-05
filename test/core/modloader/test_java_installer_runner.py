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
