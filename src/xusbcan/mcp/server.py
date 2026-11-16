"""MCP 服务器入口：FastMCP + 配置加载 + 常驻 SessionManager。"""

from __future__ import annotations

import json
import sys

from mcp.server.mcpserver import MCPServer

from ..config.loader import load_config
from ..core import SessionManager
from ..models.result import Result
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


def main(config_path: str | None = None) -> int:
    result, manager = _build_manager(config_path)
    if result.status == "error":
        print(json.dumps(result.to_dict(), ensure_ascii=False), file=sys.stderr)
        return 1
    assert manager is not None
    register_tools(mcp, manager)
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
