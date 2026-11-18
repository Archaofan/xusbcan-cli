"""监听（有界采集）。

MCP 形态：有界采集，duration_s（默认 1、上限 30）+ max_frames（默认 500），
返回普通 Result，帧在 data.frames，带 count / truncated。运行期间 session 标记
接收所有者，receive_frame 返回 MONITOR_ACTIVE。常驻监听用 receive_frame 轮询。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

import can

from ..models.frame import CanFrame
from ..models.result import ErrorCode, Result
from .session import CLOSE_TIMEOUT_S, map_error

DEFAULT_DURATION_S = 1.0
MAX_DURATION_S = 30.0
DEFAULT_MAX_FRAMES = 500
# 采集循环的轮询步长：用小步长让 stop()/close() 能及时收回线程，
# 而不是整段 duration 阻塞在某一次 recv 里。
POLL_INTERVAL_S = 0.1


@dataclass
class Monitor:
    """有界采集器。在守护线程里跑；session.monitor 引用它，stop() 置位后 join()。"""

    name: str  # 会话别名
    bus: Any  # can.BusABC
    duration_s: float
    max_frames: int
    frames: list[CanFrame] = field(default_factory=list)
    truncated: bool = False
    error: BaseException | None = None
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name=f"xusbcan-monitor-{self.name}", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def join(self, timeout: float | None = None) -> bool:
        """等待采集线程结束；返回是否已结束（False = join 超时）。"""
        if self._thread is None:
            return True
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _run(self) -> None:
        deadline = time.monotonic() + self.duration_s
        while not self._stop.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            timeout = min(remaining, POLL_INTERVAL_S)
            try:
                msg = self.bus.recv(timeout=timeout)
            except can.CanError as e:
                self.error = e
                break
            if msg is None:
                continue  # 到点或步长内无帧，循环重算 deadline
            frame = CanFrame.from_can_message(msg)
            with self._lock:
                if len(self.frames) < self.max_frames:
                    self.frames.append(frame)
                else:
                    # 超过 max_frames：丢弃后续并停止采集
                    self.truncated = True
                    self._stop.set()
                    break

    def _result_data(self) -> dict:
        with self._lock:
            frames = list(self.frames)
        return {
            "frames": [f.to_dict() for f in frames],
            "count": len(frames),
            "truncated": self.truncated,
        }

    def to_result(self) -> Result:
        if self.error is not None:
            return Result.err(
                map_error(self.error),
                f"监听失败: {self.error}",
                detail=str(self.error),
            )
        return Result.ok(self._result_data())


def _normalize_duration(duration_s: float | None) -> float | None:
    if duration_s is None:
        return DEFAULT_DURATION_S
    if duration_s < 0:
        return None
    return min(float(duration_s), MAX_DURATION_S)


def _normalize_max_frames(max_frames: int | None) -> int | None:
    if max_frames is None:
        return DEFAULT_MAX_FRAMES
    if max_frames <= 0:
        return None
    return max_frames


def capture_bounded(session, duration_s: float | None, max_frames: int | None) -> Result:
    """有界采集（MCP / 一次性共用）。占用接收所有者，采集完返回 Result。"""
    d = _normalize_duration(duration_s)
    if d is None:
        return Result.err(ErrorCode.INVALID_ARGUMENT, f"duration_s 不能为负: {duration_s}")
    m = _normalize_max_frames(max_frames)
    if m is None:
        return Result.err(ErrorCode.INVALID_ARGUMENT, f"max_frames 必须为正: {max_frames}")

    if not session.acquire_receive("monitor"):
        return Result.err(
            ErrorCode.MONITOR_ACTIVE,
            "监听/采集已在进行",
            context={"alias": session.name},
        )

    monitor = Monitor(name=session.name, bus=session.bus, duration_s=d, max_frames=m)
    session.set_monitor(monitor)
    try:
        monitor.start()
        # 多给一点余量，避免与 close 的 join 超时误判
        monitor.join(timeout=d + CLOSE_TIMEOUT_S)
        return monitor.to_result()
    finally:
        session.clear_monitor(monitor)
        session.release_receive("monitor")


def start_monitor(
    session, duration_s: float | None = None, max_frames: int | None = None
) -> Result:
    """后台启动监听（会话形态，不阻塞）。运行期间 receive_frame 返回 MONITOR_ACTIVE。"""
    d = _normalize_duration(duration_s)
    if d is None:
        return Result.err(ErrorCode.INVALID_ARGUMENT, f"duration_s 不能为负: {duration_s}")
    m = _normalize_max_frames(max_frames)
    if m is None:
        return Result.err(ErrorCode.INVALID_ARGUMENT, f"max_frames 必须为正: {max_frames}")

    if not session.acquire_receive("monitor"):
        return Result.err(
            ErrorCode.MONITOR_ACTIVE,
            "监听/采集已在进行",
            context={"alias": session.name},
        )
    monitor = Monitor(name=session.name, bus=session.bus, duration_s=d, max_frames=m)
    session.set_monitor(monitor)
    monitor.start()
    return Result.ok({"monitor": session.name, "started": True})


def stop_monitor(session) -> Result:
    """停止监听。join 超时则保留 Monitor 引用与接收所有权，返回 CLOSE_TIMEOUT。"""
    monitor = session.monitor
    if monitor is None:
        return Result.err(ErrorCode.SESSION_NOT_FOUND, "没有正在运行的监听")
    monitor.stop()
    if not monitor.join(timeout=CLOSE_TIMEOUT_S):
        return Result.err(
            ErrorCode.CLOSE_TIMEOUT,
            f"停止监听超时: {session.name}",
            context={"alias": session.name},
        )
    session.clear_monitor(monitor)
    session.release_receive("monitor")
    return monitor.to_result()
