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
