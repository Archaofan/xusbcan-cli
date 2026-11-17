"""周立功型号快捷方式。不导入 DLL；打开设备时才加载后端。"""

from __future__ import annotations

from ..profile import Profile

# device_type 21 即 USBCAN-2E-U，与 zlgcan 的设备类型常量一致。
PROFILES = {
    ("zlg", "USBCAN-2E-U"): Profile(
        "zlg",
        channels=2,
        fd=False,
        options={"device_type": 21, "device_index": 0},
    ),
}
