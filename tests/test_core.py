"""core 层单元测试：会话管理、复用规则、命令处理器（virtual 后端 + 假适配器）。"""

from __future__ import annotations

import time

import can
import pytest

from xusbcan.core import (
    SessionManager,
    list_devices,
    periodic_list,
    periodic_start,
    periodic_stop,
    receive,
    send,
    status,
    transmit,
)
from xusbcan.models import BitrateConfig, CanFrame, DeviceSpec, Result

_active_managers: list[SessionManager] = []


@pytest.fixture(autouse=True)
def _cleanup_managers():
    """测试结束统一 close_all，避免 virtual bus 未 shutdown 的警告。"""
    _active_managers.clear()
    yield
    for m in _active_managers:
        m.close_all()
    _active_managers.clear()


def _virtual_manager() -> SessionManager:
    def opener(spec: DeviceSpec):
        return Result.ok(
            can.Bus(interface="virtual", channel=f"v{spec.channel}", bitrate=500_000)
        )

    mgr = SessionManager(opener=opener)
    mgr.register(
        "can0",
        DeviceSpec(
            vendor="zlg",
            model="USBCAN-2E-U",
            channel=0,
            bitrate=BitrateConfig(nominal=500_000),
        ),
    )
    _active_managers.append(mgr)
    return mgr


def test_open_close_lifecycle():
    mgr = _virtual_manager()
    r = mgr.open("can0")
    assert r.status == "ok"
    assert mgr.get("can0").state.value == "open"
    r = mgr.close("can0")
    assert r.status == "ok"
    assert mgr.get("can0") is None


def test_send_reuses_open_session():
    """已打开 → 复用不 shutdown（§4.4 复用规则）。"""
    mgr = _virtual_manager()
    mgr.open("can0")
    r = send(mgr, "can0", CanFrame(arbitration_id=0x123, data=b"\x01"))
    assert r.status == "ok"
    assert mgr.get("can0") is not None  # 会话仍 open


def test_send_one_off_leaves_no_residual():
    """未打开 → 一次性 try/finally 关闭，不残留会话。"""
    mgr = _virtual_manager()
    r = send(mgr, "can0", CanFrame(arbitration_id=0x123, data=b"\x01"))
    assert r.status == "ok"
    assert mgr.get("can0") is None


def test_receive_timeout_is_success():
    mgr = _virtual_manager()
    r = receive(mgr, "can0", timeout=0.1)
    assert r.status == "ok"
    assert r.data["frame"] is None
    assert r.data["reason"] == "timeout"


def test_list_and_status_schema():
    mgr = _virtual_manager()
    r = list_devices(mgr)
    d = r.data["devices"][0]
    assert d["name"] == "can0"
    assert d["channel"] == 0
    assert "opened" in d and "features" in d

    r = status(mgr, "can0")
    assert set(r.data) >= {"state", "features", "receive_owner"}


def test_periodic_lifecycle():
    mgr = _virtual_manager()
    mgr.open("can0")
    f = CanFrame(arbitration_id=0x123, data=b"\x01")
    r = periodic_start(mgr, "can0", "p1", f, 0.1)
    assert r.status == "ok"
    assert len(periodic_list(mgr, "can0").data["tasks"]) == 1
    assert periodic_stop(mgr, "can0", "p1").status == "ok"
    assert len(periodic_list(mgr, "can0").data["tasks"]) == 0


def test_periodic_duration_auto_stops():
    from xusbcan.core.periodic import MAX_PERIODIC_DURATION_S

    mgr = _virtual_manager()
    mgr.open("can0")
    f = CanFrame(arbitration_id=0x123, data=b"\x01")
    r = periodic_start(mgr, "can0", "p1", f, 0.05, duration_s=0.2)
    assert r.status == "ok"
    assert r.data["duration_s"] == 0.2
    assert len(periodic_list(mgr, "can0").data["tasks"]) == 1
    time.sleep(0.45)
    assert len(periodic_list(mgr, "can0").data["tasks"]) == 0

    over = periodic_start(
        mgr, "can0", "p2", f, 0.1, duration_s=MAX_PERIODIC_DURATION_S + 1
    )
    assert over.status == "error"
    assert over.error is not None
    assert over.error.code == "INVALID_ARGUMENT"


