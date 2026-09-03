from pathlib import Path
from io import BytesIO
import os
import stat
import tarfile
from zipfile import ZipFile

import pytest

from src.core.java.java_archive_extractor import JavaArchiveExtractor


def test_extract_finds_java_home(tmp_path: Path) -> None:
    archive_path = tmp_path / "java.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("jdk-17/bin/javaw.exe", b"test")
        archive.writestr("jdk-17/release", b"JAVA_VERSION=17")

    java_home = JavaArchiveExtractor.extract(archive_path, tmp_path / "extract")
    assert java_home.name == "jdk-17"
    assert (java_home / "bin" / "javaw.exe").is_file()


def test_rejects_zip_slip(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside.txt", b"unsafe")

    with pytest.raises(RuntimeError):
        JavaArchiveExtractor.extract(archive_path, tmp_path / "extract")


def test_extracts_linux_tar_and_preserves_java_executable(tmp_path: Path) -> None:
    archive_path = tmp_path / "java.tar.gz"
    payload = b"#!/bin/sh\n"
    with tarfile.open(archive_path, "w:gz") as archive:
        directory = tarfile.TarInfo("jdk-21/bin")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        archive.addfile(directory)
        executable = tarfile.TarInfo("jdk-21/bin/java")
        executable.size = len(payload)
        executable.mode = 0o755
        archive.addfile(executable, BytesIO(payload))

    java_home = JavaArchiveExtractor.extract(archive_path, tmp_path / "extract")

    java = java_home / "bin" / "java"
    assert java.is_file()
    assert java.read_bytes() == payload
    if os.name != "nt":
        assert java.stat().st_mode & stat.S_IXUSR
