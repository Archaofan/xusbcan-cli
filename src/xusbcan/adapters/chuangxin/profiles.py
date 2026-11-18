"""创芯型号快捷方式。不导入 DLL；打开设备时才加载 ControlCAN。

USB_CAN-2C 与 USB_CAN-2A-GD 共用同一后端与设备类型值（VCI_USBCAN2=4）。
USB_CAN-2A-GD 仅登记；真机验证暂挂起，勿写成已确认。
"""

from __future__ import annotations

from ..profile import Profile

_SHARED = {"device_type": 4, "device_index": 0}

PROFILES = {
    ("chuangxin", "USB_CAN-2C"): Profile(
        "chuangxin",
        channels=2,
        fd=False,
        options=dict(_SHARED),
    ),
    # 同接口族；真机确认以实物为准，可与 2C 共用后端。
    ("chuangxin", "USB_CAN-2A-GD"): Profile(
        "chuangxin",
        channels=2,
        fd=False,
        options=dict(_SHARED),
    ),
}
