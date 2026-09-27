from __future__ import annotations

import json
import logging
import os
import queue
import socket
import struct
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Minecraft Discord Application ID (SimpleRPC / Minecraft)
DEFAULT_DISCORD_CLIENT_ID = "762726289341677668"

OP_HANDSHAKE = 0
OP_FRAME = 1
OP_CLOSE = 2
OP_PING = 3
OP_PONG = 4


def get_discord_client_id(override: str | None = None) -> str:
    cleaned = str(override or "").strip()
    if cleaned:
        return cleaned
    return str(os.environ.get("MCW_DISCORD_CLIENT_ID", DEFAULT_DISCORD_CLIENT_ID)).strip() or DEFAULT_DISCORD_CLIENT_ID


class DiscordRpcClient:
    """Low-level cross-platform Discord IPC client using standard library."""

    def __init__(self, client_id: str | None = None) -> None:
        self.client_id = str(client_id or get_discord_client_id()).strip()
        self._pipe: Any = None
        self._sock: socket.socket | None = None
        self._connected = False
        self._lock = threading.RLock()

    @property
    def is_connected(self) -> bool:
        return self._connected

    def set_client_id(self, client_id: str | None) -> None:
        new_id = str(client_id or "").strip() or DEFAULT_DISCORD_CLIENT_ID
        with self._lock:
            if self.client_id != new_id:
                self.client_id = new_id
                self._close_internal()

    def connect(self) -> bool:
        with self._lock:
            if self._connected:
                return True
            self._close_internal()

            if sys.platform == "win32":
                return self._connect_windows()
            return self._connect_unix()

    def _connect_windows(self) -> bool:
        for index in range(10):
            pipe_path = rf"\\.\pipe\discord-ipc-{index}"
            try:
                # Open pipe directly in binary unbuffered mode
                self._pipe = open(pipe_path, "r+b", buffering=0)
                if self._handshake():
                    self._connected = True
                    return True
                self._close_internal()
            except (OSError, FileNotFoundError):
                self._close_internal()
                continue
            except Exception as error:
                logger.debug("Failed opening Discord pipe %s: %s", pipe_path, error)
                self._close_internal()
                continue
        return False

    def _connect_unix(self) -> bool:
        candidates: list[Path] = []
        xdg = os.environ.get("XDG_RUNTIME_DIR")
        if xdg:
            candidates.append(Path(xdg))
        tmp = os.environ.get("TMPDIR") or os.environ.get("TMP") or "/tmp"
        candidates.append(Path(tmp))
        uid = getattr(os, "getuid", lambda: None)()
        if uid is not None:
            candidates.append(Path(f"/run/user/{uid}"))

        for base in candidates:
            if not base.is_dir():
                continue
            for index in range(10):
                sock_path = base / f"discord-ipc-{index}"
                if not sock_path.exists():
                    continue
                try:
                    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    sock.settimeout(2.0)
                    sock.connect(str(sock_path))
                    self._sock = sock
                    if self._handshake():
                        self._connected = True
                        return True
                    self._close_internal()
                except (OSError, socket.error) as error:
                    logger.debug("Failed connecting Unix socket %s: %s", sock_path, error)
                    self._close_internal()
                    continue
        return False

    def _send(self, op: int, payload: dict[str, Any]) -> bool:
        raw_json = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        header = struct.pack("<II", op, len(raw_json))
        packet = header + raw_json

        try:
            if self._pipe is not None:
                self._pipe.write(packet)
                return True
            if self._sock is not None:
                self._sock.sendall(packet)
                return True
        except (OSError, socket.error) as error:
            logger.debug("Error writing to Discord IPC: %s", error)
            self._close_internal()
        return False

    def _pipe_ready(self, required: int = 8, timeout: float = 2.0) -> bool:
        if self._pipe is None:
            return False
        if sys.platform != "win32":
            return True
        try:
            import msvcrt
            import ctypes
            handle = msvcrt.get_osfhandle(self._pipe.fileno())
            avail = ctypes.c_ulong()
            start = time.monotonic()
            while time.monotonic() - start < timeout:
                success = ctypes.windll.kernel32.PeekNamedPipe(
                    handle, None, 0, None, ctypes.byref(avail), None
                )
                if not success:
                    return False
                if avail.value >= required:
                    return True
                time.sleep(0.01)
            return False
        except Exception:
            return True

    def _receive(self, timeout: float = 2.0) -> tuple[int, dict[str, Any]] | None:
        try:
            if self._pipe is not None:
                if not self._pipe_ready(required=8, timeout=timeout):
                    return None
                header = self._pipe.read(8)
                if not header or len(header) < 8:
                    return None
                op, length = struct.unpack("<II", header)
                if length > 0:
                    if not self._pipe_ready(required=length, timeout=timeout):
                        return None
                    payload_bytes = self._pipe.read(length)
                else:
                    payload_bytes = b""
                data = json.loads(payload_bytes.decode("utf-8")) if payload_bytes else {}
                return op, data

            if self._sock is not None:
                self._sock.settimeout(timeout)
                header = self._sock.recv(8)
                if not header or len(header) < 8:
                    return None
                op, length = struct.unpack("<II", header)
                chunks: list[bytes] = []
                received = 0
                while received < length:
                    chunk = self._sock.recv(min(length - received, 4096))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    received += len(chunk)
                payload_bytes = b"".join(chunks)
                data = json.loads(payload_bytes.decode("utf-8")) if payload_bytes else {}
                return op, data
        except (OSError, socket.error, json.JSONDecodeError) as error:
            logger.debug("Error reading from Discord IPC: %s", error)
            self._close_internal()
        return None

    def _handshake(self) -> bool:
        payload = {"v": 1, "client_id": self.client_id}
        if not self._send(OP_HANDSHAKE, payload):
            return False
        response = self._receive(timeout=2.0)
        if response is None:
            return False
        op, data = response
        if op == OP_CLOSE or data.get("code") in {4000, 4001, 4002}:
            logger.debug("Discord handshake rejected: %s", data)
            return False
        return True

    def update_activity(
        self,
        details: str,
        state: str,
        start_timestamp: int | None = None,
        large_image: str = "default",
        large_text: str = "MCW Launcher",
        small_image: str | None = None,
        small_text: str | None = None,
    ) -> bool:
        if not self._connected and not self.connect():
            return False

        activity: dict[str, Any] = {
            "details": str(details or "").strip(),
            "state": str(state or "").strip(),
            "assets": {
                "large_image": str(large_image or "default"),
                "large_text": str(large_text or "MCW Launcher"),
            },
        }

        if small_image:
            activity["assets"]["small_image"] = str(small_image)
            if small_text:
                activity["assets"]["small_text"] = str(small_text)

        if start_timestamp is not None and start_timestamp > 0:
            activity["timestamps"] = {"start": int(start_timestamp)}

        payload = {
            "cmd": "SET_ACTIVITY",
            "args": {
                "pid": os.getpid(),
                "activity": activity,
            },
            "nonce": str(uuid.uuid4()),
        }

        with self._lock:
            if not self._send(OP_FRAME, payload):
                return False
            # Read response to keep pipe synchronized
            self._receive(timeout=1.0)
            return True

    def clear_activity(self) -> bool:
        if not self._connected:
            return True

        payload = {
            "cmd": "SET_ACTIVITY",
            "args": {
                "pid": os.getpid(),
                "activity": None,
            },
            "nonce": str(uuid.uuid4()),
        }

        with self._lock:
            success = self._send(OP_FRAME, payload)
            if success:
                self._receive(timeout=1.0)
            return success

    def close(self) -> None:
        with self._lock:
            self._close_internal()

    def _close_internal(self) -> None:
        self._connected = False
        if self._pipe is not None:
            try:
                self._pipe.close()
            except Exception:
                pass
            self._pipe = None
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None


