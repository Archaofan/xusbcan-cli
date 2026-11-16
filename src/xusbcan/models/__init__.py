"""领域模型（数据契约）：跨层共享的稳定数据结构。"""

from .device import BitrateConfig, DeviceSpec
from .frame import CanFrame
from .result import ErrorCode, ErrorInfo, Result

__all__ = [
    "BitrateConfig",
    "DeviceSpec",
    "CanFrame",
    "ErrorCode",
    "ErrorInfo",
    "Result",
]
