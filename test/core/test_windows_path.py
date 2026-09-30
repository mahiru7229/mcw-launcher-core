from pathlib import Path
from src.core.fs.windows_path import (
    copy_file,
    is_file,
    link_file,
    make_directory,
    native_filesystem_path,
    open_file,
    replace_path,
    same_file,
    stat_path,
    to_extended_windows_path,
    unlink_file,
)


def test_extended_windows_path_supports_drive_paths() -> None:
    assert to_extended_windows_path(r"C:\Users\Player\MCW") == r"\\?\C:\Users\Player\MCW"


def test_extended_windows_path_supports_unc_paths() -> None:
    assert to_extended_windows_path(r"\\server\share\MCW") == r"\\?\UNC\server\share\MCW"


def test_copy_file_and_same_file(tmp_path: Path) -> None:
    src = tmp_path / "source.txt"
    dst = tmp_path / "sub" / "dest.txt"
    with open_file(src, "w", encoding="utf-8") as f:
        f.write("hello world")

    assert is_file(src)
    assert not is_file(dst)
    copy_file(src, dst)
    assert is_file(dst)
    assert stat_path(dst).st_size == len("hello world")
    with open_file(dst, "r", encoding="utf-8") as f:
        assert f.read() == "hello world"
    assert not same_file(src, dst)


def test_link_file(tmp_path: Path) -> None:
    src = tmp_path / "source.bin"
    dst = tmp_path / "nested" / "linked.bin"
    with open_file(src, "wb") as f:
        f.write(b"binary data 12345")

    link_file(src, dst)
    assert is_file(dst)
    assert same_file(src, dst)


def test_replace_path_and_unlink(tmp_path: Path) -> None:
    src = tmp_path / "a.txt"
    dst = tmp_path / "b.txt"
    with open_file(src, "w") as f:
        f.write("test replace")
    replace_path(src, dst)
    assert not is_file(src)
    assert is_file(dst)
    unlink_file(dst)
    assert not is_file(dst)
    # missing_ok should not raise
    unlink_file(dst, missing_ok=True)


def test_long_path_operations(tmp_path: Path) -> None:
    # Build a path exceeding MAX_PATH (260 chars)
    long_segment = "a_very_long_directory_name_to_force_extended_path_handling"
    deep_dir = tmp_path / long_segment / long_segment / long_segment / long_segment
    make_directory(deep_dir)
    long_file = deep_dir / "my_deeply_nested_file_with_a_long_name.txt"

    with open_file(long_file, "w", encoding="utf-8") as f:
        f.write("deep file content")

    assert is_file(long_file)
    assert stat_path(long_file).st_size == len("deep file content")

    dst_file = deep_dir / "copied_deep_file.txt"
    copy_file(long_file, dst_file)
    assert is_file(dst_file)

    with open_file(dst_file, "r", encoding="utf-8") as f:
        assert f.read() == "deep file content"

