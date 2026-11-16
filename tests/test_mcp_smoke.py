"""MCP 工具冒烟测试：用 virtual 后端验证工具注册与调用（不依赖真实硬件）。"""

from __future__ import annotations

import asyncio

import can

from xusbcan.core import SessionManager
from xusbcan.mcp.tools import register_tools
from xusbcan.models import BitrateConfig, DeviceSpec, Result


def _make_manager():
    def opener(spec: DeviceSpec):
        return Result.ok(
            can.Bus(interface="virtual", channel=f"v{spec.channel}", bitrate=500000)
        )

    manager = SessionManager(opener=opener)
    manager.register(
        "can0",
        DeviceSpec(
            vendor="zlg",
            model="USBCAN-2E-U",
            channel=0,
            bitrate=BitrateConfig(nominal=500000),
        ),
    )
    return manager


async def _async_test():
    from mcp.server.mcpserver import MCPServer

    mcp = MCPServer("xusbcan-test")
    manager = _make_manager()
    register_tools(mcp, manager)

    tools = await mcp.list_tools()
    names = sorted(t.name for t in tools)
    print("已注册工具:", names)
    assert "send_frame" in names
    assert "receive_frame" in names
    assert "monitor" in names
    assert "periodic_start" in names

    result = await mcp.call_tool("list_devices", {})
    print("call_tool(list_devices) 结果类型:", type(result).__name__)
    # CallToolResult.content 是结构化内容列表
    content = result.content if hasattr(result, "content") else None
    print("content:", content)
    return names


def main():
    try:
        import mcp.server.mcpserver  # noqa: F401
    except ImportError:
        print("mcp 未安装，跳过")
        return
    names = asyncio.run(_async_test())
    print(f"MCP 工具冒烟 OK（{len(names)} 个工具）")


if __name__ == "__main__":
    main()