def test_periodic_rejects_nonfinite_period():
    mgr = _virtual_manager()
    mgr.open("can0")
    f = CanFrame(arbitration_id=0x123, data=b"\x01")
    bad = periodic_start(mgr, "can0", "p1", f, float("nan"))
    assert bad.status == "error"
    assert bad.error is not None
    assert bad.error.code == "INVALID_ARGUMENT"


def test_periodic_stop_failure_keeps_registration():
    mgr = _virtual_manager()
    mgr.open("can0")
    f = CanFrame(arbitration_id=0x123, data=b"\x01")
    assert periodic_start(mgr, "can0", "p1", f, 0.1).status == "ok"
    session = mgr.get("can0")
    assert session is not None
    pt = session.pop_periodic("p1")
    assert pt is not None
    real_task = pt.task

    class _BoomStop:
        def stop(self) -> None:
            raise RuntimeError("hw stop fail")

    pt.task = _BoomStop()
    assert session.add_periodic("p1", pt)
    failed = periodic_stop(mgr, "can0", "p1")
    assert failed.status == "error"
    assert failed.error is not None
    assert "停止周期发送失败" in failed.error.message
    assert len(periodic_list(mgr, "can0").data["tasks"]) == 1

    pt.task = real_task
    assert periodic_stop(mgr, "can0", "p1").status == "ok"
    assert periodic_list(mgr, "can0").data["tasks"] == []


def test_session_close_periodic_stop_failure_returns_error():
    """close_device / Session.close 不得吞掉 stop 异常并报成功。"""
    from xusbcan.core.session import SessionState

    mgr = _virtual_manager()
    mgr.open("can0")
    f = CanFrame(arbitration_id=0x123, data=b"\x01")
    assert periodic_start(mgr, "can0", "p1", f, 0.1).status == "ok"
    session = mgr.get("can0")
    assert session is not None
    pt = session.pop_periodic("p1")
    assert pt is not None
    real_task = pt.task

    class _BoomStop:
        def stop(self) -> None:
            raise RuntimeError("close stop fail")

    pt.task = _BoomStop()
    assert session.add_periodic("p1", pt)

    closed = mgr.close("can0")
    assert closed.status == "error"
    assert closed.error is not None
    assert "停止周期发送失败" in closed.error.message
    assert session.state is SessionState.ERROR
    assert mgr.get("can0") is session
    assert len(periodic_list(mgr, "can0").data["tasks"]) == 1

    pt.task = real_task
    assert periodic_stop(mgr, "can0", "p1").status == "ok"
    assert mgr.close("can0").status == "ok"


def test_periodic_rejects_period_below_minimum_and_task_cap():
    from xusbcan.core.periodic import MAX_PERIODIC_TASKS, MIN_PERIODIC_PERIOD_S

    mgr = _virtual_manager()
    mgr.open("can0")
    f = CanFrame(arbitration_id=0x123, data=b"\x01")
    too_small = periodic_start(mgr, "can0", "p0", f, MIN_PERIODIC_PERIOD_S / 10)
    assert too_small.status == "error"
    assert too_small.error is not None
    assert too_small.error.code == "INVALID_ARGUMENT"

    for i in range(MAX_PERIODIC_TASKS):
        assert periodic_start(mgr, "can0", f"t{i}", f, 0.1).status == "ok"
    over = periodic_start(mgr, "can0", "overflow", f, 0.1)
    assert over.status == "error"
    assert over.error is not None
    assert "上限" in over.error.message


