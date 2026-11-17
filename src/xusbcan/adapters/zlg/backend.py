"""python-can 入口：``interface='zlg'`` → 按 device_type 分发到型号实现。

entry point：``zlg = xusbcan.adapters.zlg.backend:ZlgBus``。
上层只传 channel / bitrate / device_type；不要直接依赖具体型号类。
"""

from __future__ import annotations

from .common import ZlgCapabilityUnsupportedError
from .dll import ZCAN_USBCAN2, ZCAN_USBCAN_2E_U
from .usbcan2 import Usbcan2Bus
from .usbcan_2e_u import Usbcan2EUBus

__all__ = [
    "ZlgBus",
    "ZlgCapabilityUnsupportedError",
    "Usbcan2Bus",
    "Usbcan2EUBus",
    "ZCAN_USBCAN2",
    "ZCAN_USBCAN_2E_U",
]


class ZlgBus:
    """兼容工厂：默认 2E-U；``device_type=4`` 走 USBCAN-II。"""

    def __new__(cls, channel, can_filters=None, **kwargs):
        device_type = int(kwargs.get("device_type", ZCAN_USBCAN_2E_U))
        if device_type == ZCAN_USBCAN2:
            return Usbcan2Bus(channel, can_filters=can_filters, **kwargs)
        return Usbcan2EUBus(channel, can_filters=can_filters, **kwargs)
