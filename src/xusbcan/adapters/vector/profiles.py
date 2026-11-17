"""Vector 型号快捷方式。通道号原样交给 python-can 的 vector，不做逻辑重映射。"""

from __future__ import annotations

from ..profile import Profile

PROFILES = {
    ("vector", "VN1630"): Profile("vector", channels=2, fd=True),
    # VN1640A：物理通道索引与 python-can / XL Driver 一致（常见 0..4）。
    # app_name=None → 按全局通道号打开，不依赖 Vector Hardware Config 里的应用绑定。
    ("vector", "VN1640A"): Profile(
        "vector",
        channels=5,
        fd=True,
        options={"app_name": None},
    ),
}
