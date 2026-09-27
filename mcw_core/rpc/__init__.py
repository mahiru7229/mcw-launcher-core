"""Headless JSON-RPC 2.0 (Stdio Sidecar & Local HTTP/SSE) interface for MCW Core v1.8.0."""

from mcw_core.rpc.client import CoreRpcClient, CoreRpcError
from mcw_core.rpc.dispatcher import CoreRpcDispatcher
from mcw_core.rpc.http_server import HttpRpcServer
from mcw_core.rpc.protocol import RpcError, RpcEvent, RpcRequest, RpcResponse, to_json_compatible
from mcw_core.rpc.stdio_server import StdioRpcServer

__all__ = [
    "CoreRpcClient",
    "CoreRpcDispatcher",
    "CoreRpcError",
    "HttpRpcServer",
    "RpcError",
    "RpcEvent",
    "RpcRequest",
    "RpcResponse",
    "StdioRpcServer",
    "to_json_compatible",
]
