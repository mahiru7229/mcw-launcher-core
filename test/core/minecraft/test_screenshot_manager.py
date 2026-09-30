from __future__ import annotations

import os
from pathlib import Path
import time

import pytest

from mcw_core.api.minecraft.screenshot_manager import ScreenshotManager


def test_screenshot_manager_list_and_delete(tmp_path: Path) -> None:
    shots_dir = tmp_path / "screenshots"
    shots_dir.mkdir()

    s1 = shots_dir / "2026-09-01_10.00.00.png"
    s1.write_bytes(b"\x89PNG\r\n\x1a\n")
    # Set older mtime
    os.utime(s1, (1000, 1000))

    s2 = shots_dir / "2026-09-10_12.00.00.png"
    s2.write_bytes(b"\x89PNG\r\n\x1a\n")
    # Set newer mtime
    os.utime(s2, (2000, 2000))

    # Not a png, should be ignored
    (shots_dir / "notes.txt").write_text("not a screenshot", encoding="utf-8")

    screenshots = ScreenshotManager.list_screenshots(tmp_path)
    assert len(screenshots) == 2
    assert screenshots[0].filename == "2026-09-10_12.00.00.png"
    assert screenshots[1].filename == "2026-09-01_10.00.00.png"

    # Delete one
    deleted = ScreenshotManager.delete_screenshot(tmp_path, "2026-09-01_10.00.00.png")
    assert deleted is True
    assert not s1.exists()

    # Verify listing again
    screenshots_after = ScreenshotManager.list_screenshots(tmp_path)
    assert len(screenshots_after) == 1
    assert screenshots_after[0].filename == "2026-09-10_12.00.00.png"
