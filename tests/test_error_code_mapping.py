"""适配器异常上的 ErrorCode 须经 registry / map_error 传到 Result.error.code。"""

from __future__ import annotations

from unittest.mock import patch

import can

from xusbcan.adapters.chuangxin.dll import ChuangxinConfigError
from xusbcan.adapters.registry import open_device
from xusbcan.adapters.zlg.dll import ZlgDllNotFoundError
from xusbcan.core.commands import transmit
from xusbcan.core.session import Session, SessionState, map_error
from xusbcan.models import BitrateConfig, CanFrame, DeviceSpec, ErrorCode


def test_map_error_prefers_attached_code():
    exc = ZlgDllNotFoundError("missing dll")
    assert map_error(exc) is ErrorCode.DLL_NOT_FOUND
    assert map_error(ChuangxinConfigError("bad env")) is ErrorCode.CONFIG_ERROR


def test_open_device_preserves_dll_not_found():
    spec = DeviceSpec(
        vendor="zlg",
        model="USBCAN-2E-U",
        channel=0,
        bitrate=BitrateConfig(nominal=500_000),
    )
    with patch(
        "xusbcan.adapters.registry.open_bus",
        side_effect=ZlgDllNotFoundError("SDK 目录不存在"),
    ):
        result = open_device(spec)
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == ErrorCode.DLL_NOT_FOUND.value


def test_open_device_preserves_config_error_from_chuangxin():
    spec = DeviceSpec(
        vendor="chuangxin",
        model="USB_CAN-2C",
        channel=0,
        bitrate=BitrateConfig(nominal=500_000),
    )
    with patch(
        "xusbcan.adapters.registry.open_bus",
        side_effect=ChuangxinConfigError("未设置 CHUANGXIN_SDK_DIR"),
    ):
        result = open_device(spec)
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == ErrorCode.CONFIG_ERROR.value


def test_transmit_maps_capability_code():
    class _Bus(can.BusABC):
        def __init__(self) -> None:
            super().__init__(channel="t")

        def send(self, msg, timeout=None):
            from xusbcan.adapters.zlg.common import ZlgCapabilityUnsupportedError

            raise ZlgCapabilityUnsupportedError("no fd")

        def _recv_internal(self, timeout):
            return None, False

        def shutdown(self):
            return None

    session = Session(
        name="t",
        bus=_Bus(),
        spec=DeviceSpec(
            vendor="zlg",
            model="USBCAN-2E-U",
            channel=0,
            bitrate=BitrateConfig(nominal=500_000),
        ),
        state=SessionState.OPEN,
    )
    result = transmit(session, CanFrame(arbitration_id=0x1, data=b"\x01", is_fd=True))
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == ErrorCode.CAPABILITY_UNSUPPORTED.value


def test_cli_periodic_rejects_nonfinite_duration():
    from argparse import Namespace

    from xusbcan.cli.app import _periodic_for
    from xusbcan.core import SessionManager

    mgr = SessionManager()
    args = Namespace(
        alias="missing",
        id="0x123",
        data="01",
        ext=False,
        name="hb",
        period=0.1,
        duration=float("nan"),
    )
    result = _periodic_for(mgr, args)
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == ErrorCode.INVALID_ARGUMENT.value
