from __future__ import annotations

import io
import json
from pathlib import Path
import sys

from mcw_core.rpc import (
    CoreRpcClient,
    CoreRpcDispatcher,
    HttpRpcServer,
    RpcEvent,
    StdioRpcServer,
)


def test_core_rpc_direct_and_event_subscription(tmp_path: Path) -> None:
    client = CoreRpcClient(mode="direct", root=tmp_path)
    events: list[RpcEvent] = []
    unsub = client.subscribe(lambda evt: events.append(evt))

    ping = client.call("system.ping")
    assert ping["ok"] is True
    assert ping["version_id"] == "1.8.0"
    assert ping["protocol"] == "jsonrpc-2.0"

    # Test sensitive data redaction via JSON-RPC
    redacted = client.call(
        "diagnostics.redact",
        text=r"accessToken=secret_jwt_123 C:\Users\TestPlayer\AppData\Roaming",
    )
    assert "[REDACTED_TOKEN]" in redacted["redacted"] or "REDACTED" in redacted["redacted"]

    # Test diagnostic bundle export via JSON-RPC
    bundle = client.call(
        "diagnostics.export_bundle",
        instance_name="TestInstance",
        log_text="Sample log output",
    )
    assert Path(bundle["path"]).is_file()

    # Test operation lifecycle events
    client.call("operations.pause")
    client.call("operations.resume")
    assert len(events) >= 2
    assert events[0].event == "operation.state"
    unsub()
    client.close()


def test_core_rpc_http_server_and_client(tmp_path: Path) -> None:
    dispatcher = CoreRpcDispatcher(root=tmp_path)
    server = HttpRpcServer(dispatcher=dispatcher, host="127.0.0.1", port=0)
    base_url = server.start_background()
    try:
        client = CoreRpcClient(mode="http", http_url=base_url)
        ping = client.call("system.ping")
        assert ping["ok"] is True
        assert ping["version"] == "v1.8.0"

        hotfix = client.call("system.hotfix_status")
        assert "cdn_label" in hotfix
        client.close()
    finally:
        server.stop()


def test_core_rpc_stdio_server_stream(tmp_path: Path) -> None:
    dispatcher = CoreRpcDispatcher(root=tmp_path)
    fake_in = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 42, "method": "system.version", "params": {}})
        + "\n"
        + '{"method":"system.shutdown"}\n'
    )
    fake_out = io.StringIO()
    stdio_srv = StdioRpcServer(dispatcher=dispatcher, stdin=fake_in, stdout=fake_out)
    exit_code = stdio_srv.serve_forever()
    assert exit_code == 0

    lines = [line for line in fake_out.getvalue().splitlines() if line.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["id"] == 42
    assert parsed["result"]["version_id"] == "1.8.0"


def test_core_rpc_stdio_sidecar_subprocess(tmp_path: Path) -> None:
    client = CoreRpcClient(
        mode="stdio",
        root=tmp_path,
        python_executable=sys.executable,
    )
    try:
        res = client.call("system.ping")
        assert res["ok"] is True
        assert res["version_id"] == "1.8.0"
    finally:
        client.close()
