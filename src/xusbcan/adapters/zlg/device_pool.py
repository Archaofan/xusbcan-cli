# -*- coding: utf-8 -*-
"""ZlgDevicePool：一张物理卡的设备句柄共享 + 引用计数 + 互斥锁。

key = (device_type, device_index)。首次 acquire 才 ZCAN_OpenDevice，最后一路
release 才 ZCAN_CloseDevice。同一张卡的发送 / 接收 / SetValue 都走 entry.lock
这把互斥锁。进程级单例（模块级一个池实例）。
"""

from __future__ import annotations

import atexit
import threading
import time
from dataclasses import dataclass, field

import can

from .dll import INVALID_HANDLE, get_dll


@dataclass
class _DeviceEntry:
    """一张已打开设备卡的状态。lock 覆盖该卡的发送 / 接收 / SetValue。"""

    handle: int
    refcount: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)
    open_channels: set[int] = field(default_factory=set)


class ZlgDevicePool:
    """设备句柄池。key=(device_type, device_index)，进程级单例。"""

    def __init__(self) -> None:
        self._entries: dict[tuple[int, int], _DeviceEntry] = {}
        self._pool_lock = threading.Lock()  # 只保护 _entries 字典的簿记

    def acquire(self, device_type: int, device_index: int) -> _DeviceEntry:
        """取得设备卡句柄（引用计数 +1）。首次 acquire 才 OpenDevice。"""
        key = (device_type, device_index)
        dll = get_dll()
        with self._pool_lock:
            entry = self._entries.get(key)
            if entry is None:
                handle = dll.ZCAN_OpenDevice(device_type, device_index, 0)
                if not handle or handle == INVALID_HANDLE:
                    raise can.CanInitializationError(
                        f"ZCAN_OpenDevice({device_type}, {device_index}) 返回空句柄"
                        "（设备未连接或内核 DLL 缺失）"
                    )
                entry = _DeviceEntry(handle=handle)
                self._entries[key] = entry
            entry.refcount += 1
            return entry

    def release(self, device_type: int, device_index: int) -> bool:
        """归还设备卡引用（引用计数 -1）。最后一路 release 才 CloseDevice。"""
        key = (device_type, device_index)
        with self._pool_lock:
            entry = self._entries.get(key)
            if entry is None:
                return False
            entry.refcount -= 1
            if entry.refcount > 0:
                return False
            del self._entries[key]
        # 引用归零，最后一路：关闭整卡（在池锁外关闭，避免阻塞其它卡）
        dll = get_dll()
        dll.ZCAN_CloseDevice(entry.handle)
        # 真机实测：CloseDevice 异步，立即 reopen 会 InitCAN 失败；
        # 需短暂等待设备复位（0.5s 已实测足够）。
        time.sleep(0.5)
        return True

    def close_all(self) -> None:
        """进程退出时兜底：关闭所有仍持有的设备句柄。"""
        with self._pool_lock:
            entries = list(self._entries.values())
            self._entries.clear()
        if not entries:
            return
        # 有 entry 时 DLL 必然已加载（acquire 先 get_dll 再 OpenDevice），此处走缓存
        dll = get_dll()
        for entry in entries:
            try:
                dll.ZCAN_CloseDevice(entry.handle)
            except Exception:  # noqa: BLE001 —— 退出清理尽力而为
                pass


# 进程级单例（架构方案 §4.4 / §10：设备池只存在于 adapters/zlg/）
device_pool = ZlgDevicePool()

# 进程退出时注册清理，把设备池里残留的句柄关掉（架构方案 §4.4 第 5 条）
atexit.register(device_pool.close_all)
