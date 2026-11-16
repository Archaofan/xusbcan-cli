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
            nominal = d.get("nominal")
            bitrate = BitrateConfig(nominal=nominal) if nominal else None
            spec = DeviceSpec(
                vendor=d["vendor"],
                model=d["model"],
                channel=d.get("channel", 0),
                bitrate=bitrate,
                extra=d.get("extra", {}),
            )
        except KeyError as e:
            return Result.err(ErrorCode.CONFIG_ERROR, f"设备配置缺少字段: {e}")
        cfg.devices.append(DeviceEntry(name=d["name"], spec=spec))

    return Result.ok(cfg)
