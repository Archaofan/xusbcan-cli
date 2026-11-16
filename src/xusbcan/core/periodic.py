"""周期发送：基于 can.Bus.send_periodic（软件层，跨后端通用）。

2E 的硬件定时发送（auto_send）只作为 backend 的 _send_periodic_internal 可选覆盖，
core 不出现厂商分支。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ..models.frame import CanFrame
from ..models.result import ErrorCode, Result


@dataclass
class PeriodicTask:
    """会话内的一条周期发送任务。task 是 python-can 的 CyclicSendTaskABC。"""

    name: str
    frame: CanFrame
    period: float  # 秒
    task: Any  # can.broadcastmanager.CyclicSendTaskABC
    started_at: float = field(default_factory=time.time)

    def stop(self) -> None:
        try:
            self.task.stop()
        except Exception:
            pass

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "arbitration_id": self.frame.arbitration_id,
            "data": self.frame.data.hex(),
            "is_extended": self.frame.is_extended,
            "is_fd": self.frame.is_fd,
            "period_ms": round(self.period * 1000.0, 3),
        }


def start(session, name: str, frame: CanFrame, period: float) -> Result:
    """在已打开的 session 上启动一条周期发送。session 由调用方保证已打开。"""
    if period <= 0:
        return Result.err(ErrorCode.INVALID_ARGUMENT, f"周期必须为正: {period}")
    try:
        task = session.bus.send_periodic(frame.to_can_message(), period)
    except Exception as e:
        return Result.err(ErrorCode.INTERNAL_ERROR, f"启动周期发送失败: {e}")
    pt = PeriodicTask(name=name, frame=frame, period=period, task=task)
    if not session.add_periodic(name, pt):
        pt.stop()  # 名字冲突：回滚刚启动的任务
        return Result.err(
            ErrorCode.INVALID_ARGUMENT,
            f"周期任务已存在: {name}",
            context={"alias": session.name, "name": name},
        )
    return Result.ok(pt.to_dict())


def stop(session, name: str) -> Result:
    task = session.pop_periodic(name)
    if task is None:
        return Result.err(ErrorCode.SESSION_NOT_FOUND, f"周期任务不存在: {name}")
    task.stop()
    return Result.ok({"name": name, "stopped": True})


def list_tasks(session) -> Result:
    return Result.ok({"tasks": [t.to_dict() for t in session.snapshot_periodic()]})
