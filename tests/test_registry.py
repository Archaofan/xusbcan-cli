"""registry 单元测试：Profile 映射与 can.Bus 构造（不依赖真实硬件）。"""

from __future__ import annotations

from unittest import mock

import pytest

from xusbcan.adapters import registry
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
    spec = DeviceSpec(
        vendor="peak", model="PCAN-USB", channel=0, bitrate=BitrateConfig(nominal=500_000)
    )
    with mock.patch.object(registry.can, "Bus") as mock_bus:
        registry.open_bus(spec)
    kwargs = mock_bus.call_args.kwargs
    assert kwargs["interface"] == "pcan"
    assert kwargs["channel"] == "PCAN_USBBUS1"  # channel_map：逻辑 0 → PCAN_USBBUS1
    assert kwargs["bitrate"] == 500_000
    assert kwargs["ignore_config"] is True


def test_vector_profile_allows_second_channel_and_fd():
    spec = DeviceSpec(
        vendor="vector",
        model="VN1630",
        channel=1,
        bitrate=BitrateConfig(nominal=500_000, data=2_000_000),
    )
    with mock.patch.object(registry.can, "Bus") as mock_bus:
        registry.open_bus(spec)
    kwargs = mock_bus.call_args.kwargs
    assert kwargs["interface"] == "vector"
    assert kwargs["channel"] == 1
    assert kwargs["bitrate"] == 500_000
    assert kwargs["data_bitrate"] == 2_000_000
    assert kwargs["fd"] is True


def test_classic_profile_rejects_data_bitrate():
    spec = DeviceSpec(
        vendor="zlg",
        model="USBCAN-2E-U",
        channel=0,
        bitrate=BitrateConfig(nominal=500_000, data=2_000_000),
    )
    with pytest.raises(ValueError, match="CAN FD"):
        open_bus(spec)


def test_python_can_interface_opens_without_profile():
    spec = DeviceSpec(interface="virtual", channel="virt-a", bitrate=BitrateConfig(nominal=500_000))
    bus = open_bus(spec)
    try:
        assert bus.channel_info
    finally:
        bus.shutdown()


def test_unknown_python_can_interface_raises():
    spec = DeviceSpec(interface="not-a-real-backend", channel=0)
    with pytest.raises(KeyError, match="未声明"):
        open_bus(spec)


def test_channel_out_of_range():
    spec = DeviceSpec(vendor="zlg", model="USBCAN-2E-U", channel=9)
    with pytest.raises(ValueError):
        open_bus(spec)
