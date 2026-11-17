"""创芯 USB_CAN-2C：profile 与 ControlCAN 打开参数（无硬件）。"""

from __future__ import annotations

from unittest import mock

import pytest

from xusbcan.adapters import registry
from xusbcan.adapters.registry import open_bus, resolve
from xusbcan.models import BitrateConfig, DeviceSpec


def test_resolve_usb_can_2c_profile():
    p = resolve(DeviceSpec(vendor="chuangxin", model="USB_CAN-2C"))
    assert p.interface == "chuangxin"
    assert p.channels == 2
    assert p.fd is False
    assert p.channel_map is None
    assert p.options == {"device_type": 4, "device_index": 0}


def test_resolve_usb_can_2a_gd_shares_backend():
    p = resolve(DeviceSpec(vendor="chuangxin", model="USB_CAN-2A-GD"))
    assert p.interface == "chuangxin"
    assert p.channels == 2
    assert p.options == {"device_type": 4, "device_index": 0}


def test_open_bus_passes_channel_and_bitrate_unchanged():
    spec = DeviceSpec(
        vendor="chuangxin",
        model="USB_CAN-2C",
        channel=0,
        bitrate=BitrateConfig(nominal=250_000),
    )
    with mock.patch.object(registry.can, "Bus") as mock_bus:
        open_bus(spec)
    kwargs = mock_bus.call_args.kwargs
    assert kwargs["interface"] == "chuangxin"
    assert kwargs["channel"] == 0
    assert kwargs["bitrate"] == 250_000
    assert kwargs["device_type"] == 4
    assert kwargs["device_index"] == 0


def test_bitrate_to_timing_250k():
    from xusbcan.adapters.chuangxin.dll import bitrate_to_timing

    assert bitrate_to_timing(250_000) == (0x01, 0x1C)


def test_bitrate_to_timing_unknown_raises():
    from xusbcan.adapters.chuangxin.dll import bitrate_to_timing

    with pytest.raises(ValueError, match="不支持的波特率"):
        bitrate_to_timing(123_456)


def test_sdk_env_required(monkeypatch):
    from xusbcan.adapters.chuangxin import dll as cx_dll

    monkeypatch.delenv(cx_dll.SDK_ENV_VAR, raising=False)
    cx_dll.get_dll.cache_clear()
    with pytest.raises(Exception, match=cx_dll.SDK_ENV_VAR):
        cx_dll.get_dll()
    cx_dll.get_dll.cache_clear()
