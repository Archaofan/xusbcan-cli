"""MCP 工具定义：薄封装 core，只做「参数解析 → 调 core → 序列化 Result」。"""

from __future__ import annotations

import json

from .. import core
from ..models.frame import CanFrame
from ..models.result import ErrorCode, Result


def _json(result: Result) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False)


def register_tools(mcp, manager: core.SessionManager) -> None:
    """把 core 命令注册为 MCP 工具。工具签名是统一语义，不含厂商概念。"""

    @mcp.tool()
    def list_devices() -> str:
        """列出配置中的所有设备：别名、通道、能力、是否已打开。返回 JSON。"""
        return _json(core.list_devices(manager))

    @mcp.tool()
    def send_frame(device: str, arbitration_id: int, data: str, is_extended: bool = False) -> str:
        """发送一帧 CAN 报文。device 为别名；data 为十六进制字节串（如 "01 02 03"）。返回 JSON。"""
        try:
            frame = CanFrame(
                arbitration_id=arbitration_id,
                data=core.parse_hex(data),
                is_extended=is_extended,
            )
        except ValueError as e:
            return _json(Result.err(ErrorCode.INVALID_ARGUMENT, str(e)))
        return _json(core.send(manager, device, frame))

    @mcp.tool()
    def receive_frame(device: str, timeout: float = 1.0) -> str:
        """接收一帧 CAN 报文。timeout 为超时（秒）；超时返回 status=ok 且 frame=null。"""
        return _json(core.receive(manager, device, timeout))

    @mcp.tool()
    def monitor(device: str, duration_s: float = 1.0, max_frames: int = 500) -> str:
        """有界监听一段时间。duration_s 上限 30 秒；返回 data.frames[] + count + truncated。"""
        return _json(core.monitor(manager, device, duration_s, max_frames))

    @mcp.tool()
    def get_status(device: str) -> str:
        """查询会话/设备状态：state、features、receive_owner。返回结构化 JSON。"""
        return _json(core.status(manager, device))

    @mcp.tool()
    def open_device(device: str) -> str:
        """打开设备会话（常驻进程持有，后续 send/receive 复用该会话）。返回结构化 JSON。"""
        return _json(core.open_session(manager, device))

    @mcp.tool()
    def close_device(device: str) -> str:
        """关闭设备会话，释放资源。返回结构化 JSON。"""
        return _json(core.close_session(manager, device))

    @mcp.tool()
    def periodic_start(
        device: str,
        name: str,
        arbitration_id: int,
        data: str,
        period_s: float,
        is_extended: bool = False,
    ) -> str:
        """启动周期发送。name 为任务名；period_s 为周期（秒）。
        支持硬件定时发送的适配器会走硬件周期，期间普通 send_frame 会失败，需先 periodic_stop。
        """
        try:
            frame = CanFrame(
                arbitration_id=arbitration_id,
                data=core.parse_hex(data),
                is_extended=is_extended,
            )
        except ValueError as e:
            return _json(Result.err(ErrorCode.INVALID_ARGUMENT, str(e)))
        return _json(core.periodic_start(manager, device, name, frame, period_s))

    @mcp.tool()
    def periodic_stop(device: str, name: str) -> str:
        """停止并移除一条周期发送任务。返回结构化 JSON。"""
        return _json(core.periodic_stop(manager, device, name))

    @mcp.tool()
    def periodic_list(device: str) -> str:
        """列出当前会话的所有周期发送任务。返回结构化 JSON。"""
        return _json(core.periodic_list(manager, device))

    @mcp.tool()
    def set_frame_filter(
        device: str, start_id: int, end_id: int, is_extended: bool = False
    ) -> str:
        """用一条 ID 范围替换接收滤波（会话须已 open_device）。空表不是全收。"""
        return _json(core.set_frame_filter(manager, device, start_id, end_id, is_extended))

    @mcp.tool()
    def accept_all_frames(device: str) -> str:
        """恢复接收全部帧。设置过滤波后若要重新全收，调用本工具而不是只清空滤波表。"""
        return _json(core.accept_all_frames(manager, device))
