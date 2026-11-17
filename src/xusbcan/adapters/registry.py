"""单一适配链路：DeviceSpec → registry → can.Bus。

zlg 是 python-can 的自定义 interface，经 entry point 注册，与官方 backend 地位平等。
本模块模块级不 import adapters.zlg，保证 Linux 上可导入（virtual 后端测试可运行）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import can

from ..models.device import DeviceSpec
from ..models.result import ErrorCode, Result


@dataclass
class Profile:
    """(vendor, model) → backend 的映射。options 是 backend 专属选项，进 can.Bus kwargs。"""

    interface: str  # python-can interface 名
    channels: int = 1  # 通道数（能力查询 + 越界检查）
    fd: bool = False  # 是否支持 CAN FD
    channel_map: Callable[[int], int | str] | None = None  # 逻辑通道号 → 厂商通道地址
    options: dict | None = None  # backend 专属选项（不混入厂商联合体）


# 注意：周立功手册的 "CANalyst-II+" 走 zlgcan；python-can 官方 canalystii（创芯
# CANalyst-II）是否覆盖它尚未证实，暂不把创芯卡列为「改配置即可」。
PROFILES: dict[tuple[str, str], Profile] = {
    ("zlg", "USBCAN-2E-U"): Profile(
        "zlg", channels=2, fd=False, options={"device_type": 21, "device_index": 0}
    ),
    ("peak", "PCAN-USB"): Profile("pcan", channel_map=lambda n: f"PCAN_USBBUS{n + 1}"),
    ("vector", "VN1630"): Profile("vector", channels=2, fd=True),
}


def resolve(spec: DeviceSpec) -> Profile:
    """按 (vendor, model) 查 Profile。找不到抛 KeyError，由调用方转 CONFIG_ERROR。"""
    key = (spec.vendor, spec.model)
    try:
        return PROFILES[key]
    except KeyError as e:
        raise KeyError(f"未注册的设备: {spec.vendor}/{spec.model}") from e


def _bus_kwargs(
    spec: DeviceSpec,
    interface: str,
    channel: int | str | None,
    options: dict | None,
) -> dict:
    kwargs: dict = dict(options or {})
    kwargs.update(spec.extra or {})
    kwargs.pop("interface", None)
    kwargs.pop("channel", None)
    kwargs["interface"] = interface
    kwargs["channel"] = channel
    kwargs["ignore_config"] = True
    if spec.bitrate is not None:
        kwargs["bitrate"] = spec.bitrate.nominal
        if spec.bitrate.data is not None:
            kwargs["data_bitrate"] = spec.bitrate.data
            kwargs["fd"] = True
        if spec.bitrate.sjw is not None:
            kwargs.setdefault("sjw", spec.bitrate.sjw)
            kwargs.setdefault("sjw_abr", spec.bitrate.sjw)
        if spec.bitrate.tseg1 is not None:
            kwargs.setdefault("tseg1", spec.bitrate.tseg1)
            kwargs.setdefault("tseg1_abr", spec.bitrate.tseg1)
        if spec.bitrate.tseg2 is not None:
            kwargs.setdefault("tseg2", spec.bitrate.tseg2)
            kwargs.setdefault("tseg2_abr", spec.bitrate.tseg2)
    return kwargs


def open_bus(spec: DeviceSpec) -> can.BusABC:
    """打开 can.Bus。写了 interface 就用 python-can 该后端；否则按型号登记做通道映射。"""
    if spec.interface:
        if spec.interface not in can.interfaces.VALID_INTERFACES:
            raise KeyError(f"python-can 未声明该接口: {spec.interface}")
        return can.Bus(**_bus_kwargs(spec, spec.interface, spec.channel, None))

    profile = resolve(spec)
    if spec.bitrate is not None and spec.bitrate.data is not None and not profile.fd:
        raise ValueError(f"{spec.vendor}/{spec.model} 不支持 CAN FD 数据段波特率")
    if not isinstance(spec.channel, int):
        raise ValueError(f"该型号的通道必须是整数: {spec.channel!r}")
    if spec.channel < 0 or spec.channel >= profile.channels:
        raise ValueError(f"通道号越界: {spec.channel}（该设备 {profile.channels} 路）")

    channel: int | str = spec.channel
    if profile.channel_map is not None:
        channel = profile.channel_map(spec.channel)
    return can.Bus(**_bus_kwargs(spec, profile.interface, channel, profile.options))


def open_device(spec: DeviceSpec) -> Result:
    """带错误转换的打开入口。core 通过它拿 can.Bus，不直接接触厂商异常。"""
    try:
        bus = open_bus(spec)
    except KeyError as e:
        return Result.err(ErrorCode.CONFIG_ERROR, str(e))
    except ValueError as e:
        code = ErrorCode.CHANNEL_OUT_OF_RANGE if "通道" in str(e) else ErrorCode.CONFIG_ERROR
        return Result.err(code, str(e))
    except can.CanError as e:
        return Result.err(ErrorCode.DEVICE_OPEN_FAILED, f"打开设备失败: {e}")
    except Exception as e:  # noqa: BLE001 —— 收拢未知异常，避免接口层两套失败
        return Result.err(ErrorCode.INTERNAL_ERROR, f"内部错误: {e}")
    return Result.ok(bus)
