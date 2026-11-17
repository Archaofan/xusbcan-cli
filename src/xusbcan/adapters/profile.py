"""型号快捷方式。python-can 已有后端不必写在这里；这里只放通道映射和固定参数。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


class ChannelOutOfRange(ValueError):
    """逻辑通道超出该型号登记的通道数。"""


class ModelCapabilityError(ValueError):
    """型号登记明确不支持的能力，例如经典 CAN 卡上的数据段波特率。"""


@dataclass
class Profile:
    """(vendor, model) → python-can interface。options 原样进入 can.Bus。"""

    interface: str
    channels: int = 1
    fd: bool = False
    channel_map: Callable[[int], int | str] | None = None
    options: dict | None = None
