"""core 层单元测试：会话管理、复用规则、命令处理器（virtual 后端 + 假适配器）。"""

from __future__ import annotations

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
