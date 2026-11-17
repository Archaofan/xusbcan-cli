"""MCP 服务器入口：FastMCP + 配置加载 + 常驻 SessionManager。"""

from __future__ import annotations

import json
import sys

from mcp.server.mcpserver import MCPServer

from ..config.loader import load_config
from ..core import SessionManager
from ..models.result import ErrorCode, Result
from .tools import register_tools

mcp = MCPServer("xusbcan")


def _build_manager(config_path: str | None) -> tuple[Result, SessionManager | None]:
    result = load_config(config_path)
    if result.status == "error":
        return result, None
    cfg = result.data
    manager = SessionManager()
    for entry in cfg.devices:
        manager.register(entry.name, entry.spec)
    return result, manager


def resolve_mcp_transport(server: dict) -> tuple[str, dict]:
    """stdio 或只绑定环回地址的 HTTP。配置里的非本机 host 直接拒绝。"""
    backend = str(server.get("backend", "stdio"))
    if backend == "stdio":
        return "stdio", {}
    if backend != "http":
        raise ValueError(f"不支持的 MCP 传输: {backend}")
    host = str(server.get("host", "127.0.0.1"))
    if host == "localhost":
        host = "127.0.0.1"
    if host not in ("127.0.0.1", "::1"):
        raise ValueError("MCP HTTP 只允许绑定 127.0.0.1")
    port = int(server.get("port", 8765))
    if not 1 <= port <= 65535:
        raise ValueError(f"非法端口: {port}")
    return "streamable-http", {"host": "127.0.0.1", "port": port}


def main(config_path: str | None = None) -> int:
    result, manager = _build_manager(config_path)
    if result.status == "error":
        print(json.dumps(result.to_dict(), ensure_ascii=False), file=sys.stderr)
        return 1
    assert manager is not None
    register_tools(mcp, manager)
    server_cfg = result.data.server if isinstance(result.data.server, dict) else {}
    try:
        transport, options = resolve_mcp_transport(server_cfg)
    except ValueError as e:
        err = Result.err(ErrorCode.CONFIG_ERROR, str(e))
        print(json.dumps(err.to_dict(), ensure_ascii=False), file=sys.stderr)
        return 1
    mcp.run(transport, **options)  # type: ignore[arg-type]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
