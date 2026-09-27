from __future__ import annotations

import sys
from threading import RLock
from typing import TextIO

from mcw_core.rpc.dispatcher import CoreRpcDispatcher
from mcw_core.rpc.protocol import RpcEvent


class StdioRpcServer:
    """Line-delimited JSON-RPC 2.0 server over stdin/stdout (Sidecar mode)."""

    def __init__(
        self,
        dispatcher: CoreRpcDispatcher | None = None,
        stdin: TextIO | None = None,
        stdout: TextIO | None = None,
    ) -> None:
        self.dispatcher = dispatcher or CoreRpcDispatcher()
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self._write_lock = RLock()
        self._unsubscribe = self.dispatcher.subscribe(self._on_event)

    def _write_line(self, line: str) -> None:
        with self._write_lock:
            self.stdout.write(line + "\n")
            self.stdout.flush()

    def _on_event(self, event: RpcEvent) -> None:
        self._write_line(event.to_json())

    def serve_forever(self) -> int:
        try:
            for raw_line in self.stdin:
                stripped = raw_line.strip()
                if not stripped:
                    continue
                if stripped == '{"method":"system.shutdown"}':
                    break
                response_json = self.dispatcher.handle_json(stripped)
                self._write_line(response_json)
            return 0
        finally:
            self._unsubscribe()
