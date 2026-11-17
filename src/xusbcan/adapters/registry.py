"""打开设备：interface 直通 python-can，或按厂商目录里的型号快捷方式映射。

新增 python-can 已有后端不必改这里。需要通道映射或固定参数时，在
``adapters/<vendor>/profiles.py`` 增加 ``PROFILES``。python-can 没有的卡，
在该厂商目录里加 backend，并注册 ``can.interface`` 入口。
"""

from __future__ import annotations

import importlib
import pkgutil

import can

import xusbcan.adapters as adapters_pkg

from ..models.device import DeviceSpec
from ..models.result import ErrorCode, Result
from .profile import ChannelOutOfRange, ModelCapabilityError, Profile


def _discover_profiles() -> dict[tuple[str, str], Profile]:
    """收集 adapters/<厂商>/profiles.py。新增厂商目录即可，不必改本文件。"""
    merged: dict[tuple[str, str], Profile] = {}
    prefix = adapters_pkg.__name__ + "."
    for info in pkgutil.iter_modules(adapters_pkg.__path__):
        if not info.ispkg:
            continue
        try:
            module = importlib.import_module(prefix + info.name + ".profiles")
        except ModuleNotFoundError:
            continue
        part = getattr(module, "PROFILES", None)
        if not part:
            continue
        overlap = set(merged) & set(part)
        if overlap:
            raise RuntimeError(f"重复的型号登记: {sorted(overlap)}")
        merged.update(part)
    return merged


PROFILES = _discover_profiles()


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
        raise ModelCapabilityError(f"{spec.vendor}/{spec.model} 不支持 CAN FD 数据段波特率")
    if not isinstance(spec.channel, int):
        raise ChannelOutOfRange(f"该型号的通道必须是整数: {spec.channel!r}")
    if spec.channel < 0 or spec.channel >= profile.channels:
        raise ChannelOutOfRange(f"通道号越界: {spec.channel}（该设备 {profile.channels} 路）")

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
    except ChannelOutOfRange as e:
        return Result.err(ErrorCode.CHANNEL_OUT_OF_RANGE, str(e))
    except ModelCapabilityError as e:
        return Result.err(ErrorCode.CAPABILITY_UNSUPPORTED, str(e))
    except can.CanError as e:
        return Result.err(ErrorCode.DEVICE_OPEN_FAILED, f"打开设备失败: {e}")
    except Exception as e:  # noqa: BLE001 —— 收拢未知异常，避免接口层两套失败
        return Result.err(ErrorCode.INTERNAL_ERROR, f"内部错误: {e}")
    return Result.ok(bus)
