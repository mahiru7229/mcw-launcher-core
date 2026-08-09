from src.core.fs.windows_path import to_extended_windows_path


def test_extended_windows_path_supports_drive_paths() -> None:
    assert to_extended_windows_path(r"C:\\Users\\Player\\MCW") == r"\\?\C:\\Users\\Player\\MCW"


def test_extended_windows_path_supports_unc_paths() -> None:
    assert to_extended_windows_path(r"\\server\share\MCW") == r"\\?\UNC\server\share\MCW"