class DiscordRpcService:
    """Background service managing Discord RPC lifecycle for Minecraft instances."""

    def __init__(self, client: DiscordRpcClient | None = None, enabled: bool = True) -> None:
        self._client = client or DiscordRpcClient()
        self._enabled = bool(enabled)
        self._queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        self._worker_thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.RLock()
        self._current_activity: dict[str, Any] | None = None

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            new_state = bool(enabled)
            if self._enabled == new_state:
                return
            self._enabled = new_state
            current_activity = dict(self._current_activity) if self._current_activity is not None else None

        if not new_state:
            self._enqueue("clear", {})
            self._enqueue("close", {})
        elif current_activity is not None:
            self._enqueue("update", current_activity)

    def set_client_id(self, client_id: str | None) -> None:
        new_id = str(client_id or "").strip() or DEFAULT_DISCORD_CLIENT_ID
        with self._lock:
            if self._client.client_id == new_id:
                return
            self._client.set_client_id(new_id)
            current_activity = dict(self._current_activity) if self._current_activity is not None else None

        self._enqueue("close", {})
        if current_activity is not None and self.enabled:
            self._enqueue("update", current_activity)

    def _start_worker_if_needed(self) -> None:
        with self._lock:
            if self._worker_thread is None or not self._worker_thread.is_alive():
                self._running = True
                self._worker_thread = threading.Thread(
                    target=self._worker_loop,
                    name="DiscordRpcWorker",
                    daemon=True,
                )
                self._worker_thread.start()

    def _enqueue(self, action: str, data: dict[str, Any]) -> None:
        self._start_worker_if_needed()
        self._queue.put((action, data))

    def _worker_loop(self) -> None:
        while True:
            with self._lock:
                if not self._running and self._queue.empty():
                    break
            try:
                action, data = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                if action == "update":
                    if self.enabled:
                        self._client.update_activity(
                            details=data.get("details", ""),
                            state=data.get("state", ""),
                            start_timestamp=data.get("start_timestamp"),
                            large_image=data.get("large_image", "default"),
                            large_text=data.get("large_text", "MCW Launcher"),
                        )
                elif action == "clear":
                    self._client.clear_activity()
                elif action == "close":
                    self._client.close()
                elif action == "stop":
                    self._client.clear_activity()
                    self._client.close()
                    break
            except Exception as error:
                logger.debug("Discord RPC worker error: %s", error)
            finally:
                self._queue.task_done()

    def on_game_started(
        self,
        instance_name: str,
        minecraft_version: str,
        loader_name: str = "vanilla",
        loader_version: str = "-1",
        start_timestamp: int | None = None,
    ) -> None:
        name = str(instance_name or "Minecraft").strip()
        version = str(minecraft_version or "").strip()
        loader = str(loader_name or "vanilla").strip().capitalize()

        if loader.lower() == "vanilla" or str(loader_version).strip() in {"", "-1"}:
            details = f"Minecraft {version}" if version else "Minecraft"
        else:
            details = f"{loader} {version}"

        state = f"Instance: {name}"
        timestamp = start_timestamp if start_timestamp is not None else int(time.time())

        activity_data = {
            "details": details,
            "state": state,
            "start_timestamp": timestamp,
            "large_image": "default",
            "large_text": f"MCW Launcher — {name}",
        }

        with self._lock:
            self._current_activity = activity_data

        if self.enabled:
            self._enqueue("update", activity_data)

    def on_game_stopped(self) -> None:
        with self._lock:
            self._current_activity = None
        self._enqueue("clear", {})
        self._enqueue("close", {})

    def shutdown(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
        self._queue.put(("stop", {}))
        if self._worker_thread is not None and self._worker_thread.is_alive():
            try:
                self._worker_thread.join(timeout=1.0)
            except Exception:
                pass


_global_discord_rpc_service: DiscordRpcService | None = None
_service_lock = threading.Lock()


def get_discord_rpc_service() -> DiscordRpcService:
    global _global_discord_rpc_service
    with _service_lock:
        if _global_discord_rpc_service is None:
            _global_discord_rpc_service = DiscordRpcService()
        return _global_discord_rpc_service
