"""Vector 型号快捷方式。VN1630 为两路，并允许 CAN FD 数据段波特率。"""

from __future__ import annotations

from ..profile import Profile

PROFILES = {
    ("vector", "VN1630"): Profile("vector", channels=2, fd=True),
}
