"""命令处理器：一次性命令与会话命令共用同一套 transmit / receive_frame / capture。

分层：
- 底层（面向已打开的 Session）：transmit / receive_frame / capture
- 别名级（复用规则）：send / receive / monitor
- 会话命令：open_session / close_session / periodic_*
- 查询：list_devices / status

十六进制解析、Result 序列化、异常翻译都只放一份，CLI 与 MCP 共用。
"""

from __future__ import annotations

from collections.abc import Iterable

import can

from ..adapters.profile import Profile
from ..adapters.registry import resolve
from ..models.frame import CanFrame
from ..models.result import ErrorCode, Result
from . import monitor as monitor_mod
from . import periodic as periodic_mod
from .filters import id_masks
from .session import Session, SessionManager, SessionState, map_error

__all__ = [
    "map_error",
    "parse_hex",
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
]


# --------------------------------------------------------------------------- #
# 公共工具
# --------------------------------------------------------------------------- #


def parse_hex(s: str) -> bytes:
    """十六进制字符串 → bytes。支持 "010203" 与 "01 02 03"、"0x01 0x02"。"""
    if not isinstance(s, str):
        raise ValueError(f"数据必须是字符串: {s!r}")
    cleaned = s.strip().replace("0x", "").replace("0X", "")
    cleaned = "".join(cleaned.split())
    if cleaned == "":
        return b""
    if len(cleaned) % 2 != 0:
        raise ValueError(f"十六进制数据长度必须为偶数: {s!r}")
    try:
        return bytes.fromhex(cleaned)
    except ValueError as e:
        raise ValueError(f"非法十六进制数据: {s!r}") from e


def profile_features(profile: Profile) -> dict:
    """Profile → list/status 里的 features 字段（§4.5）。"""
    return {
        "fd": profile.fd,
        "channels": profile.channels,
        "interface": profile.interface,
    }


def device_features(spec) -> dict:
    """直接指定的 python-can 接口，或型号登记表里的能力。"""
    if spec.interface:
        fd = bool(spec.bitrate is not None and spec.bitrate.data is not None)
        return {"fd": fd, "channels": None, "interface": spec.interface}
    return profile_features(resolve(spec))


# --------------------------------------------------------------------------- #
# 底层（面向已打开的 Session，一次性与会话共用）
# --------------------------------------------------------------------------- #


def transmit(session: Session, frames: CanFrame | Iterable[CanFrame]) -> Result:
    """在已打开的 session 上发送若干帧。多帧发送不是全有或全无。"""
    if isinstance(frames, CanFrame):
        frames = [frames]
    else:
        frames = list(frames)
    if not frames:
        return Result.err(ErrorCode.INVALID_ARGUMENT, "没有要发送的帧")
    sent = 0
    for i, frame in enumerate(frames):
        try:
            session.bus.send(frame.to_can_message())
            sent += 1
        except can.CanError as e:
            return Result.err(
                map_error(e, default_can=ErrorCode.SEND_FAILED),
                f"发送失败（第 {i + 1} 帧）: {e}",
                data={"sent": sent, "failed_index": i},
                detail=str(e),
            )
        except Exception as e:
            return Result.err(
                ErrorCode.INTERNAL_ERROR,
                f"发送异常（第 {i + 1} 帧）: {e}",
                data={"sent": sent, "failed_index": i},
                detail=str(e),
            )
    return Result.ok({"sent": sent})


def receive_frame(session: Session, timeout: float | None) -> Result:
    """在已打开的 session 上收一帧。超时是成功态；监听运行中返回 MONITOR_ACTIVE。"""
    if session.receive_owner is not None:
        return Result.err(
            ErrorCode.MONITOR_ACTIVE,
            "监听/采集已在进行",
            context={"alias": session.name},
        )
    try:
        msg = session.bus.recv(timeout=timeout)
    except can.CanTimeoutError:
        return Result.ok({"frame": None, "reason": "timeout"})
    except can.CanError as e:
        return Result.err(map_error(e), f"接收失败: {e}", detail=str(e))
    except Exception as e:
        return Result.err(ErrorCode.INTERNAL_ERROR, f"接收异常: {e}")
    if msg is None:
        return Result.ok({"frame": None, "reason": "timeout"})
    return Result.ok({"frame": CanFrame.from_can_message(msg).to_dict()})


