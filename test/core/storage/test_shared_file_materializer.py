from __future__ import annotations

from pathlib import Path
from src.core.fs.windows_path import is_file, make_directory, open_file
from src.core.storage.shared_file_materializer import SharedFileMaterializer


def test_publish_from_staging_basic(tmp_path: Path) -> None:
    staging = tmp_path / "staging" / "lib.jar"
    target = tmp_path / "libraries" / "com" / "example" / "lib.jar"

    make_directory(staging.parent)
    with open_file(staging, "wb") as f:
        f.write(b"JAR_CONTENT_12345")

    SharedFileMaterializer.publish_from_staging(staging, target)

    assert is_file(target)
    assert not is_file(staging)
    with open_file(target, "rb") as f:
        assert f.read() == b"JAR_CONTENT_12345"


def test_publish_from_staging_long_path(tmp_path: Path) -> None:
    # Build a destination path where path length > 260 characters
    long_segment = "a_very_long_directory_name_for_simulating_deep_libraries_folder"
    deep_dest_dir = tmp_path / long_segment / long_segment / long_segment / "com" / "google" / "guava" / "listenablefuture" / "9999.0-empty-to-avoid-conflict-with-guava"
    target = deep_dest_dir / "listenablefuture-9999.0-empty-to-avoid-conflict-with-guava.jar"

    staging = tmp_path / "staging" / "listenablefuture.jar"
    make_directory(staging.parent)
    with open_file(staging, "wb") as f:
        f.write(b"EXTENDED_PATH_JAR_CONTENT")

    assert len(str(target.resolve())) > 260

    SharedFileMaterializer.publish_from_staging(staging, target)

    assert is_file(target)
    with open_file(target, "rb") as f:
        assert f.read() == b"EXTENDED_PATH_JAR_CONTENT"


def test_link_or_copy_basic_and_long_path(tmp_path: Path) -> None:
    long_segment = "another_very_long_directory_structure_for_link_or_copy_testing"
    deep_dir = tmp_path / long_segment / long_segment / long_segment / long_segment
    source = deep_dir / "source_library.jar"
    dest = deep_dir / "destination_library.jar"

    make_directory(deep_dir)
    with open_file(source, "wb") as f:
        f.write(b"TEST_LIBRARY_DATA")

    assert len(str(source.resolve())) > 260

    SharedFileMaterializer.link_or_copy(source, dest)
    assert is_file(dest)
    with open_file(dest, "rb") as f:
        assert f.read() == b"TEST_LIBRARY_DATA"

    # Running link_or_copy again when destination already has identical content
    SharedFileMaterializer.link_or_copy(source, dest)
    assert is_file(dest)


def test_same_content(tmp_path: Path) -> None:
    file1 = tmp_path / "file1.bin"
    file2 = tmp_path / "file2.bin"
    file3 = tmp_path / "file3.bin"

    with open_file(file1, "wb") as f:
        f.write(b"identical data")
    with open_file(file2, "wb") as f:
        f.write(b"identical data")
    with open_file(file3, "wb") as f:
        f.write(b"different data")

    assert SharedFileMaterializer.same_content(file1, file2)
    assert not SharedFileMaterializer.same_content(file1, file3)
