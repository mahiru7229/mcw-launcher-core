from __future__ import annotations

import io
import json
from pathlib import Path
import struct
import time
from unittest.mock import MagicMock

import pytest

from mcw_core.api.integrations.discord import (
    DiscordRpcClient,
    DiscordRpcService,
    get_discord_rpc_service,
)
from src.core.config.launcher_settings_manager import LauncherSettingsManager
from src.core.integrations.discord.discord_rpc import OP_CLOSE, OP_FRAME, OP_HANDSHAKE


class DummyPipe(io.BytesIO):
    """In-memory binary stream simulating a duplex pipe/socket for Discord IPC."""

    def __init__(self) -> None:
        super().__init__()
        self.closed_count = 0

    def close(self) -> None:
        self.closed_count += 1
        super().close()


def test_discord_rpc_framing_and_send() -> None:
    client = DiscordRpcClient(client_id="test_id")
    dummy = DummyPipe()
    client._pipe = dummy
    client._connected = True

    payload = {"test": "data", "count": 42}
    success = client._send(OP_FRAME, payload)
    assert success is True

    data = dummy.getvalue()
    assert len(data) >= 8
    op, length = struct.unpack("<II", data[:8])
    assert op == OP_FRAME
    assert length == len(data) - 8

    body = json.loads(data[8:].decode("utf-8"))
    assert body == payload


def test_discord_rpc_receive() -> None:
    client = DiscordRpcClient(client_id="test_id")
    payload = {"cmd": "DISPATCH", "evt": "READY"}
    encoded = json.dumps(payload).encode("utf-8")
    header = struct.pack("<II", OP_FRAME, len(encoded))

    stream = io.BytesIO(header + encoded)
    client._pipe = stream
    client._connected = True

    result = client._receive(timeout=0.5)
    assert result is not None
    op, data = result
    assert op == OP_FRAME
    assert data == payload


def test_discord_rpc_connect_fails_gracefully_when_discord_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DiscordRpcClient(client_id="nonexistent")
    monkeypatch.setattr(client, "_connect_windows", lambda: False)
    monkeypatch.setattr(client, "_connect_unix", lambda: False)
    assert client.connect() is False
    assert client.is_connected is False


def test_discord_rpc_update_activity_payload() -> None:
    client = DiscordRpcClient(client_id="test_id")
    sent_payloads: list[dict] = []

    def mock_send(op: int, payload: dict) -> bool:
        sent_payloads.append(payload)
        return True

    client._send = mock_send  # type: ignore[method-assign]
    client._receive = lambda timeout=1.0: (OP_FRAME, {})  # type: ignore[method-assign]
    client._connected = True

    ok = client.update_activity(
        details="Fabric 1.21.1",
        state="Instance: Survival",
        start_timestamp=1700000000,
        large_image="default",
        large_text="MCW Launcher — Survival",
    )
    assert ok is True
    assert len(sent_payloads) == 1

    activity = sent_payloads[0]["args"]["activity"]
    assert activity["details"] == "Fabric 1.21.1"
    assert activity["state"] == "Instance: Survival"
    assert activity["timestamps"] == {"start": 1700000000}
    assert activity["assets"]["large_image"] == "default"
    assert activity["assets"]["large_text"] == "MCW Launcher — Survival"


def test_discord_rpc_clear_activity_payload() -> None:
    client = DiscordRpcClient(client_id="test_id")
    sent_payloads: list[dict] = []

    def mock_send(op: int, payload: dict) -> bool:
        sent_payloads.append(payload)
        return True

    client._send = mock_send  # type: ignore[method-assign]
    client._receive = lambda timeout=1.0: (OP_FRAME, {})  # type: ignore[method-assign]
    client._connected = True

    ok = client.clear_activity()
    assert ok is True
    assert len(sent_payloads) == 1
    assert sent_payloads[0]["args"]["activity"] is None


def test_discord_rpc_service_lifecycle() -> None:
    mock_client = MagicMock(spec=DiscordRpcClient)
    service = DiscordRpcService(client=mock_client, enabled=True)

    try:
        assert service.enabled is True

        service.on_game_started(
            instance_name="Hypixel",
            minecraft_version="1.8.9",
            loader_name="forge",
            loader_version="11.15.1.2318",
            start_timestamp=1700000000,
        )

        for _ in range(20):
            if mock_client.update_activity.called:
                break
            time.sleep(0.05)

        mock_client.update_activity.assert_called_once_with(
            details="Forge 1.8.9",
            state="Instance: Hypixel",
            start_timestamp=1700000000,
            large_image="default",
            large_text="MCW Launcher — Hypixel",
        )

        service.on_game_stopped()
        for _ in range(20):
            if mock_client.clear_activity.called and mock_client.close.called:
                break
            time.sleep(0.05)

        mock_client.clear_activity.assert_called()
        mock_client.close.assert_called()

        # Toggle disabled
        service.set_enabled(False)
        assert service.enabled is False
    finally:
        service.shutdown()


def test_discord_rpc_service_vanilla_formatting() -> None:
    mock_client = MagicMock(spec=DiscordRpcClient)
    service = DiscordRpcService(client=mock_client, enabled=True)

    try:
        service.on_game_started(
            instance_name="Vanilla World",
            minecraft_version="1.21.1",
            loader_name="vanilla",
            start_timestamp=1700000000,
        )
        for _ in range(20):
            if mock_client.update_activity.called:
                break
            time.sleep(0.05)

        mock_client.update_activity.assert_called_once_with(
            details="Minecraft 1.21.1",
            state="Instance: Vanilla World",
            start_timestamp=1700000000,
            large_image="default",
            large_text="MCW Launcher — Vanilla World",
        )
    finally:
        service.shutdown()


def test_launcher_settings_discord_rpc_default(tmp_path: Path) -> None:
    settings_file = tmp_path / "launcher_settings.json"
    manager = LauncherSettingsManager(settings_file)
    settings = manager.load()
    assert settings["launch"]["discord_rpc_enabled"] is True


def test_facade_singleton_service() -> None:
    service1 = get_discord_rpc_service()
    service2 = get_discord_rpc_service()
    assert service1 is service2


def test_discord_client_id_default_and_override() -> None:
    from src.core.integrations.discord.discord_rpc import (
        DEFAULT_DISCORD_CLIENT_ID,
        get_discord_client_id,
    )

    assert DEFAULT_DISCORD_CLIENT_ID == "762726289341677668"
    assert get_discord_client_id() == "762726289341677668"
    assert get_discord_client_id("123456789012345678") == "123456789012345678"

    client = DiscordRpcClient()
    assert client.client_id == "762726289341677668"
    client.set_client_id("987654321098765432")
    assert client.client_id == "987654321098765432"

    service = DiscordRpcService(client=client, enabled=False)
    service.set_client_id("111222333444555666")
    assert client.client_id == "111222333444555666"

