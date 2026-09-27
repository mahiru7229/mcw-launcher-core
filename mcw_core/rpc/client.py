from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any
import urllib.request

from mcw_core.rpc.dispatcher import CoreRpcDispatcher
from mcw_core.rpc.protocol import RpcEvent, RpcRequest


class CoreRpcError(RuntimeError):
    """Raised when the remote or local JSON-RPC Core returns an error object."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data


class CoreRpcClient:
    """Multi-transport JSON-RPC 2.0 Client for MCW Core v1.8.0.

    Supports three transport modes:
    - ``direct``: Serializes requests to JSON, invokes ``CoreRpcDispatcher.handle_json``,
      and parses the JSON response (100% strict JSON boundary without socket overhead).
    - ``http``: Connects to ``HttpRpcServer`` over ``http://127.0.0.1:<port>/rpc``.
    - ``stdio``: Spawns ``mcw_core.rpc.cli --stdio`` as a Sidecar child process and
      communicates over ``stdin`` / ``stdout`` pipes.
    """

    def __init__(
        self,
        mode: str = "direct",
        *,
        dispatcher: CoreRpcDispatcher | None = None,
        root: Path | str | None = None,
        data_root: Path | str | None = None,
        http_url: str = "",
        base_url: str = "",
        python_executable: str | None = None,
    ) -> None:
        self.mode = mode.lower().strip()
        resolved_root = root if root is not None else data_root
        self.root = Path(resolved_root) if resolved_root is not None else None
        resolved_url = http_url or base_url
        self.http_url = resolved_url.rstrip("/")
        self.python_executable = python_executable or sys.executable
        self._lock = threading.RLock()
        self._next_id = 1
        self._dispatcher: CoreRpcDispatcher | None = dispatcher
        self._proc: subprocess.Popen[str] | None = None

        if self.mode == "direct" and self._dispatcher is None:
            self._dispatcher = CoreRpcDispatcher(root=self.root)
        elif self.mode == "stdio":
            self._start_stdio_sidecar()

    def _start_stdio_sidecar(self) -> None:
        cmd = [self.python_executable, "-m", "mcw_core.rpc.cli", "--stdio"]
        if self.root is not None:
            cmd.extend(["--root", str(self.root)])
        core_repo_root = Path(__file__).resolve().parents[2]
        self._proc = subprocess.Popen(
            cmd,
            cwd=str(core_repo_root),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )

    def subscribe(self, callback: Callable[[RpcEvent], None]) -> Callable[[], None]:
        if self._dispatcher is not None:
            return self._dispatcher.subscribe(callback)
        return lambda: None

    def call(self, method: str, params: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        merged_params = dict(params or {})
        merged_params.update(kwargs)
        with self._lock:
            req_id = self._next_id
            self._next_id += 1
            request_json = RpcRequest(method=method, params=merged_params, id=req_id).to_json()

            if self.mode == "direct":
                assert self._dispatcher is not None
                raw_response = self._dispatcher.handle_json(request_json)
            elif self.mode == "http":
                req = urllib.request.Request(
                    f"{self.http_url}/rpc",
                    data=request_json.encode("utf-8"),
                    headers={"Content-Type": "application/json; charset=utf-8"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=15.0) as resp:
                    raw_response = resp.read().decode("utf-8")
            elif self.mode == "stdio":
                if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
                    raise RuntimeError("Stdio RPC Sidecar process is not running.")
                self._proc.stdin.write(request_json + "\n")
                self._proc.stdin.flush()
                raw_response = self._proc.stdout.readline().strip()
                while raw_response:
                    parsed_line = json.loads(raw_response)
                    if parsed_line.get("method") == "core.event":
                        raw_response = self._proc.stdout.readline().strip()
                        continue
                    break
            else:
                raise ValueError(f"Unsupported RPC client mode: {self.mode}")

        payload = json.loads(raw_response)
        if "error" in payload and payload["error"] is not None:
            err = payload["error"]
            raise CoreRpcError(
                code=int(err.get("code", -32000)),
                message=str(err.get("message", "RPC Error")),
                data=err.get("data"),
            )
        return payload.get("result")

    def close(self) -> None:
        with self._lock:
            if self._proc is not None:
                try:
                    if self._proc.stdin:
                        self._proc.stdin.write('{"method":"system.shutdown"}\n')
                        self._proc.stdin.flush()
                    self._proc.terminate()
                    self._proc.wait(timeout=3.0)
                except Exception:
                    pass
                finally:
                    self._proc = None
