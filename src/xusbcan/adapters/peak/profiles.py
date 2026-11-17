"""PEAK 型号快捷方式。通道 0 对应 PCAN_USBBUS1。"""

from __future__ import annotations

from ..profile import Profile


def _pcan_channel(index: int) -> str:
    return f"PCAN_USBBUS{index + 1}"


PROFILES = {
    ("peak", "PCAN-USB"): Profile("pcan", channel_map=_pcan_channel),
}
