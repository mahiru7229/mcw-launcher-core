from pathlib import Path
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
