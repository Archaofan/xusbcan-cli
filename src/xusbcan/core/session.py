"""会话管理：SessionManager + Session。

会话状态机只有 closed / open / error 三态；设备打开、通道初始化、句柄引用计数
只属于 backend（如 ZlgBus / ZlgDevicePool），绝不进入 Session——否则 core 会重新
长出厂商生命周期。

core 只面向 can.Bus 与领域模型；唯一接触适配层的地方是通过 registry（不 import
adapters.zlg）。
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import can

from ..adapters.registry import open_device
from ..models.device import DeviceSpec
from ..models.result import ErrorCode, Result

# 关闭时 join 的超时（秒）。取值 > zlg 无 ACK 发送阻塞的 ~3.5s（见 architecture §12.10），
# 保证能收回监听线程；收不回时该会话进入 error 并返回 CLOSE_TIMEOUT。
CLOSE_TIMEOUT_S = 5.0


class SessionState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    ERROR = "error"


def map_error(exc: BaseException) -> ErrorCode:
    """把 python-can 异常集中翻译成 ErrorCode（core 只翻译这一次，CLI/MCP 不各自翻译）。"""
    if isinstance(exc, can.CanInterfaceNotImplementedError):
        return ErrorCode.DEVICE_OPEN_FAILED
    if isinstance(exc, can.CanInitializationError):
        return ErrorCode.DEVICE_OPEN_FAILED
    if isinstance(exc, can.CanOperationError):
        return ErrorCode.DEVICE_NOT_OPEN
    if isinstance(exc, can.CanError):
        # 含 CanTimeoutError：超时本应在调用点按「成功超时」处理，逃逸到此属内部错误。
        return ErrorCode.INTERNAL_ERROR
    return ErrorCode.INTERNAL_ERROR


@dataclass
class Session:
    """一条已打开的会话（一路通道）。持有 can.Bus 与领域模型，不含厂商生命周期。"""

    name: str  # 配置别名，如 can0 / can1
    bus: can.BusABC
    spec: DeviceSpec
    state: SessionState = SessionState.OPEN
    receive_owner: str | None = None  # "monitor"（有界采集运行时占用）
    periodic: dict[str, Any] = field(default_factory=dict)  # name -> PeriodicTask
    monitor: Any | None = None  # 运行中的 Monitor
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    # ---- 接收所有者（core 内部，供 monitor.py / commands.py 使用）----

    def acquire_receive(self, owner: str) -> bool:
        """占用接收所有权；已被占用返回 False。"""
        with self._lock:
            if self.receive_owner is not None:
                return False
            self.receive_owner = owner
            return True

    def release_receive(self, owner: str) -> None:
        with self._lock:
            if self.receive_owner == owner:
                self.receive_owner = None

    # ---- 监听（core 内部）----

    def set_monitor(self, monitor: Any) -> None:
        with self._lock:
            self.monitor = monitor

    def clear_monitor(self, monitor: Any) -> None:
        with self._lock:
            if self.monitor is monitor:
                self.monitor = None

    # ---- 周期任务（core 内部）----

    def add_periodic(self, name: str, task: Any) -> bool:
        """登记一条周期任务；名字已存在返回 False。"""
        with self._lock:
            if name in self.periodic:
                return False
            self.periodic[name] = task
            return True

    def pop_periodic(self, name: str) -> Any:
        with self._lock:
            return self.periodic.pop(name, None)

    def snapshot_periodic(self) -> list:
        with self._lock:
            return list(self.periodic.values())

    def close(self) -> Result:
        """只做三步：停周期任务 → 停监听 → bus.shutdown()。

        设备句柄的引用归还由 backend 的 shutdown() 内部完成（最后一路才真正关设备）。
        """
        with self._lock:
            if self.state is SessionState.CLOSED:
                return Result.ok({"state": self.state.value})
            tasks = list(self.periodic.values())
            self.periodic.clear()
            monitor = self.monitor
            self.monitor = None

        # 1. 停周期任务（best-effort，不阻断 shutdown）
        for task in tasks:
            try:
                task.stop()
            except Exception:
                pass

        # 2. 停监听（先置停止标志再 join，带超时）
        if monitor is not None:
            monitor.stop()
            if not monitor.join(timeout=CLOSE_TIMEOUT_S):
                with self._lock:
                    self.state = SessionState.ERROR
                return Result.err(
                    ErrorCode.CLOSE_TIMEOUT,
                    f"关闭监听超时: {self.name}",
                    context={"alias": self.name},
                )

        # 3. shutdown
        try:
            self.bus.shutdown()
        except can.CanError as e:
            with self._lock:
                self.state = SessionState.ERROR
            return Result.err(map_error(e), f"关闭设备失败: {e}", detail=str(e))
        except Exception as e:
            with self._lock:
                self.state = SessionState.ERROR
            return Result.err(ErrorCode.INTERNAL_ERROR, f"关闭设备失败: {e}")

        with self._lock:
            self.receive_owner = None
            self.state = SessionState.CLOSED
        return Result.ok({"state": self.state.value})


def _default_opener(spec: DeviceSpec) -> Result:
    return open_device(spec)


class SessionManager:
    """按别名管理会话。opener 可注入（默认 registry.open_device），测试用假 BusABC 注入。"""

    def __init__(
        self,
        opener: Callable[[DeviceSpec], Any] | None = None,
        specs: dict[str, DeviceSpec] | None = None,
    ) -> None:
        self._opener = opener if opener is not None else _default_opener
        self._specs: dict[str, DeviceSpec] = dict(specs or {})
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()

    # ---- 配置 ----

    def register(self, alias: str, spec: DeviceSpec) -> None:
        with self._lock:
            self._specs[alias] = spec

    def get_spec(self, alias: str) -> DeviceSpec | None:
        return self._specs.get(alias)

    @property
    def specs(self) -> dict[str, DeviceSpec]:
        return dict(self._specs)

    @property
    def sessions(self) -> dict[str, Session]:
        return dict(self._sessions)

    def get(self, alias: str) -> Session | None:
        return self._sessions.get(alias)

    # ---- 打开 / 关闭 ----

    def _open_bus(self, spec: DeviceSpec) -> Result:
        r = self._opener(spec)
        if isinstance(r, Result):
            return r
        # 注入的假 BusABC 直接返回对象（不包 Result）
        return Result.ok(r)

    def open(self, alias: str) -> Result:
        with self._lock:
            existing = self._sessions.get(alias)
            if existing is not None and existing.state is SessionState.OPEN:
                return Result.ok({"state": existing.state.value, "reused": True})
            spec = self._specs.get(alias)
        if spec is None:
            return Result.err(ErrorCode.SESSION_NOT_FOUND, f"会话不存在: {alias}")
        result = self._open_bus(spec)  # 打开放在锁外，避免阻塞其它别名
        if result.status == "error":
            return result
        session = Session(name=alias, bus=result.data, spec=spec)
        with self._lock:
            existing = self._sessions.get(alias)
            if existing is not None and existing.state is SessionState.OPEN:
                session.close()  # 并发下已被打开，放弃本次、复用已有
                return Result.ok({"state": "open", "reused": True})
            self._sessions[alias] = session
        return Result.ok({"state": "open", "reused": False})

    def close(self, alias: str) -> Result:
        with self._lock:
            session = self._sessions.get(alias)
        if session is None:
            return Result.err(ErrorCode.SESSION_NOT_FOUND, f"会话不存在或未打开: {alias}")
        result = session.close()
        if result.status == "ok":
            with self._lock:
                if self._sessions.get(alias) is session:
                    self._sessions.pop(alias, None)
        # 失败时保留会话（state=error），该路上后续发送被拒绝
        return result

    def close_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for s in sessions:
            try:
                s.close()
            except Exception:
                pass

    # ---- 复用规则（一次性 vs 会话共用同一条路径）----

    def acquire(self, alias: str) -> tuple[Session | None, Result | None, bool]:
        """按别名取会话。返回 (session, error, reused)：

        - 已打开 → (session, None, True)：复用，调用方返回时**不得 shutdown**；
        - 未打开 → 一次性打开 (session, None, False)：调用方需 try/finally shutdown；
        - 失败   → (None, errorResult, False)。
        """
        with self._lock:
            session = self._sessions.get(alias)
            if session is not None:
                if session.state is SessionState.OPEN:
                    return session, None, True
                if session.state is SessionState.ERROR:
                    return None, Result.err(
                        ErrorCode.DEVICE_NOT_OPEN,
                        f"会话处于错误状态: {alias}",
                        context={"alias": alias},
                    ), False
        spec = self._specs.get(alias)
        if spec is None:
            return None, Result.err(ErrorCode.SESSION_NOT_FOUND, f"会话不存在: {alias}"), False
        result = self._open_bus(spec)
        if result.status == "error":
            return None, result, False
        session = Session(name=alias, bus=result.data, spec=spec)
        return session, None, False

    def release(self, session: Session | None, reused: bool) -> None:
        """释放 acquire 取得的会话。reused=True 时不动；否则 shutdown（一次性路径）。"""
        if session is None or reused:
            return
        try:
            session.close()
        except Exception:
            pass
