"""创芯 ControlCAN.dll 的 ctypes 封装 + 惰性加载。

环境变量 ``CHUANGXIN_SDK_DIR`` 指向含 ControlCAN.dll 的目录（用户自备，不进仓库）。
用绝对路径加载，避免与其它同名 DLL 混淆。
"""

from __future__ import annotations

import ctypes
import functools
import os
from ctypes import POINTER, Structure, c_char, c_int, c_uint, c_ulong, c_ushort

import can

from ...models.result import ErrorCode

DLL_FILENAME = "ControlCAN.dll"
SDK_ENV_VAR = "CHUANGXIN_SDK_DIR"

# 与创芯 ControlCAN.h 一致：USBCAN-2A / USB_CAN-2C / CANalyst-II 均为 4。
VCI_USBCAN2 = 4

STATUS_OK = 1
STATUS_ERR = 0

# 常见波特率 → (Timing0, Timing1)，与创芯/同类 ControlCAN 时序表一致（8 MHz）。
_BITRATE_TIMING: dict[int, tuple[int, int]] = {
    1_000_000: (0x00, 0x14),
    800_000: (0x00, 0x16),
    500_000: (0x00, 0x1C),
    250_000: (0x01, 0x1C),
    125_000: (0x03, 0x1C),
    100_000: (0x04, 0x1C),
    50_000: (0x09, 0x1C),
}


class ChuangxinError(can.CanError):
    """创芯适配层异常。``code`` 供 core 映射。"""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR


class ChuangxinConfigError(ChuangxinError):
    code: ErrorCode = ErrorCode.CONFIG_ERROR


class VCI_BOARD_INFO(Structure):
    _fields_ = [
        ("hw_Version", c_ushort),
        ("fw_Version", c_ushort),
        ("dr_Version", c_ushort),
        ("in_Version", c_ushort),
        ("irq_Num", c_ushort),
        ("can_Num", ctypes.c_ubyte),
        ("str_Serial_Num", c_char * 20),
        ("str_hw_Type", c_char * 40),
        ("Reserved", c_ushort * 4),
    ]


class VCI_CAN_OBJ(Structure):
    _fields_ = [
        ("ID", c_uint),
        ("TimeStamp", c_uint),
        ("TimeFlag", ctypes.c_ubyte),
        ("SendType", ctypes.c_ubyte),
        ("RemoteFlag", ctypes.c_ubyte),
        ("ExternFlag", ctypes.c_ubyte),
        ("DataLen", ctypes.c_ubyte),
        ("Data", ctypes.c_ubyte * 8),
        ("Reserved", ctypes.c_ubyte * 3),
    ]


class VCI_INIT_CONFIG(Structure):
    _fields_ = [
        ("AccCode", c_ulong),
        ("AccMask", c_ulong),
        ("Reserved", c_ulong),
        ("Filter", ctypes.c_ubyte),
        ("Timing0", ctypes.c_ubyte),
        ("Timing1", ctypes.c_ubyte),
        ("Mode", ctypes.c_ubyte),
    ]


def bitrate_to_timing(bitrate: int) -> tuple[int, int]:
    """标称波特率 → ControlCAN Timing0/Timing1。"""
    try:
        return _BITRATE_TIMING[int(bitrate)]
    except KeyError as e:
        supported = ", ".join(str(b) for b in sorted(_BITRATE_TIMING))
        raise ValueError(f"不支持的波特率: {bitrate}（支持: {supported}）") from e


def make_init_config(bitrate: int) -> VCI_INIT_CONFIG:
    t0, t1 = bitrate_to_timing(bitrate)
    return VCI_INIT_CONFIG(
        AccCode=0,
        AccMask=0xFFFFFFFF,
        Reserved=0,
        Filter=0,
        Timing0=t0,
        Timing1=t1,
        Mode=0,
    )


def _load_dll() -> ctypes.WinDLL:
    root = os.environ.get(SDK_ENV_VAR)
    if not root or not str(root).strip():
        raise ChuangxinConfigError(
            f"环境变量 {SDK_ENV_VAR} 未设置，无法定位 {DLL_FILENAME}"
        )
    path = os.path.join(os.path.abspath(str(root).strip()), DLL_FILENAME)
    if not os.path.isfile(path):
        raise ChuangxinConfigError(f"未找到 {DLL_FILENAME}: {path}")

    dll = ctypes.WinDLL(path)

    dll.VCI_OpenDevice.restype = c_ulong
    dll.VCI_OpenDevice.argtypes = [c_ulong, c_ulong, c_ulong]

    dll.VCI_CloseDevice.restype = c_ulong
    dll.VCI_CloseDevice.argtypes = [c_ulong, c_ulong]

    dll.VCI_InitCAN.restype = c_ulong
    dll.VCI_InitCAN.argtypes = [c_ulong, c_ulong, c_ulong, POINTER(VCI_INIT_CONFIG)]

    dll.VCI_StartCAN.restype = c_ulong
    dll.VCI_StartCAN.argtypes = [c_ulong, c_ulong, c_ulong]

    dll.VCI_ResetCAN.restype = c_ulong
    dll.VCI_ResetCAN.argtypes = [c_ulong, c_ulong, c_ulong]

    dll.VCI_ClearBuffer.restype = c_ulong
    dll.VCI_ClearBuffer.argtypes = [c_ulong, c_ulong, c_ulong]

    dll.VCI_GetReceiveNum.restype = c_ulong
    dll.VCI_GetReceiveNum.argtypes = [c_ulong, c_ulong, c_ulong]

    dll.VCI_Transmit.restype = c_ulong
    dll.VCI_Transmit.argtypes = [
        c_ulong,
        c_ulong,
        c_ulong,
        POINTER(VCI_CAN_OBJ),
        c_ulong,
    ]

    dll.VCI_Receive.restype = c_ulong
    dll.VCI_Receive.argtypes = [
        c_ulong,
        c_ulong,
        c_ulong,
        POINTER(VCI_CAN_OBJ),
        c_ulong,
        c_int,
    ]

    dll.VCI_ReadBoardInfo.restype = c_ulong
    dll.VCI_ReadBoardInfo.argtypes = [c_ulong, c_ulong, POINTER(VCI_BOARD_INFO)]

    return dll


@functools.lru_cache(maxsize=1)
def get_dll() -> ctypes.WinDLL:
    """惰性加载 ControlCAN.dll（进程内按路径只加载一次）。"""
    return _load_dll()
