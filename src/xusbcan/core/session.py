"""会话管理：SessionManager + Session。

会话状态机只有 closed / open / error 三态；设备打开、通道初始化、句柄引用计数
只属于 backend（如 ZlgBus / ZlgDevicePool），绝不进入 Session——否则 core 会重新
长出厂商生命周期。

core 只面向 can.Bus 与领域模型；唯一接触适配层的地方是通过 registry（不 import
adapters.zlg）。
"""

from __future__ import annotations

import threading
import time
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


def map_error(
    exc: BaseException,
    *,
    default_can: ErrorCode = ErrorCode.INTERNAL_ERROR,
) -> ErrorCode:
    """把异常集中翻译成 ErrorCode（core 只翻译这一次，CLI/MCP 不各自翻译）。

    适配器异常可挂 ``code``（``ErrorCode`` 或同名字符串）；有则优先采用。
    """
    attached = getattr(exc, "code", None)
    if isinstance(attached, ErrorCode):
        return attached
    if isinstance(attached, str):
        try:
            return ErrorCode(attached)
        except ValueError:
            pass
    if isinstance(exc, can.CanInterfaceNotImplementedError):
        return ErrorCode.DEVICE_OPEN_FAILED
    if isinstance(exc, can.CanInitializationError):
        return ErrorCode.DEVICE_OPEN_FAILED
    if isinstance(exc, can.CanError):
        # 含 CanOperationError / CanTimeoutError：调用方用 default_can 区分发送/接收/关闭等语义。
        return default_can
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
    _periodic_reserved: set[str] = field(default_factory=set, repr=False)
    _inflight_periodic_ops: int = field(default=0, repr=False)
    _closing: bool = field(default=False, repr=False)
    monitor: Any | None = None  # 运行中的 Monitor
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def _accepts_periodic(self) -> bool:
        return self.state is SessionState.OPEN and not self._closing

    def begin_periodic_op(self) -> bool:
        """登记一笔在途周期操作（启动回滚 / stop / Timer expire）。

        CLOSED 拒绝；``_closing`` 期间仍允许，以便关闭等待这些操作完成。
        """
        with self._lock:
            if self.state is SessionState.CLOSED:
                return False
            self._inflight_periodic_ops += 1
            return True

    def end_periodic_op(self) -> None:
        with self._lock:
            if self._inflight_periodic_ops > 0:
                self._inflight_periodic_ops -= 1

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
            if not self._accepts_periodic():
                return False
            if name in self.periodic or name in self._periodic_reserved:
                return False
            self.periodic[name] = task
            return True

    def reserve_periodic(self, name: str, *, max_tasks: int) -> Result:
        """原子预留名称与容量（启动底层任务前调用）。非 OPEN / 正在关闭时拒绝。"""
        with self._lock:
            if not self._accepts_periodic():
                return Result.err(
                    ErrorCode.DEVICE_NOT_OPEN,
                    f"会话不可启动周期任务: {self.name}",
                    context={"alias": self.name, "state": self.state.value},
                )
            if name in self.periodic or name in self._periodic_reserved:
                return Result.err(
                    ErrorCode.INVALID_ARGUMENT,
                    f"周期任务已存在: {name}",
                    context={"alias": self.name, "name": name},
                )
            used = len(self.periodic) + len(self._periodic_reserved)
            if used >= max_tasks:
                return Result.err(
                    ErrorCode.INVALID_ARGUMENT,
                    f"周期任务数已达上限 {max_tasks}",
                    context={"alias": self.name, "max_tasks": max_tasks},
                )
            self._periodic_reserved.add(name)
            return Result.ok({"name": name, "reserved": True})

    def commit_periodic(self, name: str, task: Any) -> bool:
        """把预留位换成真实任务。

        关闭中或非 OPEN 时返回 False 且**保留预留**，由调用方完成底层回滚后再
        ``cancel_periodic_reserve``，避免 close 在回滚完成前看到预留已空。
        """
        with self._lock:
            if name not in self._periodic_reserved:
                return False
            if not self._accepts_periodic():
                return False
            self._periodic_reserved.discard(name)
            self.periodic[name] = task
            return True

    def cancel_periodic_reserve(self, name: str) -> None:
        with self._lock:
            self._periodic_reserved.discard(name)

    def restore_periodic(self, name: str, task: Any) -> str:
        """停止失败后放回任务。冲突时用唯一后缀登记，不覆盖、不吞掉另一个任务。"""
        with self._lock:
            if self.state is SessionState.CLOSED:
                # 不应在成功关闭后登记；调用方须保证在途操作在 close 成功前结束
                return name
            existing = self.periodic.get(name)
            if existing is None or existing is task:
                self.periodic[name] = task
                self._periodic_reserved.discard(name)
                return name
            alt = f"{name}__stop_failed_{id(task)}"
            self.periodic[alt] = task
            return alt

    def pop_periodic(self, name: str) -> Any:
        with self._lock:
            return self.periodic.pop(name, None)

    def snapshot_periodic(self) -> list:
        with self._lock:
            return list(self.periodic.values())

    def _wait_periodic_quiescent(self, deadline: float) -> Result | None:
        """等待预留与在途周期操作均结束；超时则 ERROR。"""
        while True:
            with self._lock:
                if not self._periodic_reserved and self._inflight_periodic_ops == 0:
                    return None
                pending = {
                    "reserved": sorted(self._periodic_reserved),
                    "inflight": self._inflight_periodic_ops,
                }
            if time.monotonic() >= deadline:
                with self._lock:
                    self.state = SessionState.ERROR
                return Result.err(
                    ErrorCode.CLOSE_TIMEOUT,
                    f"关闭时周期任务操作未完成: {self.name}",
                    context={"alias": self.name, **pending},
                )
            time.sleep(0.01)

    def close(self) -> Result:
        """停周期任务 → 停监听 → bus.shutdown()。

        设置 ``_closing`` 后等待预留与在途 stop/回滚结束，再停已登记任务；
        循环直到登记表为空，避免 Timer/stop 与 close 交错漏停。
        周期停止失败时重新登记并进入 error，不继续 shutdown。
        """
        with self._lock:
            if self.state is SessionState.CLOSED:
                return Result.ok({"state": self.state.value})
            self._closing = True

        deadline = time.monotonic() + CLOSE_TIMEOUT_S

        while True:
            quiet = self._wait_periodic_quiescent(deadline)
            if quiet is not None:
                return quiet

            with self._lock:
                names = list(self.periodic.keys())

            if not names:
                break

            stop_failures: list[str] = []
            for name in names:
                if not self.begin_periodic_op():
                    stop_failures.append(f"{name}: session closed during stop")
                    continue
                try:
                    task = self.pop_periodic(name)
                    if task is None:
                        continue
                    try:
                        task.stop()
                    except Exception as e:
                        restored = self.restore_periodic(name, task)
                        stop_failures.append(f"{restored}: {e}")
                finally:
                    self.end_periodic_op()

            if stop_failures:
                with self._lock:
                    self.state = SessionState.ERROR
                return Result.err(
                    ErrorCode.INTERNAL_ERROR,
                    f"关闭前停止周期发送失败: {'; '.join(stop_failures)}",
                    context={
                        "alias": self.name,
                        "failed_tasks": [
                            item.split(":", 1)[0] for item in stop_failures
                        ],
                    },
                    detail="; ".join(stop_failures),
                )
            # 成功停完一轮后继续循环，吞掉期间新登记或晚到的 expire

        # 停监听（成功 join 后再摘掉会话上的引用）
        with self._lock:
            monitor = self.monitor
        if monitor is not None:
            monitor.stop()
            if not monitor.join(timeout=max(0.0, deadline - time.monotonic())):
                with self._lock:
                    self.state = SessionState.ERROR
                return Result.err(
                    ErrorCode.CLOSE_TIMEOUT,
                    f"关闭监听超时: {self.name}",
                    context={"alias": self.name},
                )
            with self._lock:
                if self.monitor is monitor:
                    self.monitor = None

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
            self.monitor = None
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
            if existing is not None:
                if existing.state is SessionState.ERROR:
                    return Result.err(
                        ErrorCode.DEVICE_NOT_OPEN,
                        f"会话处于错误状态，须先清理周期任务并关闭后再打开: {alias}",
                        context={"alias": alias, "state": existing.state.value},
                    )
                if existing.state is SessionState.OPEN:
                    if existing._closing:
                        return Result.err(
                            ErrorCode.DEVICE_NOT_OPEN,
                            f"会话正在关闭: {alias}",
                            context={"alias": alias, "state": existing.state.value},
                        )
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
            if existing is not None:
                if existing.state is SessionState.ERROR:
                    session.close()
                    return Result.err(
                        ErrorCode.DEVICE_NOT_OPEN,
                        f"会话处于错误状态，须先清理周期任务并关闭后再打开: {alias}",
                        context={"alias": alias, "state": existing.state.value},
                    )
                if existing.state is SessionState.OPEN:
                    session.close()
                    if existing._closing:
                        return Result.err(
                            ErrorCode.DEVICE_NOT_OPEN,
                            f"会话正在关闭: {alias}",
                            context={"alias": alias, "state": existing.state.value},
                        )
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

    def close_all(self) -> list[Result]:
        """关闭全部会话：仅移除成功关闭的；失败会话保留供重试。

        返回每个会话一次 ``close()`` 的 Result（顺序与关闭时快照一致）。
        """
        with self._lock:
            items = list(self._sessions.items())
        results: list[Result] = []
        for alias, session in items:
            try:
                result = session.close()
            except Exception as e:  # noqa: BLE001 — 汇总为 Result，避免丢失会话
                with self._lock:
                    session.state = SessionState.ERROR
                result = Result.err(
                    ErrorCode.INTERNAL_ERROR,
                    f"关闭设备异常: {e}",
                    context={"alias": alias},
                )
            results.append(result)
            if result.status == "ok":
                with self._lock:
                    if self._sessions.get(alias) is session:
                        self._sessions.pop(alias, None)
        return results

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
                if session.state is SessionState.ERROR:
                    return None, Result.err(
                        ErrorCode.DEVICE_NOT_OPEN,
                        f"会话处于错误状态: {alias}",
                        context={"alias": alias},
                    ), False
                if session.state is SessionState.OPEN:
                    if session._closing:
                        return None, Result.err(
                            ErrorCode.DEVICE_NOT_OPEN,
                            f"会话正在关闭: {alias}",
                            context={"alias": alias},
                        ), False
                    return session, None, True
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
