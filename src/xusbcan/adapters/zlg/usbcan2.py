"""USBCAN-II：软件滤波 + 软件周期发送（不写 filter_* / auto_send）。

真机确认：SetValue(baud_rate) + InitCAN + 收发可用；filter_clear / auto_send
在 II 上不可靠或失败，故与 2E 硬件路径隔离。
"""

from __future__ import annotations

from .common import ZlgBusBase
from .dll import ZCAN_USBCAN2


class Usbcan2Bus(ZlgBusBase):
    """周立功 USBCAN-II（device_type=4）。"""

    CARD_LABEL = "USBCAN-II"

    def __init__(self, channel, can_filters=None, **kwargs):
        kwargs.setdefault("device_type", ZCAN_USBCAN2)
        super().__init__(channel, can_filters=can_filters, **kwargs)

    # 不覆盖 _apply_filters / _send_periodic_internal：走 python-can 软件滤波与线程周期。
