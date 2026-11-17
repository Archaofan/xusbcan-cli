"""ZlgBus：把 zlgcan.dll 适配成 python-can 的 ``interface='zlg'`` backend。

经 entry point ``zlg = xusbcan.adapters.zlg.backend:ZlgBus`` 注册，与官方 backend
地位平等。上层只面向 can.Bus / can.Message，看不到厂商细节。

关键点（架构方案 v0.4 §4.4 / §11 / §12）：
  - 打开顺序：acquire 设备池 -> ZCAN_SetValue(baud_rate)（InitCAN 之前）
    -> ZCAN_InitCAN -> ZCAN_StartCAN。
  - InitCAN 成功但 StartCAN 失败时，构造内反向释放（ReleaseChannel + 归还池），
    不留半打开句柄。
  - 实现 _recv_internal（有限等待轮询，绝不用 wait_time=-1）与 send 与 shutdown，
    不覆盖 recv。
  - can_id 映射与 Linux socketcan 一致：arbitration_id = can_id & 0x1FFFFFFF；
    is_extended = can_id & 0x80000000；is_remote = can_id & 0x40000000。
  - 时间戳：设备上电微秒 -> 在 backend 内换算成 Unix 秒（float）。
"""

from __future__ import annotations

import ctypes
import time

import can
from can import BusABC, Message

from ...models.result import ErrorCode
from .device_pool import device_pool
from .dll import (
    INVALID_HANDLE,
    STATUS_OK,
    TYPE_CAN,
    ZCAN_AUTO_TRANSMIT_OBJ,
    ZCAN_USBCAN_2E_U,
    ZCAN_Receive_Data,
    ZCAN_Transmit_Data,
    ZlgError,
    get_dll,
    make_init_config,
)


class ZlgCapabilityUnsupportedError(ZlgError):
    """设备不支持该能力（对应 CAPABILITY_UNSUPPORTED），如 2E 卡发 CAN FD。"""

    code: ErrorCode = ErrorCode.CAPABILITY_UNSUPPORTED


