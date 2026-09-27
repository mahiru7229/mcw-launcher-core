from __future__ import annotations

import argparse
from pathlib import Path
import sys

from mcw_core.rpc.dispatcher import CoreRpcDispatcher
from mcw_core.rpc.http_server import HttpRpcServer
from mcw_core.rpc.stdio_server import StdioRpcServer


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MCW Core v1.8.0 Headless JSON-RPC Server (Stdio Sidecar & HTTP Daemon)")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="MCW workspace data root")
    parser.add_argument("--stdio", action="store_true", help="Run line-delimited JSON-RPC 2.0 over stdin/stdout")
    parser.add_argument("--http", action="store_true", help="Run Localhost HTTP JSON-RPC + SSE server")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=28475, help="HTTP bind port (default: 28475)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    dispatcher = CoreRpcDispatcher(root=args.root)

    if args.http:
        server = HttpRpcServer(dispatcher=dispatcher, host=args.host, port=args.port)
        print(f"MCW Core v1.8.0 HTTP RPC listening on http://{args.host}:{args.port}", flush=True)
        server.serve_forever()
        return 0

    stdio_server = StdioRpcServer(dispatcher=dispatcher)
    return stdio_server.serve_forever()


if __name__ == "__main__":
    raise SystemExit(main())