def test_close_all_keeps_failed_sessions():
    from xusbcan.core.session import SessionState

    mgr = _virtual_manager()
    mgr.open("can0")
    f = CanFrame(arbitration_id=0x123, data=b"\x01")
    assert periodic_start(mgr, "can0", "p1", f, 0.1).status == "ok"
    session = mgr.get("can0")
    assert session is not None
    pt = session.pop_periodic("p1")
    assert pt is not None
    real = pt.task

    class _Boom:
        def stop(self) -> None:
            raise RuntimeError("close_all boom")

    pt.task = _Boom()
    session.add_periodic("p1", pt)
    results = mgr.close_all()
    assert len(results) == 1
    assert results[0].status == "error"
    assert mgr.get("can0") is session
    assert session.state is SessionState.ERROR
    pt.task = real
    assert periodic_stop(mgr, "can0", "p1").status == "ok"
    assert mgr.close("can0").status == "ok"


def test_session_close_keeps_monitor_when_periodic_stop_fails():
    from xusbcan.core.monitor import Monitor
    from xusbcan.core.session import SessionState

    mgr = _virtual_manager()
    mgr.open("can0")
    session = mgr.get("can0")
    assert session is not None
    monitor = Monitor(name="can0", bus=session.bus, duration_s=30.0, max_frames=10)
    monitor.start()
    session.set_monitor(monitor)
    session.acquire_receive("monitor")
    f = CanFrame(arbitration_id=0x123, data=b"\x01")
    assert periodic_start(mgr, "can0", "p1", f, 0.1).status == "ok"
    pt = session.pop_periodic("p1")
    assert pt is not None
    real = pt.task

    class _Boom:
        def stop(self) -> None:
            raise RuntimeError("monitor+periodic")

    pt.task = _Boom()
    session.add_periodic("p1", pt)
    closed = session.close()
    assert closed.status == "error"
    assert session.monitor is monitor
    assert session.state is SessionState.ERROR
    pt.task = real
    assert periodic_stop(mgr, "can0", "p1").status == "ok"
    assert session.close().status == "ok"


def test_periodic_timer_expire_records_stop_failed():
    import time

    mgr = _virtual_manager()
    mgr.open("can0")
    session = mgr.get("can0")
    assert session is not None
    f = CanFrame(arbitration_id=0x123, data=b"\x01")
    assert periodic_start(mgr, "can0", "p1", f, 0.05, duration_s=0.05).status == "ok"
    pt = session.pop_periodic("p1")
    assert pt is not None

    class _Boom:
        def stop(self) -> None:
            raise RuntimeError("expire boom")

    # 保留 timer：只替换底层 task，让 expire 回调走到 boom
    pt.task = _Boom()
    session.add_periodic("p1", pt)
    deadline = time.time() + 2.0
    seen = None
    while time.time() < deadline:
        tasks = periodic_list(mgr, "can0").data["tasks"]
        if tasks and tasks[0].get("state") == "stop_failed":
            seen = tasks[0]
            break
        time.sleep(0.02)
    assert seen is not None
    assert "expire boom" in (seen.get("stop_error") or "")
    # 清理：换成可停 task
    pt2 = session.pop_periodic(seen["name"])
    assert pt2 is not None

    class _Ok:
        def stop(self) -> None:
            return None

    pt2.task = _Ok()
    if pt2._timer is not None:
        pt2._timer.cancel()
        pt2._timer = None
    session.add_periodic(seen["name"], pt2)
    assert periodic_stop(mgr, "can0", seen["name"]).status == "ok"