class ZlgBus(BusABC):
    """周立功 zlgcan backend。channel 即 can_index（0/1）。"""

    def __init__(self, channel, can_filters=None, **kwargs):
        self._channel = int(channel)
        self._device_type = int(kwargs.pop("device_type", ZCAN_USBCAN_2E_U))
        self._device_index = int(kwargs.pop("device_index", 0))
        fd = bool(kwargs.pop("fd", False))
        data_bitrate = kwargs.pop("data_bitrate", None)
        for key in ("sjw", "tseg1", "tseg2", "sjw_abr", "tseg1_abr", "tseg2_abr"):
            kwargs.pop(key, None)
        if fd or data_bitrate:
            raise can.CanInitializationError("USBCAN-2E-U 不支持 CAN FD")
        bitrate = kwargs.pop("bitrate", None)
        if bitrate is None:
            raise can.CanInitializationError(
                "zlg backend 需要 bitrate（标称波特率），2E 卡必须显式设置"
            )
        self._bitrate = int(bitrate)

        # 惰性加载 DLL（此时才真正触碰 WinDLL / 环境变量）
        self._dll = get_dll()
        # acquire 设备池（首次才 OpenDevice）
        self._entry = device_pool.acquire(self._device_type, self._device_index)
        self._ch_handle = INVALID_HANDLE
        self._ts_ref: tuple[int, float] | None = None  # (设备微秒, Unix 秒) 参考点
        self._hw_jobs: dict[int, tuple[Message, int]] = {}  # index -> (帧, 周期 ms)

        try:
            self._open_channel()
        except Exception:
            # 反向释放：InitCAN 已成功则 ReleaseChannel + 移除通道占用，再归还池引用
            self._release_channel()
            device_pool.release(self._device_type, self._device_index)
            raise

        self.channel_info = f"zlg: device_type={self._device_type}, can_index={self._channel}"
        super().__init__(channel=channel, can_filters=can_filters, **kwargs)

    # ---- 打开序列 ----
    def _open_channel(self) -> None:
        """SetValue(baud_rate) -> InitCAN -> StartCAN（顺序不可变）。"""
        entry = self._entry
        dll = self._dll
        ch = self._channel
        with entry.lock:
            if ch in entry.open_channels:
                raise can.CanInitializationError(f"通道 {ch} 已被本进程占用")
            key = f"{ch}/baud_rate".encode("ascii")
            ok = dll.ZCAN_SetValue(
                entry.handle, key, str(self._bitrate).encode("ascii")
            )
            if ok != STATUS_OK:
                raise can.CanInitializationError(
                    f"ZCAN_SetValue({key.decode()}) 失败，返回 {ok}"
                )
            cfg = make_init_config()
            ch_handle = dll.ZCAN_InitCAN(entry.handle, ch, ctypes.byref(cfg))
            if not ch_handle:
                raise can.CanInitializationError(f"ZCAN_InitCAN 通道 {ch} 失败（空句柄）")
            # InitCAN 成功，记录通道占用，供反向释放判断
            self._ch_handle = ch_handle
            entry.open_channels.add(ch)
            r = dll.ZCAN_StartCAN(ch_handle)
            if r != STATUS_OK:
                raise can.CanInitializationError(
                    f"ZCAN_StartCAN 通道 {ch} 失败，返回 {r}"
                )

    def _release_channel(self) -> None:
        """反向释放通道句柄（若已 InitCAN），并从设备池移除通道占用。幂等。

        只有真正持有通道句柄（InitCAN 成功）才移除 open_channels，避免失败重入
        的实例误删其它实例登记的通道占用。
        """
        entry = self._entry
        if entry is None:
            return
        with entry.lock:
            if self._ch_handle not in (INVALID_HANDLE, None):
                # 通道随 CloseDevice（最后一路）释放；zlgcan 无独立 ReleaseChannel API，
                # 这里只做簿记（移除通道占用 + 置空句柄）。
                self._ch_handle = INVALID_HANDLE
                entry.open_channels.discard(self._channel)

    # ---- 发送 ----
    def send(self, msg: Message, timeout=None) -> None:
        if self._hw_jobs:
            raise can.CanOperationError(
                "硬件周期发送进行中，普通发送被禁止；请先停止周期任务"
            )
        if msg.is_fd:
            # 2E 卡不支持 CAN FD，不送进 DLL
            raise ZlgCapabilityUnsupportedError(
                "USBCAN-2E-U 不支持 CAN FD（is_fd=True）"
            )

        data = bytes(msg.data) if msg.data is not None else b""
        if msg.is_remote_frame:
            dlc = int(msg.dlc or 0)
        else:
            dlc = len(data)
        if dlc > 8:
            raise can.CanOperationError(f"经典 CAN 数据长度 {dlc} 超过 8 字节")

        can_id = msg.arbitration_id & 0x1FFFFFFF
        if msg.is_extended_id:
            can_id |= 0x80000000
        if msg.is_remote_frame:
            can_id |= 0x40000000

        tx = ZCAN_Transmit_Data()
        tx.frame.can_id = can_id
        tx.frame.can_dlc = dlc
        for i, b in enumerate(data[:8]):
            tx.frame.data[i] = b
        tx.transmit_type = 0  # 正常发送

        # 同一张卡的发送 / 接收 / SetValue 都走设备池互斥锁
        with self._entry.lock:
            sent = self._dll.ZCAN_Transmit(self._ch_handle, ctypes.byref(tx), 1)
        # 返回「成功帧数」；无 ACK 时 Transmit 阻塞约 3.5s 后返回 0
        if sent != 1:
            raise can.CanOperationError(
                f"ZCAN_Transmit 发送失败，成功帧数 {sent}（期望 1）"
            )

    # ---- 硬件定时发送（send_periodic 的适配层覆盖）----
    HW_PERIODIC_MAX = 32

    def _set_prop(self, path: str, value: bytes | ctypes.c_char_p) -> None:
        ok = self._dll.ZCAN_SetValue(self._entry.handle, path.encode("ascii"), value)
        if ok != STATUS_OK:
            raise can.CanOperationError(f"ZCAN_SetValue({path}) 失败，返回 {ok}")

    def _fill_tx(self, msg: Message) -> tuple[int, int, bytes]:
        if msg.is_fd:
            raise ZlgCapabilityUnsupportedError("USBCAN-2E-U 不支持 CAN FD")
        data = bytes(msg.data) if msg.data is not None else b""
        dlc = int(msg.dlc or 0) if msg.is_remote_frame else len(data)
        if dlc > 8:
            raise can.CanOperationError(f"经典 CAN 数据长度 {dlc} 超过 8 字节")
        can_id = msg.arbitration_id & 0x1FFFFFFF
        if msg.is_extended_id:
            can_id |= 0x80000000
        if msg.is_remote_frame:
            can_id |= 0x40000000
        return can_id, dlc, data

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
        """清空后按表重下。设备侧 clear 会清整表，停止单条时也必须重下其余条目。"""
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
        del self._hw_jobs[index]
        self._program_all_hw()

    def start_auto_send(self, msg: Message, interval_ms: int, index: int = 0) -> None:
        """启动一条硬件定时发送。开启后本通道不能再普通 send()，直到全部停止。"""
        if index < 0 or index >= self.HW_PERIODIC_MAX:
            raise can.CanOperationError(f"定时发送索引越界: {index}")
        if index in self._hw_jobs:
            raise can.CanOperationError(f"定时发送索引已被占用: {index}")
        self._fill_tx(msg)
        self._hw_jobs[index] = (msg, int(interval_ms))
        self._program_all_hw()

    def stop_auto_send(self) -> None:
        """清除本通道全部硬件定时发送，并恢复普通发送。"""
        self._hw_jobs.clear()
        with self._entry.lock:
            self._clear_hw_device()

    def _send_periodic_internal(
        self, msgs, period, duration=None, autostart=True, modifier_callback=None
    ):
        """python-can send_periodic 的硬件实现。不支持 duration 与数据改写回调。"""
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

    # ---- 硬件滤波（运行时，非掉电保存）----
    def set_acceptance(self, start: int, end: int, is_extended: bool) -> None:
        """用一条范围替换本通道滤波表。空表不会被留下。"""
        start_i, end_i = int(start), int(end)
        limit = 0x1FFFFFFF if is_extended else 0x7FF
        if start_i < 0 or end_i < start_i or end_i > limit:
            raise can.CanOperationError(
                f"滤波范围非法: 0x{start_i:X}..0x{end_i:X} extended={is_extended}"
            )
        mode = b"1" if is_extended else b"0"
        ch = self._channel
        with self._entry.lock:
            self._set_prop(f"{ch}/filter_clear", b"0")
            self._set_prop(f"{ch}/filter_mode", mode)
            self._set_prop(f"{ch}/filter_start", f"0x{start_i:08X}".encode("ascii"))
            self._set_prop(f"{ch}/filter_end", f"0x{end_i:08X}".encode("ascii"))
            self._set_prop(f"{ch}/filter_ack", b"0")

    def accept_all(self) -> None:
        """恢复全收：标准帧全范围 + 扩展帧全范围，再确认一次。"""
        ch = self._channel
        with self._entry.lock:
            self._set_prop(f"{ch}/filter_clear", b"0")
            self._set_prop(f"{ch}/filter_mode", b"0")
            self._set_prop(f"{ch}/filter_start", b"0x00000000")
            self._set_prop(f"{ch}/filter_end", b"0x000007FF")
            self._set_prop(f"{ch}/filter_mode", b"1")
            self._set_prop(f"{ch}/filter_start", b"0x00000000")
            self._set_prop(f"{ch}/filter_end", b"0x1FFFFFFF")
            self._set_prop(f"{ch}/filter_ack", b"0")

    # ---- 接收 ----
    def _recv_internal(self, timeout):
        """有限等待轮询：GetReceiveNum + Receive(wait_time<=100)，绝不用 -1 阻塞。"""
        deadline = None if timeout is None else time.monotonic() + timeout
        while not self._is_shutdown:
            if deadline is None:
                wait_ms = 100
            else:
                remain = deadline - time.monotonic()
                if remain <= 0:
                    return None, False
                wait_ms = min(100, max(1, int(remain * 1000)))

            with self._entry.lock:
                n = self._dll.ZCAN_GetReceiveNum(self._ch_handle, TYPE_CAN)
                if n > 0:
                    rx = ZCAN_Receive_Data()
                    if self._dll.ZCAN_Receive(
                        self._ch_handle, ctypes.byref(rx), 1, 0
                    ) == 1:
                        return self._make_message(rx), False
                rx = ZCAN_Receive_Data()
                if self._dll.ZCAN_Receive(
                    self._ch_handle, ctypes.byref(rx), 1, wait_ms
                ) == 1:
                    return self._make_message(rx), False
        return None, False

    def _make_message(self, rx: ZCAN_Receive_Data) -> Message:
        can_id = int(rx.frame.can_id)
        is_extended = bool(can_id & 0x80000000)
        is_remote = bool(can_id & 0x40000000)
        dlc = min(int(rx.frame.can_dlc), 8)
        data = b"" if is_remote else bytes(rx.frame.data[:dlc])
        return Message(
            timestamp=self._device_ts_to_unix(int(rx.timestamp)),
            arbitration_id=can_id & 0x1FFFFFFF,
            is_extended_id=is_extended,
            is_remote_frame=is_remote,
            channel=self._channel,
            dlc=dlc,
            data=data,
            is_fd=False,
            check=False,
        )

    def _device_ts_to_unix(self, device_us: int) -> float:
        """设备上电后微秒 -> Unix 秒（float）。首个接收帧建立参考点。"""
        if self._ts_ref is None:
            self._ts_ref = (device_us, time.time())
        ref_us, ref_unix = self._ts_ref
        return ref_unix + max(0, device_us - ref_us) / 1e6

    # ---- 关闭 ----
    def shutdown(self) -> None:
        if getattr(self, "_is_shutdown", False):
            return
        self._hw_jobs.clear()
        try:
            with self._entry.lock:
                self._clear_hw_device()
        except Exception:
            pass
        super().shutdown()  # 置 _is_shutdown + 停周期任务
        # 释放通道句柄，再归还设备池引用（最后一路才 CloseDevice）
        self._release_channel()
        device_pool.release(self._device_type, self._device_index)


class _HwSendTask(can.broadcastmanager.CyclicSendTaskABC):
    """一条硬件定时发送。stop 后从设备表删除并重下其余条目。"""

    def __init__(self, bus: ZlgBus, msg: Message, period: float, index: int) -> None:
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
        self._running = False
        self._bus._stop_hw_index(self._index)
