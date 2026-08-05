import zipfile
from pathlib import Path

import pytest

from src.core.java.java_command_compactor import JavaCommandCompactor


def _unfold_manifest(raw: bytes) -> list[str]:
    lines = raw.decode("utf-8").split("\r\n")
    unfolded: list[str] = []
    for line in lines:
        if line.startswith(" ") and unfolded:
            unfolded[-1] += line[1:]
        elif line:
            unfolded.append(line)
    return unfolded


def test_prepare_keeps_short_windows_command_unchanged(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr("src.core.java.java_command_compactor.os.name", "nt")
    command = ["-Xmx2G", "-cp", "first.jar;client.jar", "net.minecraft.client.main.Main"]

    result = JavaCommandCompactor.prepare(Path("javaw.exe"), command, tmp_path)

    assert result == command
    assert not (tmp_path / ".mcw" / "launch").exists()


def test_prepare_compacts_long_windows_classpath_into_manifest_jar(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr("src.core.java.java_command_compactor.os.name", "nt")
    entries = [str(tmp_path / "libraries" / f"library-{index:04d}-{'x' * 90}.jar") for index in range(320)]
    command = ["-Xmx4G", "-cp", ";".join(entries), "net.minecraft.client.main.Main", "--username", "Steve"]

    result = JavaCommandCompactor.prepare(Path("C:/Java/bin/javaw.exe"), command, tmp_path)

    classpath_jar = type(tmp_path)(result[2])
    assert result[:2] == ["-Xmx4G", "-cp"]
    assert result[3:] == command[3:]
    assert classpath_jar.parent == tmp_path / ".mcw" / "launch"
    assert classpath_jar.is_file()
    assert JavaCommandCompactor._command_length(Path("C:/Java/bin/javaw.exe"), result) < JavaCommandCompactor.SAFE_WINDOWS_COMMAND_LIMIT

    with zipfile.ZipFile(classpath_jar, "r") as archive:
        manifest = archive.read("META-INF/MANIFEST.MF")

    physical_lines = [line for line in manifest.split(b"\r\n") if line]
    assert all(len(line) <= 70 for line in physical_lines)
    unfolded = _unfold_manifest(manifest)
    classpath_line = next(line for line in unfolded if line.startswith("Class-Path: "))
    assert type(tmp_path)(entries[0]).resolve(strict=False).as_uri() in classpath_line
    assert type(tmp_path)(entries[-1]).resolve(strict=False).as_uri() in classpath_line


def test_prepare_force_compacts_short_classpath(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr("src.core.java.java_command_compactor.os.name", "nt")
    first = tmp_path / "first.jar"
    client = tmp_path / "client.jar"
    command = ["-cp", f"{first};{client}", "example.Main"]

    result = JavaCommandCompactor.prepare(Path("javaw.exe"), command, tmp_path, force=True)

    assert result[0] == "-cp"
    assert type(tmp_path)(result[1]).is_file()
    assert result[2] == "example.Main"


def test_prepare_cannot_compact_command_without_classpath(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr("src.core.java.java_command_compactor.os.name", "nt")
    command = ["-Xmx2G", "example.Main", "x" * 40_000]

    result = JavaCommandCompactor.prepare(Path("javaw.exe"), command, tmp_path, force=True)

    assert result == command
