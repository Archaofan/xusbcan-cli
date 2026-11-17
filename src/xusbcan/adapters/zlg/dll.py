"""zlgcan.dll 的 ctypes 封装 + 惰性加载。

按公开二次开发 ABI 自研的 ctypes 绑定（字段布局与常见 ``can_frame`` /
通道初始化结构一致；本机探针曾核对：can_frame=16、ZCAN_Transmit_Data=20、
ZCAN_Receive_Data=24、ZCAN_CHANNEL_INIT_CONFIG=32 字节）。以 WinDLL
（__stdcall）加载用户自备的 DLL；**不**包含厂商 SDK 头文件或二进制原文。

模块级**不**加载 DLL：只有真正打开 zlg 设备时才调用 ``get_dll()``，保证
``import xusbcan.adapters.zlg.backend`` 在 Linux（无 DLL）上不报错。
"""

from __future__ import annotations

import ctypes
import functools
import os

import can

from ...models.result import ErrorCode

# ---- 基础类型 ----
UINT = ctypes.c_uint
BYTE = ctypes.c_ubyte
USHORT = ctypes.c_ushort
UINT64 = ctypes.c_uint64
VOID_P = ctypes.c_void_p

# ---- 常量 ----
ZCAN_USBCAN2 = 4  # USBCAN-II
ZCAN_USBCAN_2E_U = 21
TYPE_CAN = 0
STATUS_ERR = 0
STATUS_OK = 1
STATUS_ONLINE = 2  # ZCAN_IsDeviceOnLine 在线
STATUS_OFFLINE = 3  # ZCAN_IsDeviceOnLine 离线
INVALID_HANDLE = 0
DLL_FILENAME = "zlgcan.dll"
SDK_ENV_VAR = "ZLG_SDK_DIR"


# ---- 异常：zlg 适配层错误，携带 error.code 供 core 集中映射 ----
class ZlgError(can.CanError):
    """zlg 适配层异常基类。``code`` 是 ErrorCode 枚举，供 core 映射。"""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR


class ZlgConfigError(ZlgError):
    """环境变量 / 配置缺失（对应 CONFIG_ERROR）。"""

    code: ErrorCode = ErrorCode.CONFIG_ERROR


class ZlgDllNotFoundError(ZlgError):
    """SDK 目录或 DLL 缺失（对应 DLL_NOT_FOUND）。"""

    code: ErrorCode = ErrorCode.DLL_NOT_FOUND


# ---- 结构体（公开 ABI 布局；自然对齐）----


class can_frame(ctypes.Structure):
    _fields_ = [
        ("can_id", UINT),
        ("can_dlc", BYTE),
        ("_pad", BYTE),
        ("_res0", BYTE),
        ("_res1", BYTE),
        ("data", BYTE * 8),
    ]


class ZCAN_Transmit_Data(ctypes.Structure):
    _fields_ = [
        ("frame", can_frame),
        ("transmit_type", UINT),
    ]


class ZCAN_Receive_Data(ctypes.Structure):
    _fields_ = [
        ("frame", can_frame),
        ("timestamp", UINT64),
    ]


class ZCAN_AUTO_TRANSMIT_OBJ(ctypes.Structure):
    """硬件定时发送对象（2E 卡每通道最多 32 条）。interval 单位 ms。"""

    _fields_ = [
        ("enable", USHORT),  # 1=使能
        ("index", USHORT),  # 定时发送列表索引 0..n
        ("interval", UINT),  # 周期（ms）
        ("obj", ZCAN_Transmit_Data),
    ]


class ZCAN_DEVICE_INFO(ctypes.Structure):
    """设备基本信息（ZCAN_GetDeviceInf 填充）。"""

    _fields_ = [
        ("hw_Version", USHORT),
        ("fw_Version", USHORT),
        ("dr_Version", USHORT),
        ("in_Version", USHORT),
        ("irq_Num", USHORT),
        ("can_Num", BYTE),
        ("str_Serial_Num", ctypes.c_ubyte * 20),
        ("str_hw_Type", ctypes.c_ubyte * 40),
        ("reserved", USHORT * 4),
    ]


class ZCAN_CHANNEL_STATUS(ctypes.Structure):
    """通道状态（ZCAN_ReadChannelStatus 填充，可用于 BUS_OFF 检测）。"""

    _fields_ = [
        ("errInterrupt", BYTE),
        ("regMode", BYTE),
        ("regStatus", BYTE),
        ("regALCapture", BYTE),
        ("regECCapture", BYTE),
        ("regEWLimit", BYTE),
        ("regRECounter", BYTE),
        ("regTECounter", BYTE),
        ("Reserved", UINT),
    ]


class _InitCanCfg(ctypes.Structure):
    _fields_ = [
        ("acc_code", UINT),
        ("acc_mask", UINT),
        ("reserved", UINT),
        ("filter", BYTE),
        ("timing0", BYTE),
        ("timing1", BYTE),
        ("mode", BYTE),
    ]