def capture(
    session: Session,
    duration_s: float | None = None,
    max_frames: int | None = None,
) -> Result:
    """在已打开的 session 上有界采集（复用 monitor 实现）。"""
    return monitor_mod.capture_bounded(session, duration_s, max_frames)


# --------------------------------------------------------------------------- #
# 别名级（复用规则：已打开复用不 shutdown；未打开一次性 try/finally 关闭）
# --------------------------------------------------------------------------- #


def send(manager: SessionManager, alias: str, frames: CanFrame | Iterable[CanFrame]) -> Result:
    session, err, reused = manager.acquire(alias)
    if err is not None:
        return err
    assert session is not None
    try:
        return transmit(session, frames)
    finally:
        manager.release(session, reused)


def _apply_optional_filter(
    session: Session,
    start_id: int | None,
    end_id: int | None,
    is_extended: bool,
) -> Result | None:
    if start_id is None and end_id is None:
        return None
    if start_id is None or end_id is None:
        return Result.err(ErrorCode.INVALID_ARGUMENT, "滤波需要同时给出起始和结束 ID")
    try:
        apply_frame_filter(session.bus, start_id, end_id, is_extended)
    except ValueError as e:
        return Result.err(ErrorCode.INVALID_ARGUMENT, str(e))
    except can.CanError as e:
        return Result.err(ErrorCode.CAPABILITY_UNSUPPORTED, str(e))
    return None


def receive(
    manager: SessionManager,
    alias: str,
    timeout: float | None,
    start_id: int | None = None,
    end_id: int | None = None,
    is_extended: bool = False,
) -> Result:
    session, err, reused = manager.acquire(alias)
    if err is not None:
        return err
    assert session is not None
    try:
        filtered = _apply_optional_filter(session, start_id, end_id, is_extended)
        if filtered is not None:
            return filtered
        return receive_frame(session, timeout)
    finally:
        manager.release(session, reused)


def monitor(
    manager: SessionManager,
    alias: str,
    duration_s: float | None = None,
    max_frames: int | None = None,
    start_id: int | None = None,
    end_id: int | None = None,
    is_extended: bool = False,
) -> Result:
    session, err, reused = manager.acquire(alias)
    if err is not None:
        return err
    assert session is not None
    try:
        filtered = _apply_optional_filter(session, start_id, end_id, is_extended)
        if filtered is not None:
            return filtered
        return capture(session, duration_s, max_frames)
    finally:
        manager.release(session, reused)


# --------------------------------------------------------------------------- #
# 会话命令
# --------------------------------------------------------------------------- #


def open_session(manager: SessionManager, alias: str) -> Result:
    return manager.open(alias)


def close_session(manager: SessionManager, alias: str) -> Result:
    return manager.close(alias)


def _require_open(
    manager: SessionManager,
    alias: str,
    *,
    allow_error: bool = False,
) -> tuple[Session | None, Result | None]:
    """周期/监听等会话命令要求会话已显式打开（常驻持有），不复用一次性路径。

    ``allow_error=True``：允许 error 态（关闭前停周期失败后的观测与重试 stop）。
    """
    session = manager.get(alias)
    if session is None:
        return None, Result.err(ErrorCode.SESSION_NOT_FOUND, f"会话未打开: {alias}")
    if session.state is SessionState.OPEN:
        return session, None
    if allow_error and session.state is SessionState.ERROR:
        return session, None
    return None, Result.err(ErrorCode.DEVICE_NOT_OPEN, f"会话状态异常: {alias}")


def periodic_start(
    manager: SessionManager,
    alias: str,
    name: str,
    frame: CanFrame,
    period: float,
    duration_s: float | None = None,
) -> Result:
    session, err = _require_open(manager, alias)
    if err is not None:
        return err
    return periodic_mod.start(session, name, frame, period, duration_s=duration_s)


