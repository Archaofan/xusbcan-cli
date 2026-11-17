"""周期发送：基于 can.Bus.send_periodic（软件层，跨后端通用）。

2E 的硬件定时发送（auto_send）只作为 backend 的 _send_periodic_internal 可选覆盖，
core 不出现厂商分支。

可选 ``duration_s``：到点由定时器自动 stop（供 MCP 等 Agent 路径使用，避免无限发送）。

停止语义：底层 ``task.stop()`` 失败时向上返回错误，并把任务重新登记到会话，
避免「报告已停止但硬件/软件周期仍可能在跑」。
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from ..models.frame import CanFrame
from ..models.result import ErrorCode, Result

# MCP / Agent 路径建议的硬上限（秒）。更长的台架任务请用本机常驻进程。
MAX_PERIODIC_DURATION_S = 300.0


@dataclass
class PeriodicTask:
    """会话内的一条周期发送任务。task 是 python-can 的 CyclicSendTaskABC。"""

    name: str
    frame: CanFrame
    period: float  # 秒
    task: Any  # can.broadcastmanager.CyclicSendTaskABC
    started_at: float = field(default_factory=time.time)
    duration_s: float | None = None
    _timer: threading.Timer | None = field(default=None, repr=False)

    def stop(self) -> None:
        """取消自动停止定时器并停止底层任务。底层异常向上抛出。"""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self.task.stop()

    def to_dict(self) -> dict:
        data = {
            "name": self.name,
            "arbitration_id": self.frame.arbitration_id,
            "data": self.frame.data.hex(),
            "is_extended": self.frame.is_extended,
            "is_fd": self.frame.is_fd,
            "period_ms": round(self.period * 1000.0, 3),
        }
        if self.duration_s is not None:
            data["duration_s"] = self.duration_s
        return data


def _finite_positive(name: str, value: float) -> Result | float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return Result.err(ErrorCode.INVALID_ARGUMENT, f"{name} 无效: {value!r}")
    if not math.isfinite(number):
        return Result.err(ErrorCode.INVALID_ARGUMENT, f"{name} 必须为有限数")
    if number <= 0:
        return Result.err(ErrorCode.INVALID_ARGUMENT, f"{name} 必须为正: {number}")
    return number


def _normalize_duration(duration_s: float | None) -> Result | float | None:
    """None 表示不自动停；否则须为正有限数且不超过 MAX_PERIODIC_DURATION_S。"""
    if duration_s is None:
        return None
    normalized = _finite_positive("duration_s", duration_s)
    if isinstance(normalized, Result):
        return normalized
    if normalized > MAX_PERIODIC_DURATION_S:
        return Result.err(
            ErrorCode.INVALID_ARGUMENT,
            f"duration_s 上限 {MAX_PERIODIC_DURATION_S:g} 秒；更长请用本机常驻进程",
            context={"max_duration_s": MAX_PERIODIC_DURATION_S},
        )
    return normalized


def _reregister(session, name: str, task: PeriodicTask) -> None:
    """停止失败时把任务放回会话，便于重试 stop。"""
    if not session.add_periodic(name, task):
        # 同名已被占用：尽力保留失败任务的可观测性（覆盖极少见竞态）
        existing = session.pop_periodic(name)
        if existing is not None:
            try:
                existing.stop()
            except Exception:
                pass
        session.add_periodic(name, task)


def start(
    session,
    name: str,
    frame: CanFrame,
    period: float,
    duration_s: float | None = None,
) -> Result:
    """在已打开的 session 上启动一条周期发送。session 由调用方保证已打开。

    ``duration_s`` 为 None 时不自动停止（CLI 自行 sleep 后 stop；剧本逐步 stop）。
    传入正数时到点自动移除并停止该任务；自动停止失败时会重新登记任务。
    """
    period_n = _finite_positive("period", period)
    if isinstance(period_n, Result):
        return period_n
    normalized = _normalize_duration(duration_s)
    if isinstance(normalized, Result):
        return normalized
    duration = normalized

    try:
        task = session.bus.send_periodic(frame.to_can_message(), period_n)
    except Exception as e:
        return Result.err(ErrorCode.INTERNAL_ERROR, f"启动周期发送失败: {e}")
    pt = PeriodicTask(
        name=name, frame=frame, period=period_n, task=task, duration_s=duration
    )
    if not session.add_periodic(name, pt):
        try:
            pt.stop()
        except Exception as e:
            return Result.err(
                ErrorCode.INTERNAL_ERROR,
                f"周期任务已存在且回滚停止失败: {name}: {e}",
                context={"alias": session.name, "name": name},
            )
        return Result.err(
            ErrorCode.INVALID_ARGUMENT,
            f"周期任务已存在: {name}",
            context={"alias": session.name, "name": name},
        )

    if duration is not None:

        def _expire() -> None:
            expired = session.pop_periodic(name)
            if expired is None:
                return
            try:
                expired.stop()
            except Exception:
                _reregister(session, name, expired)

        timer = threading.Timer(duration, _expire)
        timer.daemon = True
        pt._timer = timer
        timer.start()

    return Result.ok(pt.to_dict())


def stop(session, name: str) -> Result:
    """先停止底层任务，成功后再从会话移除；失败则重新登记并返回错误。"""
    task = session.pop_periodic(name)
    if task is None:
        return Result.err(ErrorCode.SESSION_NOT_FOUND, f"周期任务不存在: {name}")
    try:
        task.stop()
    except Exception as e:
        _reregister(session, name, task)
        return Result.err(
            ErrorCode.INTERNAL_ERROR,
            f"停止周期发送失败: {e}",
            context={"alias": session.name, "name": name},
        )
    return Result.ok({"name": name, "stopped": True})


def list_tasks(session) -> Result:
    return Result.ok({"tasks": [t.to_dict() for t in session.snapshot_periodic()]})
