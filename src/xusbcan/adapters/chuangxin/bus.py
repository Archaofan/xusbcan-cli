"""创芯 ControlCAN 总线：经典 CAN 收发；滤波与周期走 python-can 软件路径。"""

from __future__ import annotations

import ctypes
import time

import can
from can import BusABC, Message

from ...models.result import ErrorCode
from .device_pool import device_pool
from .dll import (
    STATUS_OK,
    VCI_CAN_OBJ,
    VCI_USBCAN2,
    ChuangxinError,
    get_dll,
    make_init_config,
)


class ChuangxinCapabilityUnsupportedError(ChuangxinError):
    code: ErrorCode = ErrorCode.CAPABILITY_UNSUPPORTED


class ChuangxinBus(BusABC):
    """USB_CAN-2C / USB_CAN-2A-GD 等：DeviceType=4 的 ControlCAN 路径。"""

    CARD_LABEL = "chuangxin"

    def __init__(self, channel, can_filters=None, **kwargs):
        self._channel = int(channel)
        self._device_type = int(kwargs.pop("device_type", VCI_USBCAN2))
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
                f"{self.CARD_LABEL} 需要 bitrate（标称波特率）"
            )
        self._bitrate = int(bitrate)

        self._dll = get_dll()
        self._entry = device_pool.acquire(self._device_type, self._device_index)
        self._ts_ref: tuple[int, float] | None = None

        try:
            self._open_channel()
        except Exception:
            device_pool.release(self._device_type, self._device_index)
            raise

        self.channel_info = (
            f"chuangxin: device_type={self._device_type}, "
            f"device_index={self._device_index}, can_index={self._channel}"
        )
        super().__init__(channel=channel, can_filters=can_filters, **kwargs)

    def _open_channel(self) -> None:
        entry = self._entry
        dll = self._dll
        ch = self._channel
        with entry.lock:
            if ch in entry.open_channels:
                raise can.CanInitializationError(f"通道 {ch} 已被本进程占用")
            cfg = make_init_config(self._bitrate)
            ret = int(
                dll.VCI_InitCAN(
                    self._device_type,
                    self._device_index,
                    ch,
                    ctypes.byref(cfg),
                )
            )
            if ret != STATUS_OK:
                raise can.CanInitializationError(
                    f"VCI_InitCAN 通道 {ch} 失败，返回 {ret}"
                )
            ret = int(dll.VCI_StartCAN(self._device_type, self._device_index, ch))
            if ret != STATUS_OK:
                raise can.CanInitializationError(
                    f"VCI_StartCAN 通道 {ch} 失败，返回 {ret}"
                )
            entry.open_channels.add(ch)

    def _release_channel(self) -> None:
        entry = self._entry
        if entry is None:
            return
        with entry.lock:
            entry.open_channels.discard(self._channel)

    def send(self, msg: Message, timeout=None) -> None:
        if msg.is_fd:
            raise ChuangxinCapabilityUnsupportedError(f"{self.CARD_LABEL} 不支持 CAN FD")
        data = bytes(msg.data) if msg.data is not None else b""
        dlc = int(msg.dlc or 0) if msg.is_remote_frame else len(data)
        if dlc > 8:
            raise can.CanOperationError(f"经典 CAN 数据长度 {dlc} 超过 8 字节")

        obj = VCI_CAN_OBJ()
        obj.ID = msg.arbitration_id & (0x1FFFFFFF if msg.is_extended_id else 0x7FF)
        obj.TimeStamp = 0
        obj.TimeFlag = 0
        obj.SendType = 0
        obj.RemoteFlag = 1 if msg.is_remote_frame else 0
        obj.ExternFlag = 1 if msg.is_extended_id else 0
        obj.DataLen = dlc
        for i, b in enumerate(data[:8]):
            obj.Data[i] = b

        with self._entry.lock:
            sent = int(
                self._dll.VCI_Transmit(
                    self._device_type,
                    self._device_index,
                    self._channel,
                    ctypes.byref(obj),
                    1,
                )
            )
        if sent != 1:
            raise can.CanOperationError(
                f"VCI_Transmit 发送失败，成功帧数 {sent}（期望 1）"
            )

    def _recv_internal(self, timeout):
        deadline = None if timeout is None else time.monotonic() + timeout
        obj = VCI_CAN_OBJ()
        while not self._is_shutdown:
            if deadline is None:
                wait_ms = 100
            else:
                remain = deadline - time.monotonic()
                if remain <= 0:
                    return None, False
                wait_ms = min(100, max(1, int(remain * 1000)))

            with self._entry.lock:
                n = int(
                    self._dll.VCI_GetReceiveNum(
                        self._device_type, self._device_index, self._channel
                    )
                )
                if n > 0:
                    got = int(
                        self._dll.VCI_Receive(
                            self._device_type,
                            self._device_index,
                            self._channel,
                            ctypes.byref(obj),
                            1,
                            0,
                        )
                    )
                    if got == 1:
                        return self._make_message(obj), False
                got = int(
                    self._dll.VCI_Receive(
                        self._device_type,
                        self._device_index,
                        self._channel,
                        ctypes.byref(obj),
                        1,
                        wait_ms,
                    )
                )
                if got == 1:
                    return self._make_message(obj), False
        return None, False

    def _make_message(self, obj: VCI_CAN_OBJ) -> Message:
        is_extended = bool(obj.ExternFlag)
        is_remote = bool(obj.RemoteFlag)
        dlc = min(int(obj.DataLen), 8)
        data = b"" if is_remote else bytes(obj.Data[:dlc])
        ts = int(obj.TimeStamp) if obj.TimeFlag else 0
        return Message(
            timestamp=self._device_ts_to_unix(ts),
            arbitration_id=int(obj.ID) & (0x1FFFFFFF if is_extended else 0x7FF),
            is_extended_id=is_extended,
            is_remote_frame=is_remote,
            channel=self._channel,
            dlc=dlc,
            data=data,
            is_fd=False,
            check=False,
        )

    def _device_ts_to_unix(self, device_tick: int) -> float:
        if self._ts_ref is None:
            self._ts_ref = (device_tick, time.time())
        ref_tick, ref_unix = self._ts_ref
        # ControlCAN 时间戳单位常为 0.1 ms；无 TimeFlag 时 tick=0，退化为墙钟。
        return ref_unix + max(0, device_tick - ref_tick) * 1e-4

    def shutdown(self) -> None:
        if getattr(self, "_is_shutdown", False):
            return
        super().shutdown()
        self._release_channel()
        device_pool.release(self._device_type, self._device_index)
