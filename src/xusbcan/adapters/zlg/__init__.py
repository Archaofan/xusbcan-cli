"""zlg python-can backend：把周立功 zlgcan.dll 适配成 ``can.Bus(interface='zlg')``。

经 entry point ``zlg = xusbcan.adapters.zlg.backend:ZlgBus`` 注册，与官方 backend
地位平等。本包模块级**不**加载 DLL（惰性 ``get_dll()``），Linux 上可安全导入。
"""

from .backend import ZlgBus
from .device_pool import ZlgDevicePool
from .dll import (
    ZlgConfigError,
    ZlgDllNotFoundError,
    ZlgError,
    get_dll,
)

__all__ = [
    "ZlgBus",
    "ZlgDevicePool",
    "get_dll",
    "ZlgError",
    "ZlgConfigError",
    "ZlgDllNotFoundError",
]
