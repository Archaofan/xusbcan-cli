"""结构化结果契约：CLI 与 MCP 输出同一个 Result schema。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

SCHEMA_VERSION = "1.0"


class ErrorCode(str, Enum):
    """枚举化错误码。error.code 是 Agent 的程序化分支依据。"""

    DEVICE_NOT_FOUND = "DEVICE_NOT_FOUND"
    DEVICE_BUSY = "DEVICE_BUSY"
    DEVICE_OPEN_FAILED = "DEVICE_OPEN_FAILED"
    DLL_NOT_FOUND = "DLL_NOT_FOUND"
    DEVICE_NOT_OPEN = "DEVICE_NOT_OPEN"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    BITRATE_NOT_SUPPORTED = "BITRATE_NOT_SUPPORTED"
    CAPABILITY_UNSUPPORTED = "CAPABILITY_UNSUPPORTED"
    CHANNEL_OUT_OF_RANGE = "CHANNEL_OUT_OF_RANGE"
    BUS_OFF = "BUS_OFF"
    SEND_FAILED = "SEND_FAILED"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    MONITOR_ACTIVE = "MONITOR_ACTIVE"
    CLOSE_TIMEOUT = "CLOSE_TIMEOUT"
    CONFIG_ERROR = "CONFIG_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass
class ErrorInfo:
    code: str
    message: str
    detail: str | None = None
    context: dict = field(default_factory=dict)  # 仅诊断用，可含厂商名

    def to_dict(self) -> dict:
        d: dict = {"code": self.code, "message": self.message}
        if self.detail is not None:
            d["detail"] = self.detail
        if self.context:
            d["context"] = self.context
        return d


@dataclass
class Result:
    status: str  # "ok" | "error"
    data: Any = None
    error: ErrorInfo | None = None
    meta: dict = field(default_factory=dict)

    @classmethod
    def ok(cls, data: Any = None, **meta: Any) -> "Result":
        m = {"timestamp": _now(), "schema_version": SCHEMA_VERSION}
        m.update(meta)
        return cls(status="ok", data=data, meta=m)

    @classmethod
    def err(
        cls,
        code: ErrorCode | str,
        message: str,
        *,
        data: Any = None,
        detail: str | None = None,
        context: dict | None = None,
        **meta: Any,
    ) -> "Result":
        m = {"timestamp": _now(), "schema_version": SCHEMA_VERSION}
        m.update(meta)
        code_str = code.value if isinstance(code, ErrorCode) else str(code)
        return cls(
            status="error",
            data=data,
            error=ErrorInfo(code=code_str, message=message, detail=detail, context=context or {}),
            meta=m,
        )

    def to_dict(self) -> dict:
        d: dict = {
            "status": self.status,
            "data": self.data,
            "error": self.error.to_dict() if self.error else None,
            "meta": self.meta,
        }
        return d


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
