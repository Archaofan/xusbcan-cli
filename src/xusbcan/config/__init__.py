"""配置加载：TOML → DeviceSpec，供 CLI 与 MCP 共用。"""

from .loader import Config, DeviceEntry, find_config_path, load_config

__all__ = ["Config", "DeviceEntry", "find_config_path", "load_config"]
