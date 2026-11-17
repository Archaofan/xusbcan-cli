"""配置加载（标准库 tomllib）。

搜索顺序（定死，CLI/MCP 一致，避免同一台机器上打开不同的卡）：
  1. --config 命令行参数
  2. 环境变量 XUSBCAN_CONFIG
  3. 当前目录 xusbcan.toml
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from ..models.device import BitrateConfig, DeviceSpec
from ..models.result import ErrorCode, Result


@dataclass
class DeviceEntry:
    """配置里的一个设备条目：逻辑别名 + DeviceSpec。别名是 SessionManager 的 key。"""

    name: str
    spec: DeviceSpec


@dataclass
class Config:
    server: dict = field(default_factory=dict)
    devices: list[DeviceEntry] = field(default_factory=list)


def _optional_int(entry: dict, key: str) -> int | None:
    if key not in entry or entry[key] is None:
        return None
    value = entry[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} 必须是整数")
    return value


def find_config_path(explicit: str | None = None) -> Path | None:
    """按搜索顺序找配置文件，找不到返回 None。"""
    if explicit:
        return Path(explicit)
    env = os.environ.get("XUSBCAN_CONFIG")
    if env:
        return Path(env)
    local = Path("xusbcan.toml")
    if local.exists():
        return local
    return None


def load_config(explicit: str | None = None) -> Result:
    """加载配置并解析为 Config。失败返回 Result.err(CONFIG_ERROR)。"""
    path = find_config_path(explicit)
    if path is None:
        return Result.err(
            ErrorCode.CONFIG_ERROR,
            "未找到配置文件（--config / XUSBCAN_CONFIG / ./xusbcan.toml）",
        )

    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        return Result.err(ErrorCode.CONFIG_ERROR, f"读取配置失败: {e}")

    cfg = Config(server=raw.get("server", {}))
    for d in raw.get("devices", []):
        try:
            nominal = _optional_int(d, "nominal")
            data = _optional_int(d, "data")
            sjw = _optional_int(d, "sjw")
            tseg1 = _optional_int(d, "tseg1")
            tseg2 = _optional_int(d, "tseg2")
            if nominal is None and any(v is not None for v in (data, sjw, tseg1, tseg2)):
                raise ValueError("设置 data、sjw、tseg1、tseg2 时必须同时设置 nominal")
            bitrate = (
                BitrateConfig(nominal=nominal, data=data, sjw=sjw, tseg1=tseg1, tseg2=tseg2)
                if nominal is not None
                else None
            )
            interface = d.get("interface")
            if interface is not None and not isinstance(interface, str):
                raise ValueError("interface 必须是字符串")
            interface = interface.strip() if isinstance(interface, str) else None
            if interface == "":
                interface = None
            if "channel" not in d:
                channel: int | str | None = None if interface else 0
            else:
                channel = d["channel"]
                if not isinstance(channel, (int, str)):
                    raise ValueError("channel 必须是整数或字符串")
            vendor = d.get("vendor", "")
            model = d.get("model", "")
            if not interface and (not vendor or not model):
                raise KeyError("vendor/model 或 interface")
            spec = DeviceSpec(
                vendor=vendor,
                model=model,
                channel=channel,
                bitrate=bitrate,
                extra=d.get("extra", {}),
                interface=interface,
            )
        except KeyError as e:
            return Result.err(ErrorCode.CONFIG_ERROR, f"设备配置缺少字段: {e}")
        except ValueError as e:
            return Result.err(ErrorCode.CONFIG_ERROR, str(e))
        cfg.devices.append(DeviceEntry(name=d["name"], spec=spec))

    return Result.ok(cfg)