def test_periodic_reserve_is_atomic_under_contention():
    import threading

    from xusbcan.core.periodic import MAX_PERIODIC_TASKS

    mgr = _virtual_manager()
    mgr.open("can0")
    f = CanFrame(arbitration_id=0x123, data=b"\x01")
    barrier = threading.Barrier(8)
    outcomes: list[str] = []
    lock = threading.Lock()

    def worker(i: int) -> None:
        barrier.wait()
        result = periodic_start(mgr, "can0", f"c{i}", f, 0.1)
        with lock:
            outcomes.append(result.status)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert outcomes.count("ok") == 8
    assert len(periodic_list(mgr, "can0").data["tasks"]) == 8

    # 填满后并发再冲仍不得超过上限
    for i in range(MAX_PERIODIC_TASKS - 8):
        assert periodic_start(mgr, "can0", f"f{i}", f, 0.1).status == "ok"
    barrier2 = threading.Barrier(6)
    more: list[str] = []

    def overflow(i: int) -> None:
        barrier2.wait()
        result = periodic_start(mgr, "can0", f"o{i}", f, 0.1)
        with lock:
            more.append(result.status)

    threads = [threading.Thread(target=overflow, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert more.count("ok") == 0
    assert len(periodic_list(mgr, "can0").data["tasks"]) == MAX_PERIODIC_TASKS


def test_close_blocks_inflight_periodic_commit():
    """关闭开始后，在飞预留不得 commit 成功；回滚侧取消预留后关闭可完成。"""
    import threading
    import time

    from xusbcan.core.periodic import PeriodicTask
    from xusbcan.core.session import SessionState

    mgr = _virtual_manager()
    mgr.open("can0")
    session = mgr.get("can0")
    assert session is not None
    f = CanFrame(arbitration_id=0x123, data=b"\x01")
    assert session.reserve_periodic("p1", max_tasks=32).status == "ok"

    close_box: dict = {}

    def closer() -> None:
        close_box["r"] = session.close()

    thread = threading.Thread(target=closer)
    thread.start()
    deadline = time.time() + 2.0
    while time.time() < deadline and not session._closing:
        time.sleep(0.01)
    assert session._closing is True

    class _OkTask:
        def stop(self) -> None:
            return None

    pt = PeriodicTask(name="p1", frame=f, period=0.1, task=_OkTask())
    assert session.commit_periodic("p1", pt) is False
    assert "p1" in session._periodic_reserved
    assert session.reserve_periodic("p2", max_tasks=32).status == "error"
    session.cancel_periodic_reserve("p1")

    thread.join(timeout=2.0)
    assert close_box["r"].status == "ok"
    assert session.state is SessionState.CLOSED


def test_close_waits_for_periodic_start_rollback():
    """启动提交失败后的底层 stop 回滚未完成前，close 不得返回成功。"""
    import threading
    import time

    from xusbcan.core.periodic import PeriodicTask
    from xusbcan.core.session import SessionState

    mgr = _virtual_manager()
    mgr.open("can0")
    session = mgr.get("can0")
    assert session is not None
    f = CanFrame(arbitration_id=0x123, data=b"\x01")

    release_stop = threading.Event()
    stop_entered = threading.Event()
    closing_seen = threading.Event()
    reserved_ready = threading.Event()
    close_box: dict = {}

    class _SlowStop:
        def __init__(self, inner: object) -> None:
            self._inner = inner

        def stop(self) -> None:
            stop_entered.set()
            assert release_stop.wait(timeout=2.0)
            self._inner.stop()  # type: ignore[attr-defined]

    def starter() -> None:
        assert session.reserve_periodic("p1", max_tasks=32).status == "ok"
        assert session.begin_periodic_op()
        try:
            real = session.bus.send_periodic(f.to_can_message(), 0.1)
            wrapper = _SlowStop(real)
            pt = PeriodicTask(name="p1", frame=f, period=0.1, task=wrapper)
            reserved_ready.set()
            assert closing_seen.wait(timeout=2.0)
            assert session.commit_periodic("p1", pt) is False
            try:
                pt.stop()
            finally:
                session.cancel_periodic_reserve("p1")
        finally:
            session.end_periodic_op()

    def closer() -> None:
        assert reserved_ready.wait(timeout=2.0)
        close_box["r"] = session.close()

    t_start = threading.Thread(target=starter)
    t_close = threading.Thread(target=closer)
    t_start.start()
    assert reserved_ready.wait(timeout=2.0)
    t_close.start()
    deadline = time.time() + 2.0
    while time.time() < deadline and not session._closing:
        time.sleep(0.01)
    closing_seen.set()
    assert stop_entered.wait(timeout=2.0)
    time.sleep(0.15)
    assert "r" not in close_box
    release_stop.set()
    t_start.join(timeout=2.0)
    t_close.join(timeout=2.0)
    assert close_box["r"].status == "ok"
    assert session.state is SessionState.CLOSED


def test_close_waits_for_periodic_stop_inflight():
    """periodic_stop 底层 stop 未完成前，close 不得返回成功。"""
    import threading
    import time

    from xusbcan.core.session import SessionState

    mgr = _virtual_manager()
    mgr.open("can0")
    session = mgr.get("can0")
    assert session is not None
    f = CanFrame(arbitration_id=0x123, data=b"\x01")
    assert periodic_start(mgr, "can0", "p1", f, 0.1).status == "ok"
    pt = session.pop_periodic("p1")
    assert pt is not None
    real = pt.task
    release_stop = threading.Event()
    stop_entered = threading.Event()

    class _SlowStop:
        def stop(self) -> None:
            stop_entered.set()
            assert release_stop.wait(timeout=2.0)
            real.stop()

    pt.task = _SlowStop()
    session.add_periodic("p1", pt)

    stop_box: dict = {}
    close_box: dict = {}

    def stopper() -> None:
        stop_box["r"] = periodic_stop(mgr, "can0", "p1")

    def closer() -> None:
        assert stop_entered.wait(timeout=2.0)
        close_box["r"] = session.close()

    t_stop = threading.Thread(target=stopper)
    t_close = threading.Thread(target=closer)
    t_stop.start()
    assert stop_entered.wait(timeout=2.0)
    t_close.start()
    time.sleep(0.15)
    assert "r" not in close_box
    release_stop.set()
    t_stop.join(timeout=2.0)
    t_close.join(timeout=2.0)
    assert stop_box["r"].status == "ok"
    assert close_box["r"].status == "ok"
    assert session.state is SessionState.CLOSED


def test_close_waits_for_timer_expire_stop():
    """Timer expire 的 stop 未完成前，close 不得返回成功。"""
    import threading
    import time

    from xusbcan.core.session import SessionState

    mgr = _virtual_manager()
    mgr.open("can0")
    session = mgr.get("can0")
    assert session is not None
    f = CanFrame(arbitration_id=0x123, data=b"\x01")
    assert periodic_start(mgr, "can0", "p1", f, 0.05, duration_s=0.05).status == "ok"
    pt = session.pop_periodic("p1")
    assert pt is not None
    real = pt.task
    release_stop = threading.Event()
    stop_entered = threading.Event()

    class _SlowStop:
        def stop(self) -> None:
            stop_entered.set()
            assert release_stop.wait(timeout=2.0)
            real.stop()

    pt.task = _SlowStop()
    session.add_periodic("p1", pt)

    close_box: dict = {}

    def closer() -> None:
        assert stop_entered.wait(timeout=2.0)
        close_box["r"] = session.close()

    t_close = threading.Thread(target=closer)
    t_close.start()
    assert stop_entered.wait(timeout=2.0)
    time.sleep(0.15)
    assert "r" not in close_box
    release_stop.set()
    t_close.join(timeout=2.0)
    assert close_box["r"].status == "ok"
    assert session.state is SessionState.CLOSED


def test_close_rejects_periodic_stop_started_after_closing():
    """_closing 之后新进入的 periodic_stop 不得进底层 stop；由 close 统一清理。"""
    import threading
    import time

    from xusbcan.core.session import SessionState

    mgr = _virtual_manager()
    mgr.open("can0")
    session = mgr.get("can0")
    assert session is not None
    f = CanFrame(arbitration_id=0x123, data=b"\x01")
    assert periodic_start(mgr, "can0", "p1", f, 0.1).status == "ok"
    pt = session.pop_periodic("p1")
    assert pt is not None
    real = pt.task
    stop_threads: list[str] = []
    lock = threading.Lock()

    class _CountStop:
        def stop(self) -> None:
            with lock:
                stop_threads.append(threading.current_thread().name)
            real.stop()

    pt.task = _CountStop()
    session.add_periodic("p1", pt)

    closing_seen = threading.Event()
    close_box: dict = {}

    def closer() -> None:
        # 让主线程有机会在 close 循环前观察到 _closing
        def _mark() -> None:
            deadline = time.time() + 2.0
            while time.time() < deadline:
                if session._closing:
                    closing_seen.set()
                    return
                time.sleep(0.001)

        marker = threading.Thread(target=_mark, name="closing-marker")
        marker.start()
        close_box["r"] = session.close()
        marker.join(timeout=2.0)

    t_close = threading.Thread(target=closer, name="session-close")
    t_close.start()
    assert closing_seen.wait(timeout=2.0)

    late_stop = periodic_stop(mgr, "can0", "p1")
    assert late_stop.status == "error"
    assert late_stop.error is not None
    assert late_stop.error.code == "DEVICE_NOT_OPEN"

    t_close.join(timeout=2.0)
    assert close_box["r"].status == "ok"
    assert session.state is SessionState.CLOSED
    with lock:
        assert stop_threads == ["session-close"]


def test_open_does_not_replace_error_session_with_failed_periodic():
    from xusbcan.core.session import SessionState

    mgr = _virtual_manager()
    mgr.open("can0")
    f = CanFrame(arbitration_id=0x123, data=b"\x01")
    assert periodic_start(mgr, "can0", "p1", f, 0.1).status == "ok"
    session = mgr.get("can0")
    assert session is not None
    pt = session.pop_periodic("p1")
    assert pt is not None
    real = pt.task

    class _Boom:
        def stop(self) -> None:
            raise RuntimeError("keep error session")

    pt.task = _Boom()
    session.add_periodic("p1", pt)
    assert mgr.close("can0").status == "error"
    assert session.state is SessionState.ERROR
    assert mgr.get("can0") is session

    opened = mgr.open("can0")
    assert opened.status == "error"
    assert opened.error is not None
    assert opened.error.code == "DEVICE_NOT_OPEN"
    assert mgr.get("can0") is session
    assert len(periodic_list(mgr, "can0").data["tasks"]) == 1

    pt.task = real
    assert periodic_stop(mgr, "can0", "p1").status == "ok"
    assert mgr.close("can0").status == "ok"


def test_stop_monitor_join_timeout_keeps_reference():
    from xusbcan.core.monitor import stop_monitor

    mgr = _virtual_manager()
    mgr.open("can0")
    session = mgr.get("can0")
    assert session is not None

    class _Stuck:
        def stop(self) -> None:
            return None

        def join(self, timeout=None) -> bool:
            return False

        def to_result(self):
            raise AssertionError("should not clear stuck monitor")

    stuck = _Stuck()
    session.set_monitor(stuck)
    session.acquire_receive("monitor")
    result = stop_monitor(session)
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "CLOSE_TIMEOUT"
    assert session.monitor is stuck
    assert session.receive_owner == "monitor"
    session.clear_monitor(stuck)
    session.release_receive("monitor")
    assert mgr.close("can0").status == "ok"


class _FailingBus(can.BusABC):
    """假适配器：第 fail_at 帧发送抛 CanOperationError，覆盖「部分发送」分支。"""

    def __init__(self, fail_at: int = 1):
        super().__init__(channel="fake")
        self.fail_at = fail_at
        self.send_count = 0
        self.shutdown_called = False

    def send(self, msg, timeout=None):
        if self.send_count == self.fail_at:
            raise can.CanOperationError("fake send fail")
        self.send_count += 1

    def _recv_internal(self, timeout):
        return None, False

    def shutdown(self):
        self.shutdown_called = True


def test_partial_send_keeps_progress():
    """多帧发送不是全有或全无：第 1 帧成功、第 2 帧失败时保留进度（§4.5）。"""
    mgr = SessionManager(opener=lambda spec: Result.ok(_FailingBus(fail_at=1)))
    mgr.register("can0", DeviceSpec(vendor="zlg", model="USBCAN-2E-U", channel=0))
    mgr.open("can0")
    session = mgr.get("can0")
    frames = [
        CanFrame(arbitration_id=0x1, data=b"\x01"),
        CanFrame(arbitration_id=0x2, data=b"\x02"),
    ]
    r = transmit(session, frames)
    assert r.status == "error"
    assert r.data == {"sent": 1, "failed_index": 1}
    assert r.error.code == "SEND_FAILED"
