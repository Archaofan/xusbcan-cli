"""registry 单元测试：Profile 映射与 can.Bus 构造（不依赖真实硬件）。"""

from __future__ import annotations

import pytest

from xusbcan.adapters.registry import open_bus, resolve
from xusbcan.models import BitrateConfig, DeviceSpec


def test_resolve_zlg_profile():
    p = resolve(DeviceSpec(vendor="zlg", model="USBCAN-2E-U"))
    assert p.interface == "zlg"
    assert p.channels == 2
    assert p.fd is False
    assert p.options == {"device_type": 21, "device_index": 0}


def test_resolve_peak_channel_map():
    p = resolve(DeviceSpec(vendor="peak", model="PCAN-USB"))
    assert p.interface == "pcan"
    # 逻辑通道 0 → 厂商通道地址 "PCAN_USBBUS1"
    assert p.channel_map(0) == "PCAN_USBBUS1"
    assert p.channel_map(1) == "PCAN_USBBUS2"


def test_resolve_unknown_vendor_raises():
    with pytest.raises(KeyError):
        resolve(DeviceSpec(vendor="nope", model="X"))


def test_open_bus_channel_map_and_bitrate():
    """open_bus 正确应用 channel_map 与 bitrate（mock can.Bus 捕获参数）。"""
    from unittest import mock

    from xusbcan.adapters import registry

    spec = DeviceSpec(
        vendor="peak", model="PCAN-USB", channel=0, bitrate=BitrateConfig(nominal=500_000)
    )
    with mock.patch.object(registry.can, "Bus") as mock_bus:
        registry.open_bus(spec)
    kwargs = mock_bus.call_args.kwargs
    assert kwargs["interface"] == "pcan"
    assert kwargs["channel"] == "PCAN_USBBUS1"  # channel_map：逻辑 0 → PCAN_USBBUS1
    assert kwargs["bitrate"] == 500_000


def test_channel_out_of_range():
    spec = DeviceSpec(vendor="zlg", model="USBCAN-2E-U", channel=9)
    with pytest.raises(ValueError):
        open_bus(spec)
