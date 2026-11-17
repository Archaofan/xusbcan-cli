"""core 层：CLI 与 MCP 共享的业务逻辑。

只面向 can.Bus 与领域模型；唯一接触适配层的地方是通过 registry（不 import
adapters.zlg），绝不 import 厂商代码。
"""

from .commands import (
    accept_all_frames,
    capture,
    close_session,
    list_devices,
    map_error,
    monitor,
    open_session,
    parse_hex,
    periodic_list,
    periodic_start,
    periodic_stop,
    receive,
    receive_frame,
    send,
    set_frame_filter,
    status,
    transmit,
)
from .monitor import Monitor
from .periodic import MAX_PERIODIC_DURATION_S, PeriodicTask
from .session import CLOSE_TIMEOUT_S, Session, SessionManager, SessionState

__all__ = [
    "Session",
    "SessionManager",
    "SessionState",
    "CLOSE_TIMEOUT_S",
    "map_error",
    "PeriodicTask",
    "MAX_PERIODIC_DURATION_S",
    "Monitor",
    "transmit",
    "receive_frame",
    "capture",
    "send",
    "receive",
    "monitor",
    "open_session",
    "close_session",
    "list_devices",
    "status",
    "periodic_start",
    "periodic_stop",
    "periodic_list",
    "set_frame_filter",
    "accept_all_frames",
    "parse_hex",
]
