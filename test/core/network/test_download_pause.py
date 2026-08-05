from __future__ import annotations

import hashlib
from pathlib import Path
from threading import Event, Thread
from time import sleep

import pytest

from src.core.network.download_pause import DownloadCancelledError, DownloadPauseController, download_pause_controller, is_download_cancelled, is_download_paused
from src.core.network.httpx_downloader import HttpDownloader


@pytest.fixture(autouse=True)
def reset_pause_and_http_state():
    download_pause_controller.finish()
    HttpDownloader.close_client()
    HttpDownloader._path_locks.clear()
    yield
    download_pause_controller.finish()
    HttpDownloader.close_client()
    HttpDownloader._path_locks.clear()


def test_pause_controller_blocks_until_resume_and_cancel_is_detectable() -> None:
    controller = DownloadPauseController()
    controller.begin()
    completed = Event()

    assert controller.request_pause() is True

    worker = Thread(target=lambda: (controller.raise_if_requested(), completed.set()), daemon=True)
    worker.start()
    sleep(0.05)
    assert completed.is_set() is False
    assert controller.is_paused is True

    assert controller.request_resume() is True
    worker.join(timeout=1)
    assert completed.is_set() is True

    assert controller.request_cancel() is True
    with pytest.raises(DownloadCancelledError) as captured:
        controller.raise_if_requested()

    wrapped = RuntimeError("wrapped")
    wrapped.__cause__ = captured.value
    assert is_download_cancelled(wrapped) is True
    assert is_download_paused(wrapped) is True

    controller.finish()
    assert controller.request_pause() is False


def test_http_download_pauses_and_resumes_same_worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    content = b"abcdef"
    destination = tmp_path / "example.jar"
    info = type("Info", (), {"url": "https://example.com/example.jar", "sha1": hashlib.sha1(content).hexdigest(), "size": len(content)})()
    paused = Event()
    result: list[Path] = []
    errors: list[BaseException] = []

    class Response:
        status_code = 200
        headers = {"Content-Length": "6"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self, chunk_size: int):
            yield b"abc"
            download_pause_controller.request_pause()
            paused.set()
            yield b"def"

    class Client:
        def stream(self, method: str, url: str, *, headers: dict[str, str], timeout: float):
            return Response()

    monkeypatch.setattr(HttpDownloader, "get_client", lambda: Client())

    def run_download() -> None:
        try:
            result.append(HttpDownloader.download(info, destination, max_retry=1))
        except BaseException as error:
            errors.append(error)

    download_pause_controller.begin()
    thread = Thread(target=run_download, daemon=True)
    thread.start()
    assert paused.wait(timeout=1)
    sleep(0.05)
    assert thread.is_alive() is True
    assert download_pause_controller.request_resume() is True
    thread.join(timeout=2)
    download_pause_controller.finish()

    assert errors == []
    assert result == [destination]
    assert destination.read_bytes() == content
    assert destination.with_name(destination.name + ".part").exists() is False


def test_cancel_removes_partial_and_next_launch_restarts_full(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    content = b"abcdef"
    destination = tmp_path / "example.jar"
    info = type("Info", (), {"url": "https://example.com/example.jar", "sha1": hashlib.sha1(content).hexdigest(), "size": len(content)})()
    requests: list[str | None] = []
    phase = {"value": 1}

    class Response:
        def __init__(self) -> None:
            self.status_code = 200
            self.headers = {"Content-Length": "6"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self, chunk_size: int):
            if phase["value"] == 1:
                yield b"abc"
                download_pause_controller.request_cancel()
                yield b"def"
                return
            yield content

    class Client:
        def stream(self, method: str, url: str, *, headers: dict[str, str], timeout: float):
            requests.append(headers.get("Range"))
            return Response()

    monkeypatch.setattr(HttpDownloader, "get_client", lambda: Client())

    download_pause_controller.begin()
    with pytest.raises(DownloadCancelledError):
        HttpDownloader.download(info, destination, max_retry=1)

    partial = destination.with_name(destination.name + ".part")
    assert partial.exists() is False
    assert destination.exists() is False

    download_pause_controller.finish()
    phase["value"] = 2
    download_pause_controller.begin()
    result = HttpDownloader.download(info, destination, max_retry=1)
    download_pause_controller.finish()

    assert result.read_bytes() == content
    assert partial.exists() is False
    assert requests == [None, None]
