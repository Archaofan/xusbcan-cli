"""MCP stdio 端到端测试：启动 xusbcan-mcp 子进程，验证 initialize + list_tools。

依赖 mcp 可选依赖；未安装时自动跳过（CI 的 dev extra 不含 mcp）。
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

pytest.importorskip("mcp")


async def _async_test():
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "xusbcan.mcp.server"],
        env=dict(os.environ),
        cwd=os.getcwd(),  # 项目根，让 ./xusbcan.toml 可被 load_config 找到
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            assert "send_frame" in names
            assert "receive_frame" in names
            assert "monitor" in names
            return names


def test_mcp_stdio_end_to_end():
    names = asyncio.run(_async_test())
    print("stdio 端到端工具数:", len(names))
    print("工具:", names)


if __name__ == "__main__":
    test_mcp_stdio_end_to_end()