def periodic_stop(manager: SessionManager, alias: str, name: str) -> Result:
    session, err = _require_open(manager, alias, allow_error=True)
    if err is not None:
        return err
    return periodic_mod.stop(session, name)


def periodic_list(manager: SessionManager, alias: str) -> Result:
    session, err = _require_open(manager, alias, allow_error=True)
    if err is not None:
        return err
    return periodic_mod.list_tasks(session)


def apply_frame_filter(bus, start_id: int, end_id: int, is_extended: bool = False) -> str:
    """用 python-can 掩码替换接收范围。后端若实现 _apply_filters，可同时写入硬件。"""
    if not hasattr(bus, "set_filters"):
        raise can.CanError("当前设备不支持滤波")
    bus.set_filters(id_masks(start_id, end_id, is_extended))
    return "mask"


def clear_frame_filter(bus) -> str:
    """恢复全收。set_filters(None) 表示全部匹配；硬件后端在 _apply_filters 里装回全范围。"""
    if not hasattr(bus, "set_filters"):
        raise can.CanError("当前设备不支持滤波")
    bus.set_filters(None)
    return "mask"


def set_frame_filter(
    manager: SessionManager,
    alias: str,
    start_id: int,
    end_id: int,
    is_extended: bool = False,
) -> Result:
    """用一条 ID 范围替换接收滤波。需要已打开的会话。"""
    session, err = _require_open(manager, alias)
    if err is not None:
        return err
    assert session is not None
    try:
        mode = apply_frame_filter(session.bus, start_id, end_id, is_extended)
    except ValueError as e:
        return Result.err(ErrorCode.INVALID_ARGUMENT, str(e))
    except can.CanError as e:
        return Result.err(ErrorCode.CAPABILITY_UNSUPPORTED, str(e), context={"alias": alias})
    except Exception as e:
        return Result.err(ErrorCode.INTERNAL_ERROR, f"设置滤波失败: {e}")
    return Result.ok(
        {
            "start_id": start_id,
            "end_id": end_id,
            "is_extended": is_extended,
            "mode": mode,
        }
    )


def accept_all_frames(manager: SessionManager, alias: str) -> Result:
    """恢复接收全部帧。清滤波后的空表不会当成全收。"""
    session, err = _require_open(manager, alias)
    if err is not None:
        return err
    assert session is not None
    try:
        mode = clear_frame_filter(session.bus)
    except can.CanError as e:
        return Result.err(ErrorCode.CAPABILITY_UNSUPPORTED, str(e), context={"alias": alias})
    except Exception as e:
        return Result.err(ErrorCode.INTERNAL_ERROR, f"恢复全收失败: {e}")
    return Result.ok({"accept_all": True, "mode": mode})


# --------------------------------------------------------------------------- #
# 查询
# --------------------------------------------------------------------------- #


def list_devices(manager: SessionManager) -> Result:
    """§13：只读配置与会话表，不调 OpenDevice。"""
    devices = []
    for name, spec in manager.specs.items():
        try:
            features = device_features(spec)
        except KeyError:
            features = {}
        session = manager.get(name)
        opened = session is not None and session.state is SessionState.OPEN
        devices.append(
            {
                "name": name,
                "channel": spec.channel,
                "opened": opened,
                "features": features,
            }
        )
    return Result.ok({"devices": devices})


def status(manager: SessionManager, alias: str) -> Result:
    """§4.5：data 含 state / features / receive_owner。"""
    spec = manager.get_spec(alias)
    if spec is None:
        return Result.err(ErrorCode.SESSION_NOT_FOUND, f"会话不存在: {alias}")
    try:
        features = device_features(spec)
    except KeyError as e:
        return Result.err(ErrorCode.CONFIG_ERROR, str(e))
    session = manager.get(alias)
    return Result.ok(
        {
            "state": (session.state if session is not None else SessionState.CLOSED).value,
            "features": features,
            "receive_owner": session.receive_owner if session is not None else None,
        }
    )