class _InitCanFdCfg(ctypes.Structure):
    _fields_ = [
        ("acc_code", UINT),
        ("acc_mask", UINT),
        ("abit_timing", UINT),
        ("dbit_timing", UINT),
        ("brp", UINT),
        ("filter", BYTE),
        ("mode", BYTE),
        ("pad", USHORT),
        ("reserved", UINT),
    ]


class _InitUnion(ctypes.Union):
    _fields_ = [
        ("can", _InitCanCfg),
        ("canfd", _InitCanFdCfg),
    ]


class ZCAN_CHANNEL_INIT_CONFIG(ctypes.Structure):
    _fields_ = [
        ("can_type", UINT),
        ("config", _InitUnion),
    ]


def make_init_config() -> ZCAN_CHANNEL_INIT_CONFIG:
    """构造经典 CAN 通道初始化配置（2E 卡 timing0/timing1 忽略，mode=0 正常）。"""
    cfg = ZCAN_CHANNEL_INIT_CONFIG()
    cfg.can_type = TYPE_CAN
    cfg.config.can.acc_code = 0
    cfg.config.can.acc_mask = 0xFFFFFFFF
    cfg.config.can.filter = 0
    cfg.config.can.mode = 0  # 正常模式，1 为只听
    return cfg


def _resolve_dll_path() -> tuple[str, str]:
    """解析 SDK 目录与 DLL 路径。未设环境变量 -> CONFIG_ERROR；缺失 -> DLL_NOT_FOUND。"""
    sdk_dir = os.environ.get(SDK_ENV_VAR)
    if not sdk_dir:
        raise ZlgConfigError(
            f"环境变量 {SDK_ENV_VAR} 未设置，无法定位 {DLL_FILENAME}"
        )
    if not os.path.isdir(sdk_dir):
        raise ZlgDllNotFoundError(
            f"ZLG SDK 目录不存在: {sdk_dir}（请检查 {SDK_ENV_VAR}）"
        )
    dll_path = os.path.join(sdk_dir, DLL_FILENAME)
    if not os.path.isfile(dll_path):
        raise ZlgDllNotFoundError(f"{DLL_FILENAME} 缺失: {dll_path}")
    return sdk_dir, dll_path


def _load_dll():
    """加载 zlgcan.dll 并声明函数签名（__stdcall -> WinDLL）。"""
    sdk_dir, dll_path = _resolve_dll_path()
    os.add_dll_directory(sdk_dir)
    dll = ctypes.WinDLL(dll_path)

    dll.ZCAN_OpenDevice.restype = VOID_P
    dll.ZCAN_OpenDevice.argtypes = [UINT, UINT, UINT]

    dll.ZCAN_CloseDevice.restype = UINT
    dll.ZCAN_CloseDevice.argtypes = [VOID_P]

    dll.ZCAN_SetValue.restype = UINT
    dll.ZCAN_SetValue.argtypes = [VOID_P, ctypes.c_char_p, ctypes.c_char_p]

    dll.ZCAN_InitCAN.restype = VOID_P
    dll.ZCAN_InitCAN.argtypes = [VOID_P, UINT, ctypes.POINTER(ZCAN_CHANNEL_INIT_CONFIG)]

    dll.ZCAN_StartCAN.restype = UINT
    dll.ZCAN_StartCAN.argtypes = [VOID_P]

    dll.ZCAN_Transmit.restype = UINT
    dll.ZCAN_Transmit.argtypes = [VOID_P, ctypes.POINTER(ZCAN_Transmit_Data), UINT]

    dll.ZCAN_Receive.restype = UINT
    dll.ZCAN_Receive.argtypes = [VOID_P, ctypes.POINTER(ZCAN_Receive_Data), UINT, ctypes.c_int]

    dll.ZCAN_GetReceiveNum.restype = UINT
    dll.ZCAN_GetReceiveNum.argtypes = [VOID_P, BYTE]

    dll.ZCAN_GetDeviceInf.restype = UINT
    dll.ZCAN_GetDeviceInf.argtypes = [VOID_P, ctypes.POINTER(ZCAN_DEVICE_INFO)]

    dll.ZCAN_ReadChannelStatus.restype = UINT
    dll.ZCAN_ReadChannelStatus.argtypes = [VOID_P, ctypes.POINTER(ZCAN_CHANNEL_STATUS)]

    dll.ZCAN_ClearBuffer.restype = UINT
    dll.ZCAN_ClearBuffer.argtypes = [VOID_P]

    dll.ZCAN_ResetCAN.restype = UINT
    dll.ZCAN_ResetCAN.argtypes = [VOID_P]

    dll.ZCAN_GetValue.restype = VOID_P
    dll.ZCAN_GetValue.argtypes = [VOID_P, ctypes.c_char_p]

    dll.ZCAN_IsDeviceOnLine.restype = UINT
    dll.ZCAN_IsDeviceOnLine.argtypes = [VOID_P]

    return dll


@functools.lru_cache(maxsize=1)
def get_dll():
    """惰性获取已加载的 zlgcan.dll（进程内只加载一次）。

    首次调用时才真正触碰 WinDLL / 环境变量；异常不会被 lru_cache 缓存，
    修复配置后重试即可。
    """
    return _load_dll()
