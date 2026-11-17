"""周立功型号快捷方式。不导入 DLL；打开设备时才加载后端。"""

from __future__ import annotations

from ..profile import Profile

# device_type 与 zlgcan.h 一致：USBCAN-II=4，USBCAN-2E-U=21。
PROFILES = {
    ("zlg", "USBCAN-2E-U"): Profile(
        "zlg",
        channels=2,
        fd=False,
        options={"device_type": 21, "device_index": 0},
    ),
    ("zlg", "USBCAN-II"): Profile(
        "zlg",
        channels=2,
        fd=False,
        options={"device_type": 4, "device_index": 0},
    ),
}
