from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import queue
import threading
from typing import Any

from src.config import VERSION, VERSION_ID
from mcw_core.rpc.dispatcher import CoreRpcDispatcher
from mcw_core.rpc.protocol import RpcEvent


class HttpRpcServer:
    """Localhost HTTP JSON-RPC 2.0 + Server-Sent Events (SSE) daemon for MCW Core v1.8.0."""

    def __init__(
        self,
        dispatcher: CoreRpcDispatcher | None = None,
        host: str = "127.0.0.1",
        port: int = 0,
        root: Any = None,
        data_root: Any = None,
    ) -> None:
        resolved_root = root if root is not None else data_root
        self.dispatcher = dispatcher or CoreRpcDispatcher(root=resolved_root)
        self.host = host
        self.requested_port = port
        self._Subscribers_lock = threading.RLock()
        self._sse_queues: list[queue.Queue[str]] = []
        self._unsubscribe = self.dispatcher.subscribe(self._broadcast_event)
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        if self._httpd is not None:
            return int(self._httpd.server_address[1])
        return self.requested_port

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def _broadcast_event(self, event: RpcEvent) -> None:
        payload = event.to_json()
        with self._Subscribers_lock:
            queues = list(self._sse_queues)
        for q in queues:
            try:
                q.put_nowait(payload)
            except Exception:
                pass

    def _build_handler(self) -> type[BaseHTTPRequestHandler]:
        server_ref = self

        class _RpcRequestHandler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                return  # Silent headless operation

            def _send_cors_headers(self) -> None:
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")

            def do_OPTIONS(self) -> None:
                self.send_response(204)
                self._send_cors_headers()
                self.end_headers()

            def do_GET(self) -> None:
                if self.path == "/health":
                    body = json.dumps(
                        {
                            "ok": True,
                            "version": VERSION,
                            "version_id": VERSION_ID,
                            "protocol": "jsonrpc-2.0",
                        }
                    ).encode("utf-8")
                    self.send_response(200)
                    self._send_cors_headers()
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

                if self.path == "/events":
                    self.send_response(200)
                    self._send_cors_headers()
                    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.end_headers()

                    q: queue.Queue[str] = queue.Queue()
                    with server_ref._Subscribers_lock:
                        server_ref._sse_queues.append(q)
                    try:
                        while True:
                            msg = q.get(timeout=5.0)
                            if msg == "__CLOSE__":
                                break
                            self.wfile.write(f"data: {msg}\n\n".encode("utf-8"))
                            self.wfile.flush()
                    except Exception:
                        pass
                    finally:
                        with server_ref._Subscribers_lock:
                            if q in server_ref._sse_queues:
                                server_ref._sse_queues.remove(q)
                    return

                self.send_response(404)
                self.end_headers()

            def do_POST(self) -> None:
                if self.path != "/rpc":
                    self.send_response(404)
                    self.end_headers()
                    return
                length = int(self.headers.get("Content-Length", "0") or "0")
                raw_body = self.rfile.read(length)
                response_json = server_ref.dispatcher.handle_json(raw_body)
                encoded = response_json.encode("utf-8")
                self.send_response(200)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        return _RpcRequestHandler

    def start(self) -> str:
        return self.start_background()

    def start_background(self) -> str:
        if self._httpd is not None:
            return self.base_url
        self._httpd = ThreadingHTTPServer((self.host, self.requested_port), self._build_handler())
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="MCWCoreHttpRpcServer",
            daemon=True,
        )
        self._thread.start()
        return self.base_url

    def serve_forever(self) -> None:
        self._httpd = ThreadingHTTPServer((self.host, self.requested_port), self._build_handler())
        try:
            self._httpd.serve_forever()
        finally:
            self.stop()

    def stop(self) -> None:
        with self._Subscribers_lock:
            for q in self._sse_queues:
                try:
                    q.put_nowait("__CLOSE__")
                except Exception:
                    pass
            self._sse_queues.clear()
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        self._unsubscribe()
