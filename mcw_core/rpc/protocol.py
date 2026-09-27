from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from enum import Enum
import json
from pathlib import Path
from typing import Any


def to_json_compatible(value: Any) -> Any:
    """Recursively converts Python / MCWCore objects into pure JSON-serializable primitives."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): to_json_compatible(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_json_compatible(item) for item in value]
    if hasattr(value, "as_dict") and callable(value.as_dict):
        return to_json_compatible(value.as_dict())
    if is_dataclass(value) and not isinstance(value, type):
        return to_json_compatible(asdict(value))
    if hasattr(value, "__dict__"):
        return {
            str(k): to_json_compatible(v)
            for k, v in vars(value).items()
            if not str(k).startswith("_") and not callable(v)
        }
    return str(value)


@dataclass(frozen=True, slots=True)
class RpcError:
    code: int
    message: str
    data: Any = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            payload["data"] = to_json_compatible(self.data)
        return payload


@dataclass(frozen=True, slots=True)
class RpcRequest:
    method: str
    params: dict[str, Any] = field(default_factory=dict)
    id: str | int | None = 1
    jsonrpc: str = "2.0"

    @classmethod
    def from_raw(cls, raw: str | bytes | dict[str, Any]) -> "RpcRequest":
        data = json.loads(raw) if isinstance(raw, (str, bytes)) else dict(raw)
        if not isinstance(data, dict):
            raise ValueError("JSON-RPC payload must be an object.")
        method = str(data.get("method", "")).strip()
        if not method:
            raise ValueError("JSON-RPC request requires a non-empty 'method'.")
        params = data.get("params") or {}
        if not isinstance(params, dict):
            params = {"args": list(params) if isinstance(params, (list, tuple)) else [params]}
        return cls(
            method=method,
            params=params,
            id=data.get("id", 1),
            jsonrpc=str(data.get("jsonrpc", "2.0")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "jsonrpc": self.jsonrpc,
            "id": self.id,
            "method": self.method,
            "params": to_json_compatible(self.params),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class RpcResponse:
    id: str | int | None
    result: Any = None
    error: RpcError | None = None
    jsonrpc: str = "2.0"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            payload["error"] = self.error.to_dict()
        else:
            payload["result"] = to_json_compatible(self.result)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class RpcEvent:
    event: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="milliseconds"))
    jsonrpc: str = "2.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "jsonrpc": self.jsonrpc,
            "method": "core.event",
            "params": {
                "event": self.event,
                "data": to_json_compatible(self.data),
                "timestamp": self.timestamp,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)
