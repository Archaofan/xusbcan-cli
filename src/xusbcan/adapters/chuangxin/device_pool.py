"""创芯设备池：一张物理卡 OpenDevice 一次，多通道共享。

ControlCAN 的 VCI_OpenDevice 返回成功/失败，不返回句柄；池用
(device_type, device_index) 记账。最后一路 release 才 CloseDevice。
"""

from __future__ import annotations

import atexit
import threading
import time
from dataclasses import dataclass, field

import can

from .dll import STATUS_OK, get_dll


@dataclass
class _DeviceEntry:
    device_type: int
    device_index: int
    refcount: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)
    open_channels: set[int] = field(default_factory=set)


class ChuangxinDevicePool:
    def __init__(self) -> None:
        self._entries: dict[tuple[int, int], _DeviceEntry] = {}
        self._pool_lock = threading.Lock()

    def acquire(self, device_type: int, device_index: int) -> _DeviceEntry:
        key = (device_type, device_index)
        dll = get_dll()
        with self._pool_lock:
            entry = self._entries.get(key)
            if entry is None:
                ret = int(dll.VCI_OpenDevice(device_type, device_index, 0))
                if ret != STATUS_OK:
                    raise can.CanInitializationError(
                        f"VCI_OpenDevice({device_type}, {device_index}) 失败，返回 {ret}"
                        "（设备未连接、驱动未就绪，或 DLL 与硬件不匹配）"
                    )
                entry = _DeviceEntry(device_type=device_type, device_index=device_index)
                self._entries[key] = entry
            entry.refcount += 1
            return entry

    def release(self, device_type: int, device_index: int) -> bool:
        key = (device_type, device_index)
        with self._pool_lock:
            entry = self._entries.get(key)
            if entry is None:
                return False
            entry.refcount -= 1
            if entry.refcount > 0:
                return False
            del self._entries[key]
        dll = get_dll()
        dll.VCI_CloseDevice(device_type, device_index)
        time.sleep(0.5)
        return True

    def close_all(self) -> None:
        with self._pool_lock:
            entries = list(self._entries.values())
            self._entries.clear()
        if not entries:
            return
        dll = get_dll()
        for entry in entries:
            try:
                dll.VCI_CloseDevice(entry.device_type, entry.device_index)
            except Exception:  # noqa: BLE001
                pass


device_pool = ChuangxinDevicePool()
atexit.register(device_pool.close_all)
