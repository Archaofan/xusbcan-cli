"""USBCAN-2E-U：硬件滤波 + 硬件周期发送（auto_send）。"""

from __future__ import annotations

import ctypes

import can
from can import Message

from .common import ZlgBusBase
from .dll import STATUS_OK, ZCAN_AUTO_TRANSMIT_OBJ, ZCAN_USBCAN_2E_U


def _mask_span(can_id: int, can_mask: int, limit: int) -> tuple[int, int] | None:
    """低位连续通配的掩码还原成闭区间。其它形状留给软件滤波。"""
    can_id &= limit
    can_mask &= limit
    wild = (~can_mask) & limit
    if wild & (wild + 1):
        return None
    if can_id & wild:
        return None
    return can_id, can_id | wild


class Usbcan2EUBus(ZlgBusBase):
    """周立功 USBCAN-2E-U（device_type=21）。"""

    CARD_LABEL = "USBCAN-2E-U"
    HW_PERIODIC_MAX = 32

    def __init__(self, channel, can_filters=None, **kwargs):
        kwargs.setdefault("device_type", ZCAN_USBCAN_2E_U)
        self._hw_jobs: dict[int, tuple[Message, int]] = {}
        super().__init__(channel, can_filters=can_filters, **kwargs)

    def send(self, msg: Message, timeout=None) -> None:
        if self._hw_jobs:
            raise can.CanOperationError(
                "硬件周期发送进行中，普通发送被禁止；请先停止周期任务"
            )
        super().send(msg, timeout=timeout)

    def _set_prop(self, path: str, value: bytes | ctypes.c_char_p) -> None:
        ok = self._dll.ZCAN_SetValue(self._entry.handle, path.encode("ascii"), value)
        if ok != STATUS_OK:
            raise can.CanOperationError(f"ZCAN_SetValue({path}) 失败，返回 {ok}")

    def _program_one(self, msg: Message, interval_ms: int, index: int) -> None:
        can_id, dlc, data = self._fill_tx(msg)
        obj = ZCAN_AUTO_TRANSMIT_OBJ()
        obj.enable = 1
        obj.index = index
        obj.interval = interval_ms
        obj.obj.frame.can_id = can_id
        obj.obj.frame.can_dlc = dlc
        for i, b in enumerate(data[:8]):
            obj.obj.frame.data[i] = b
        obj.obj.transmit_type = 0
        ptr = ctypes.cast(ctypes.pointer(obj), ctypes.c_char_p)
        self._set_prop(f"{self._channel}/auto_send", ptr)

    def _clear_hw_device(self) -> None:
        self._set_prop(f"{self._channel}/clear_auto_send", b"0")

    def _program_all_hw(self) -> None:
        with self._entry.lock:
            self._clear_hw_device()
            for index, (msg, interval_ms) in sorted(self._hw_jobs.items()):
                self._program_one(msg, interval_ms, index)

    def _alloc_hw(self, msg: Message, interval_ms: int) -> int:
        if interval_ms < 1:
            raise can.CanOperationError("硬件周期发送最小周期为 1ms")
        used = set(self._hw_jobs)
        for index in range(self.HW_PERIODIC_MAX):
            if index not in used:
                self._hw_jobs[index] = (msg, interval_ms)
                return index
        raise can.CanOperationError(
            f"硬件周期发送已满（最多 {self.HW_PERIODIC_MAX} 条）"
        )

    def _stop_hw_index(self, index: int) -> None:
        if index not in self._hw_jobs:
            return
        removed = self._hw_jobs.pop(index)
        try:
            self._program_all_hw()
        except Exception:
            self._hw_jobs[index] = removed
            raise

    def start_auto_send(self, msg: Message, interval_ms: int, index: int = 0) -> None:
        if index < 0 or index >= self.HW_PERIODIC_MAX:
            raise can.CanOperationError(f"定时发送索引越界: {index}")
        if index in self._hw_jobs:
            raise can.CanOperationError(f"定时发送索引已被占用: {index}")
        self._fill_tx(msg)
        self._hw_jobs[index] = (msg, int(interval_ms))
        try:
            self._program_all_hw()
        except Exception:
            self._hw_jobs.pop(index, None)
            raise

    def stop_auto_send(self) -> None:
        """先清硬件表，成功后再清空内部登记。"""
        with self._entry.lock:
            self._clear_hw_device()
        self._hw_jobs.clear()

    def _send_periodic_internal(
        self, msgs, period, duration=None, autostart=True, modifier_callback=None
    ):
        if duration is not None or modifier_callback is not None:
            raise can.CanOperationError(
                "硬件周期发送不支持 duration 或 modifier_callback"
            )
        if isinstance(msgs, Message):
            messages = [msgs]
        else:
            messages = list(msgs)
        if len(messages) != 1:
            raise can.CanOperationError("硬件周期发送每次只支持一帧")
        interval_ms = int(round(float(period) * 1000))
        msg = messages[0]
        index = self._alloc_hw(msg, interval_ms)
        task = _HwSendTask(self, msg, float(period), index)
        if not autostart:
            del self._hw_jobs[index]
            return task
        try:
            task.start()
        except Exception:
            self._hw_jobs.pop(index, None)
            raise
        return task

    def _apply_filters(self, filters) -> None:
        if not filters:
            self._program_ranges([(0, 0x7FF, False), (0, 0x1FFFFFFF, True)])
            return
        ranges: list[tuple[int, int, bool]] = []
        for item in filters:
            extended = bool(item.get("extended", False))
            limit = 0x1FFFFFFF if extended else 0x7FF
            span = _mask_span(int(item["can_id"]), int(item["can_mask"]), limit)
            if span is None:
                return
            ranges.append((span[0], span[1], extended))
        self._program_ranges(ranges)

    def set_acceptance(self, start: int, end: int, is_extended: bool) -> None:
        start_i, end_i = int(start), int(end)
        limit = 0x1FFFFFFF if is_extended else 0x7FF
        if start_i < 0 or end_i < start_i or end_i > limit:
            raise can.CanOperationError(
                f"滤波范围非法: 0x{start_i:X}..0x{end_i:X} extended={is_extended}"
            )
        self._program_ranges([(start_i, end_i, is_extended)])

    def accept_all(self) -> None:
        self._program_ranges([(0, 0x7FF, False), (0, 0x1FFFFFFF, True)])

    def _program_ranges(self, ranges: list[tuple[int, int, bool]]) -> None:
        ch = self._channel
        with self._entry.lock:
            self._set_prop(f"{ch}/filter_clear", b"0")
            for start_i, end_i, is_extended in ranges:
                mode = b"1" if is_extended else b"0"
                self._set_prop(f"{ch}/filter_mode", mode)
                self._set_prop(f"{ch}/filter_start", f"0x{start_i:08X}".encode("ascii"))
                self._set_prop(f"{ch}/filter_end", f"0x{end_i:08X}".encode("ascii"))
            self._set_prop(f"{ch}/filter_ack", b"0")

    def _shutdown_card_hooks(self) -> None:
        """关闭前清硬件定时发送。清理失败时保留 ``_hw_jobs`` 并向上抛出。"""
        try:
            with self._entry.lock:
                self._clear_hw_device()
        except Exception:
            # 内部登记仍保留，便于诊断与重试；不得假装已清理成功
            raise
        self._hw_jobs.clear()


class _HwSendTask(can.broadcastmanager.CyclicSendTaskABC):
    def __init__(self, bus: Usbcan2EUBus, msg: Message, period: float, index: int) -> None:
        super().__init__(msg, period)
        self._bus = bus
        self._index = index
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        if self._index not in self._bus._hw_jobs:
            interval_ms = int(round(self.period * 1000))
            self._index = self._bus._alloc_hw(self.messages[0], interval_ms)
        self._bus._program_all_hw()
        self._running = True

    def stop(self) -> None:
        if not self._running:
            raise can.CanError("周期任务已停止")
        # 先停硬件，成功后再清标志，便于失败时重试 stop
        self._bus._stop_hw_index(self._index)
        self._running = False
