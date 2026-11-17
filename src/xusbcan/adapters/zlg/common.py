"""周立功 zlgcan 共用底座：打开 / 收发 / 关闭。

型号差异（硬件滤波、auto_send 等）放在各自文件，避免 2E 与 II 互相耦合。
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
    ZCAN_Receive_Data,
    ZCAN_Transmit_Data,
    ZlgError,
    get_dll,
    make_init_config,
)


class ZlgCapabilityUnsupportedError(ZlgError):
    """设备不支持该能力（对应 CAPABILITY_UNSUPPORTED），如发 CAN FD。"""

    code: ErrorCode = ErrorCode.CAPABILITY_UNSUPPORTED


class ZlgBusBase(BusABC):
    """共享打开序列与经典 CAN 收发。子类可覆盖滤波 / 周期发送。"""

    #: 用于错误文案
    CARD_LABEL = "zlg"

    def __init__(self, channel, can_filters=None, **kwargs):
        self._channel = int(channel)
        self._device_type = int(kwargs.pop("device_type"))
        self._device_index = int(kwargs.pop("device_index", 0))
        fd = bool(kwargs.pop("fd", False))
        data_bitrate = kwargs.pop("data_bitrate", None)
        for key in ("sjw", "tseg1", "tseg2", "sjw_abr", "tseg1_abr", "tseg2_abr"):
            kwargs.pop(key, None)
        if fd or data_bitrate:
            raise can.CanInitializationError(f"{self.CARD_LABEL} 不支持 CAN FD")
        bitrate = kwargs.pop("bitrate", None)
        if bitrate is None:
            raise can.CanInitializationError(
                f"zlg backend 需要 bitrate（标称波特率），{self.CARD_LABEL} 必须显式设置"
            )
        self._bitrate = int(bitrate)

        self._dll = get_dll()
        self._entry = device_pool.acquire(self._device_type, self._device_index)
        self._ch_handle = INVALID_HANDLE
        self._ts_ref: tuple[int, float] | None = None

        try:
            self._open_channel()
        except Exception:
            self._release_channel()
            device_pool.release(self._device_type, self._device_index)
            raise

        self.channel_info = f"zlg: device_type={self._device_type}, can_index={self._channel}"
        super().__init__(channel=channel, can_filters=can_filters, **kwargs)

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
            self._ch_handle = ch_handle
            entry.open_channels.add(ch)
            r = dll.ZCAN_StartCAN(ch_handle)
            if r != STATUS_OK:
                raise can.CanInitializationError(
                    f"ZCAN_StartCAN 通道 {ch} 失败，返回 {r}"
                )

    def _release_channel(self) -> None:
        """反向释放通道占用簿记。幂等。"""
        entry = self._entry
        if entry is None:
            return
        with entry.lock:
            if self._ch_handle not in (INVALID_HANDLE, None):
                self._ch_handle = INVALID_HANDLE
                entry.open_channels.discard(self._channel)

    def _fill_tx(self, msg: Message) -> tuple[int, int, bytes]:
        if msg.is_fd:
            raise ZlgCapabilityUnsupportedError(f"{self.CARD_LABEL} 不支持 CAN FD")
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

    def send(self, msg: Message, timeout=None) -> None:
        can_id, dlc, data = self._fill_tx(msg)
        tx = ZCAN_Transmit_Data()
        tx.frame.can_id = can_id
        tx.frame.can_dlc = dlc
        for i, b in enumerate(data[:8]):
            tx.frame.data[i] = b
        tx.transmit_type = 0

        with self._entry.lock:
            sent = self._dll.ZCAN_Transmit(self._ch_handle, ctypes.byref(tx), 1)
        if sent != 1:
            raise can.CanOperationError(
                f"ZCAN_Transmit 发送失败，成功帧数 {sent}（期望 1）"
            )

    def _recv_internal(self, timeout):
        """有限等待轮询：绝不用 wait_time=-1。"""
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
        if self._ts_ref is None:
            self._ts_ref = (device_us, time.time())
        ref_us, ref_unix = self._ts_ref
        return ref_unix + max(0, device_us - ref_us) / 1e6

    def shutdown(self) -> None:
        if getattr(self, "_is_shutdown", False):
            return
        self._shutdown_card_hooks()
        super().shutdown()
        self._release_channel()
        device_pool.release(self._device_type, self._device_index)

    def _shutdown_card_hooks(self) -> None:
        """型号在关闭前的清理；默认无额外动作。"""
        return None
