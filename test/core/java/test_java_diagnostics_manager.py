from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src.core.java.java_diagnostics_manager import JavaDiagnosticsManager
from src.core.java.java_manager import JavaManager
from src.core.progress.progress_reporter import ProgressReporter
from src.models.java.java import JavaInstallation
from src.models.java.java_source import JavaSource


def test_java_diagnostics_parses_vendor_architecture_and_home(monkeypatch, tmp_path: Path) -> None:
    java = tmp_path / "jdk" / "bin" / "javaw.exe"
    java.parent.mkdir(parents=True)
    java.write_bytes(b"")
    (java.parent / "java.exe").write_bytes(b"")
    output = """
Property settings:
    java.home = C:\\Java\\jdk-21
    java.vendor = Eclipse Adoptium
    java.version = 21.0.8
    os.arch = amd64
openjdk version "21.0.8"
"""
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: SimpleNamespace(stdout="", stderr=output, returncode=0))
    diagnostic = JavaDiagnosticsManager.inspect(JavaInstallation(version=21, executable=java, source=JavaSource.JAVA_HOME))
    assert diagnostic.major_version == 21
    assert diagnostic.vendor == "Eclipse Adoptium"
    assert diagnostic.architecture == "amd64"
    assert diagnostic.version_string == "21.0.8"
    assert "Eclipse Adoptium" in diagnostic.display_name


def test_scan_reports_java_inspection_progress(monkeypatch, tmp_path: Path) -> None:
    java = JavaInstallation(version=17, executable=tmp_path / "javaw.exe", source=JavaSource.PATH)
    events = []
    monkeypatch.setattr(JavaManager, "find_installation", lambda reporter=None: [java])
    monkeypatch.setattr(JavaDiagnosticsManager, "inspect", lambda installation: SimpleNamespace(major_version=17, vendor="Vendor", executable=installation.executable))

    JavaDiagnosticsManager.scan(ProgressReporter(events.append))

    assert [event.current for event in events] == [0, 1]
    assert events[-1].message == "java.scan.completed"
