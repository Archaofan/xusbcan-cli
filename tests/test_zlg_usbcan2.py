"""USBCAN-II 无硬件：profile、分发、软件滤波（不碰 filter_* / auto_send）。"""

from __future__ import annotations

import threading
from types import SimpleNamespace

import can
import pytest
from can import Message

from xusbcan.adapters.registry import resolve
from xusbcan.adapters.zlg.backend import ZlgBus
from xusbcan.adapters.zlg.usbcan2 import Usbcan2Bus
from xusbcan.adapters.zlg.usbcan_2e_u import Usbcan2EUBus
from xusbcan.models import DeviceSpec


class _Dll:
    def __init__(self) -> None:
        self.paths: list[str] = []

    def ZCAN_SetValue(self, handle, path, value):
        self.paths.append(path.decode() if isinstance(path, bytes) else path)
        return 1


def _bare_ii() -> Usbcan2Bus:
    bus = Usbcan2Bus.__new__(Usbcan2Bus)
    bus._hw_jobs = {}
    bus._channel = 0
    bus._dll = _Dll()
    bus._entry = SimpleNamespace(handle=1, lock=threading.Lock())
    bus._is_shutdown = False
    bus._filters = None
    return bus


def test_resolve_usbcan2_profile():
    p = resolve(DeviceSpec(vendor="zlg", model="USBCAN-II"))
    assert p.interface == "zlg"
    assert p.channels == 2
    assert p.fd is False
    assert p.options == {"device_type": 4, "device_index": 0}


def test_zlg_bus_dispatches_by_device_type(monkeypatch):
    created: list[type] = []

    def fake_2e(self, channel, can_filters=None, **kwargs):
        created.append(Usbcan2EUBus)
        self.channel_info = "2e"
        self._is_shutdown = False

    def fake_ii(self, channel, can_filters=None, **kwargs):
        created.append(Usbcan2Bus)
        self.channel_info = "ii"
        self._is_shutdown = False

    monkeypatch.setattr(Usbcan2EUBus, "__init__", fake_2e)
    monkeypatch.setattr(Usbcan2Bus, "__init__", fake_ii)

    a = ZlgBus(0, bitrate=250_000, device_type=21)
    b = ZlgBus(0, bitrate=250_000, device_type=4)
    assert isinstance(a, Usbcan2EUBus)
    assert isinstance(b, Usbcan2Bus)
    assert created == [Usbcan2EUBus, Usbcan2Bus]


def test_usbcan2_set_filters_does_not_touch_hardware_props():
    bus = _bare_ii()
    bus.set_filters([{"can_id": 0x100, "can_mask": 0x7FF, "extended": False}])
    assert bus._dll.paths == []
    bus.set_filters(None)
    assert bus._dll.paths == []


def test_usbcan2_send_allows_concurrent_software_periodic_path():
    """II 不走硬件 auto_send，send 不应被 _hw_jobs 互斥挡住。"""
    bus = _bare_ii()
    bus._hw_jobs[0] = (Message(arbitration_id=1, data=[1]), 10)

    def fake_transmit(handle, tx, n):
        return 1

    bus._dll.ZCAN_Transmit = fake_transmit  # type: ignore[attr-defined]
    bus._ch_handle = 1
    # 若误用 2E 的 send 互斥，这里会抛「硬件周期发送」
    bus.send(Message(arbitration_id=0x123, data=[0x01, 0x02]))


def test_usbcan2_rejects_fd():
    bus = _bare_ii()
    bus._ch_handle = 1
    with pytest.raises(can.CanError, match="CAN FD"):
        bus.send(Message(arbitration_id=1, data=[1], is_fd=True))
