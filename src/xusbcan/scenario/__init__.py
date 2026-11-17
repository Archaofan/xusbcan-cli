"""毫秒级报文剧本：在已打开的 SessionManager 上按步骤编排收发与滤波。

不含厂商概念；长编排请用本模块或 MCP 会话，不要循环 CLI 开关设备。
"""

from .runner import run_scenario

__all__ = ["run_scenario"]
