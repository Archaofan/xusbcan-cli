"""无硬件：硬件周期发送互斥、滤波会话接口、MCP HTTP 只绑环回。"""

from __future__ import annotations

import threading
from types import SimpleNamespace

import can
import pytest
from can import Message

from xusbcan.adapters.zlg.usbcan_2e_u import Usbcan2EUBus
from xusbcan.core import (
    SessionManager,
    accept_all_frames,
    open_session,
    periodic_start,
    periodic_stop,
    send,
    set_frame_filter,
)
from xusbcan.mcp.transport import resolve_mcp_transport
from xusbcan.models import BitrateConfig, CanFrame, DeviceSpec, Result


class _Dll:
    def __init__(self) -> None:
        self.paths: list[str] = []
        self.values: list[bytes] = []

    def ZCAN_SetValue(self, handle, path, value):
        self.paths.append(path.decode() if isinstance(path, bytes) else path)
        self.values.append(value if isinstance(value, bytes) else str(value).encode())
        return 1


def _bare() -> Usbcan2EUBus:
    bus = Usbcan2EUBus.__new__(Usbcan2EUBus)
    bus._hw_jobs = {}
    bus._channel = 0
    bus._dll = _Dll()
    bus._entry = SimpleNamespace(handle=1, lock=threading.Lock())
    bus.CARD_LABEL = "USBCAN-2E-U"
    return bus


def test_hardware_periodic_blocks_send_until_stop():
    bus = _bare()
    task = bus._send_periodic_internal(
        Message(arbitration_id=0x123, data=[1, 2]), 0.05
    )
    assert bus._hw_jobs
    assert "0/clear_auto_send" in bus._dll.paths
    assert "0/auto_send" in bus._dll.paths
    with pytest.raises(can.CanOperationError, match="硬件周期发送"):
        bus.send(Message(arbitration_id=0x1, data=[1]))
    task.stop()
    assert bus._hw_jobs == {}


def test_shutdown_hooks_preserve_jobs_when_clear_auto_send_fails():
    """clear_auto_send 失败时不得先清空 _hw_jobs，且必须向上抛出。"""
    bus = _bare()
    bus._hw_jobs[0] = (Message(arbitration_id=0x10, data=[1]), 10)

    def _boom():
        raise can.CanOperationError("clear_auto_send failed")

    bus._clear_hw_device = _boom  # type: ignore[method-assign]
    with pytest.raises(can.CanOperationError, match="clear_auto_send failed"):
        bus._shutdown_card_hooks()
    assert 0 in bus._hw_jobs


def test_hardware_periodic_rejects_duration_and_full_table():
    bus = _bare()
    with pytest.raises(can.CanOperationError, match="duration"):
        bus._send_periodic_internal(
            Message(arbitration_id=0x1, data=[1]), 0.01, duration=1
        )
    for i in range(Usbcan2EUBus.HW_PERIODIC_MAX):
        bus._alloc_hw(Message(arbitration_id=i, data=[1]), 10)
    with pytest.raises(can.CanOperationError, match="已满"):
        bus._alloc_hw(Message(arbitration_id=0x99, data=[1]), 10)


def test_acceptance_replaces_table_and_accept_all_acks():
    bus = _bare()
    bus.set_acceptance(0x100, 0x100, False)
    assert bus._dll.paths[-1] == "0/filter_ack"
    assert "0/filter_clear" in bus._dll.paths
    bus._dll.paths.clear()
    bus.accept_all()
    assert "0/filter_ack" in bus._dll.paths
    assert bus._dll.paths.count("0/filter_start") == 2
    bus._dll.paths.clear()
    bus.set_filters([{"can_id": 0x100, "can_mask": 0x7FF, "extended": False}])
    assert bus._dll.paths[-1] == "0/filter_ack"
    assert b"0x00000100" in bus._dll.values
    with pytest.raises(can.CanOperationError):
        bus.set_acceptance(0, 0x800, False)


def test_filter_tools_need_capability_and_open_session():
    class _Bus:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        def set_filters(self, filters):
            self.calls.append(("filters", filters))

        def shutdown(self):
            return None

    holder: dict = {}

    def opener(spec: DeviceSpec):
        bus = _Bus()
        holder["bus"] = bus
        return Result.ok(bus)

    mgr = SessionManager(opener=opener)
    mgr.register(
        "can0",
        DeviceSpec("zlg", "USBCAN-2E-U", 0, BitrateConfig(500_000)),
    )
    assert set_frame_filter(mgr, "can0", 1, 2, False).status == "error"
    open_session(mgr, "can0")
    r = set_frame_filter(mgr, "can0", 0x100, 0x1FF, True)
    assert r.status == "ok"
    programmed = holder["bus"].calls[-1]
    assert programmed[0] == "filters"
    assert programmed[1][0]["can_id"] == 0x100
    assert programmed[1][0]["extended"] is True
    assert accept_all_frames(mgr, "can0").status == "ok"
    assert holder["bus"].calls[-1] == ("filters", None)
    mgr.close_all()


def test_virtual_periodic_still_allows_send():
    def opener(spec: DeviceSpec):
        return Result.ok(can.Bus(interface="virtual", channel="vf", bitrate=500_000))

    mgr = SessionManager(opener=opener)
    mgr.register("can0", DeviceSpec("virtual", "virtual", 0, BitrateConfig(500_000)))
    open_session(mgr, "can0")
    filtered = set_frame_filter(mgr, "can0", 0x100, 0x1FF, False)
    assert filtered.status == "ok"
    assert filtered.data["mode"] == "mask"
    assert accept_all_frames(mgr, "can0").status == "ok"
    started = periodic_start(mgr, "can0", "hb", CanFrame(0x123, b"\x01"), 0.05)
    assert started.status == "ok"
    assert send(mgr, "can0", CanFrame(0x11, b"\x02")).status == "ok"
    assert periodic_stop(mgr, "can0", "hb").status == "ok"
    mgr.close_all()


def test_http_transport_is_loopback_only():
    kind, opts = resolve_mcp_transport({"backend": "stdio"})
    assert kind == "stdio" and opts == {}
    kind, opts = resolve_mcp_transport({"backend": "http", "port": 9000})
    assert kind == "streamable-http"
    assert opts == {"host": "127.0.0.1", "port": 9000}
    with pytest.raises(ValueError, match="127.0.0.1"):
        resolve_mcp_transport({"backend": "http", "host": "0.0.0.0"})
