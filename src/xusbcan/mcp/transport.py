"""MCP 传输选择。不依赖 mcp 包，无该可选依赖时也能测试。"""

from __future__ import annotations


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
