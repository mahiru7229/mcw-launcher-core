from __future__ import annotations

from pathlib import Path

from src.models.screenshot.screenshot_info import ScreenshotInfo


class ScreenshotManager:
    """Discovers and manages in-game screenshot captures."""

    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}

    @classmethod
    def list_screenshots(cls, instance_dir: Path | str) -> list[ScreenshotInfo]:
        screenshots_dir = Path(instance_dir) / "screenshots"
        if not screenshots_dir.is_dir():
            return []

        screenshots: list[ScreenshotInfo] = []
        for file_path in screenshots_dir.iterdir():
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in cls.IMAGE_EXTENSIONS:
                continue

            try:
                stat = file_path.stat()
                size = stat.st_size
                mtime = stat.st_mtime
            except OSError:
                size = 0
                mtime = 0.0

            screenshots.append(
                ScreenshotInfo(
                    path=file_path,
                    file_name=file_path.name,
                    file_size_bytes=size,
                    created_timestamp=mtime,
                )
            )

        # Sort newest first
        screenshots.sort(key=lambda s: s.created_timestamp, reverse=True)
        return screenshots

    @classmethod
    def delete_screenshot(cls, path_or_instance_dir: Path | str, filename: str | None = None) -> bool:
        if filename is not None:
            target = Path(path_or_instance_dir) / "screenshots" / filename
        else:
            target = Path(path_or_instance_dir)
        if not target.is_file():
            return False
        try:
            target.unlink()
            return True
        except OSError:
            return False
